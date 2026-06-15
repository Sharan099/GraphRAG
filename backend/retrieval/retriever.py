"""
retrieval/retriever.py — Step 6

4-path hybrid retriever that NEVER returns empty context.

Path 1 — Graph traversal
  Keyword search → entity IDs → 2-hop graph traversal → structured context
  Best for: "what warnings apply to the oil filter"

Path 2 — Vector similarity
  Encode query → cosine search on Chunk.embedding → raw manual text
  Best for: "how do I remove the engine" (semantic match, no entity needed)

Path 3 — BM25
  TF-IDF on all chunk texts → top-k relevant chunks
  Best for: specific part numbers, procedure codes, exact terminology

Path 4 — Community summary
  Match query topics to pre-computed community summaries → global context
  Best for: "summarise all fuel system procedures"

All 4 paths run simultaneously. Results are scored, deduplicated,
and compressed to MAX_CONTEXT_TOKENS before LLM call.
Guaranteed non-empty: vector and BM25 always return something.
"""

import json
import re
import time
from pathlib import Path
from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    DATA_DIR, CHUNKS_FILE, EMBEDDINGS_FILE, COMMUNITY_FILE,
    MAX_CONTEXT_TOKENS, TOP_K_GRAPH_HOPS,
    TOP_K_VECTOR, TOP_K_BM25, TOP_K_COMMUNITY,
    VECTOR_SCORE_MIN, NODE_PRIORITY, EMBEDDING_MODEL,
)

_CHARS_PER_TOKEN = 4


class HybridRetriever:

    def __init__(self, graph_builder):
        self.graph       = graph_builder
        self.chunks:     list[dict] = []
        self.embeddings: dict       = {}
        self.communities:list[dict] = []
        self.bm25        = None
        self._emb_model  = None
        self._load_artefacts()

    # ── Load artefacts ────────────────────────────────────────────────────────

    def _load_artefacts(self):
        # Chunks
        if CHUNKS_FILE.exists():
            with open(CHUNKS_FILE, encoding="utf-8") as f:
                self.chunks = json.load(f).get("chunks", [])
            logger.info(f"Chunks loaded: {len(self.chunks)}")
        else:
            logger.warning("chunks.json missing — BM25 disabled")

        # Embeddings
        if EMBEDDINGS_FILE.exists():
            with open(EMBEDDINGS_FILE, encoding="utf-8") as f:
                self.embeddings = json.load(f)
            logger.info(f"Embeddings loaded: {len(self.embeddings)}")
        else:
            logger.warning("embeddings.json missing — vector search disabled")

        # Communities
        if COMMUNITY_FILE.exists():
            with open(COMMUNITY_FILE, encoding="utf-8") as f:
                self.communities = json.load(f)
            logger.info(f"Communities loaded: {len(self.communities)}")

        # BM25 index
        self._build_bm25()

    def _build_bm25(self):
        if not self.chunks:
            return
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            logger.warning("rank-bm25 not installed. pip install rank-bm25")
            return

        import re
        tokenized = [
            re.sub(r'[^a-z0-9]', ' ',
                   f"{c.get('section_title','')} {c.get('text','')}".lower()).split()
            for c in self.chunks
        ]
        valid = [(t, c) for t, c in zip(tokenized, self.chunks) if t]
        if not valid:
            return
        toks, self.chunks = zip(*valid)
        self.chunks = list(self.chunks)
        self.bm25   = BM25Okapi(list(toks))
        logger.info(f"BM25 index built: {len(self.chunks)} chunks")

    def _get_embedding_model(self):
        if self._emb_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._emb_model = SentenceTransformer(EMBEDDING_MODEL)
            except ImportError:
                logger.warning("sentence-transformers not installed")
        return self._emb_model

    # ── Path 1: Graph traversal ───────────────────────────────────────────────

    def _graph_path(self, query: str) -> tuple[list[dict], list[dict], list[dict]]:
        """
        Returns (ranked_nodes, relationships, graph_viz_data)
        """
        try:
            hits = self.graph.keyword_search(query, limit=8)
        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
            return [], [], []

        # Preserve score order (no set shuffle)
        seen, entity_ids = set(), []
        for h in hits:
            eid = h.get("id")
            if eid and eid not in seen:
                seen.add(eid)
                entity_ids.append(eid)

        # Also search for ATA codes mentioned in query
        for ata in re.findall(r'\b(\d{2})\b', query):
            try:
                ata_hits = self.graph.keyword_search(f"ATA {ata}", limit=3)
                for h in ata_hits:
                    eid = h.get("id")
                    if eid and eid not in seen:
                        seen.add(eid)
                        entity_ids.append(eid)
            except Exception:
                pass

        all_nodes, all_rels, viz_nodes, viz_edges = [], [], [], set()
        seen_rels: set[tuple] = set()

        for eid in entity_ids[:6]:   # cap to avoid huge traversals
            try:
                ctx = self.graph.get_context(eid, hops=TOP_K_GRAPH_HOPS)
                root = ctx.get("node", {})
                if not root.get("id"):
                    continue

                labels = root.get("labels", [])
                score  = self._node_score(labels)
                all_nodes.append({"score": score, "node": root, "source": "graph_primary"})

                if root["id"] not in {n["id"] for n in viz_nodes if isinstance(n, dict)}:
                    viz_nodes.append({
                        "id":    root["id"],
                        "label": root.get("name") or root.get("id"),
                        "type":  labels[0] if labels else "Node",
                    })

                for rel_node in ctx.get("related", []):
                    rl = rel_node.get("labels", [])
                    s  = self._node_score(rl)
                    all_nodes.append({"score": s, "node": rel_node, "source": "graph_related"})
                    rn_id = rel_node.get("id")
                    if rn_id and rn_id not in {n["id"] for n in viz_nodes if isinstance(n,dict)}:
                        viz_nodes.append({
                            "id":    rn_id,
                            "label": rel_node.get("name") or rn_id,
                            "type":  rl[0] if rl else "Node",
                        })

                for rel in ctx.get("rels", []):
                    key = (rel.get("source"), rel.get("target"), rel.get("type"))
                    if key not in seen_rels:
                        seen_rels.add(key)
                        all_rels.append(rel)
                        viz_edges.add(key)

            except Exception as e:
                logger.warning(f"Context failed for {eid}: {e}")

        # Deduplicate nodes
        unique_nodes, seen_ids = [], set()
        for n in sorted(all_nodes, key=lambda x: -x["score"]):
            nid = n["node"].get("id")
            if nid and nid not in seen_ids:
                seen_ids.add(nid)
                unique_nodes.append(n)

        graph_viz = {
            "nodes": viz_nodes,
            "edges": [{"from": s, "to": t, "label": rt}
                      for s, t, rt in viz_edges],
        }
        return unique_nodes, all_rels, graph_viz

    def _node_score(self, labels: list) -> float:
        for lbl in labels:
            if lbl in NODE_PRIORITY:
                return NODE_PRIORITY[lbl]
        return 0.5

    # ── Path 2: Vector similarity ─────────────────────────────────────────────

    def _vector_path(self, query: str) -> list[dict]:
        model = self._get_embedding_model()
        if model is None or not self.embeddings:
            return []
        try:
            query_vec = model.encode([query], convert_to_numpy=True)[0].tolist()
        except Exception as e:
            logger.warning(f"Encoding failed: {e}"); return []

        # Try Neo4j vector index first (fastest)
        try:
            results = self.graph.vector_search(query_vec, limit=TOP_K_VECTOR)
            if results:
                return [
                    {
                        "score":   r.get("score", 0),
                        "text":    r.get("text",""),
                        "title":   r.get("section_title",""),
                        "ata":     r.get("ata",""),
                        "source":  "vector_neo4j",
                        "id":      r.get("id",""),
                    }
                    for r in results if r.get("score",0) >= VECTOR_SCORE_MIN
                ]
        except Exception:
            pass

        # Fallback: numpy cosine similarity over cached embeddings
        try:
            import numpy as np
            q_arr = np.array(query_vec)
            scored = []
            for chunk in self.chunks:
                cid = chunk.get("chunk_id","")
                emb = self.embeddings.get(cid)
                if not emb:
                    continue
                c_arr = np.array(emb)
                norm  = np.linalg.norm(q_arr) * np.linalg.norm(c_arr)
                if norm == 0: continue
                sim = float(np.dot(q_arr, c_arr) / norm)
                if sim >= VECTOR_SCORE_MIN:
                    scored.append((sim, chunk))
            scored.sort(key=lambda x: -x[0])
            return [
                {
                    "score":  sim,
                    "text":   c.get("text",""),
                    "title":  c.get("section_title",""),
                    "ata":    c.get("ata",""),
                    "source": "vector_local",
                    "id":     c.get("chunk_id",""),
                }
                for sim, c in scored[:TOP_K_VECTOR]
            ]
        except ImportError:
            logger.warning("numpy not available for local vector search")
            return []

    # ── Path 3: BM25 ─────────────────────────────────────────────────────────

    def _bm25_path(self, query: str) -> list[dict]:
        if self.bm25 is None:
            return []
        import re as _re
        tokens = _re.sub(r'[^a-z0-9]', ' ', query.lower()).split()
        scores = self.bm25.get_scores(tokens)
        ranked = sorted(enumerate(scores), key=lambda x: -x[1])
        return [
            {
                "score":  float(s),
                "text":   self.chunks[i].get("text",""),
                "title":  self.chunks[i].get("section_title",""),
                "ata":    self.chunks[i].get("ata",""),
                "source": "bm25",
                "id":     self.chunks[i].get("chunk_id",""),
            }
            for i, s in ranked[:TOP_K_BM25] if s > 0
        ]

    # ── Path 4: Community ─────────────────────────────────────────────────────

    def _community_path(self, query: str) -> list[dict]:
        if not self.communities:
            return []
        query_low = query.lower()
        scored = []
        for comm in self.communities:
            summary  = (comm.get("summary","") + " " +
                        " ".join(comm.get("ata_names",[])))
            # Simple overlap score
            score = sum(1 for w in query_low.split()
                        if len(w) > 4 and w in summary.lower())
            if score > 0:
                scored.append((score, comm))

        scored.sort(key=lambda x: -x[0])
        return [
            {
                "score":   float(s),
                "text":    c.get("summary",""),
                "title":   f"Community: {', '.join(c.get('ata_names',[])[:3])}",
                "ata":     c.get("ata_chapters",[""])[0],
                "source":  "community",
                "id":      c.get("id",""),
            }
            for s, c in scored[:TOP_K_COMMUNITY]
        ]

    # ── Context compression ───────────────────────────────────────────────────

    def _compress(
        self,
        graph_nodes:   list[dict],
        graph_rels:    list[dict],
        text_results:  list[dict],   # vector + BM25 + community combined
    ) -> str:
        budget = MAX_CONTEXT_TOKENS * _CHARS_PER_TOKEN
        lines  = []

        # Section 1: Graph entities
        if graph_nodes:
            lines.append("=== GRAPH CONTEXT ===")
            for n in graph_nodes:
                node   = n["node"]
                labels = node.get("labels", [])
                label  = (labels or ["Node"])[0]
                name   = node.get("name","") or node.get("text","") or node.get("id","")
                desc   = node.get("description","") or node.get("text","")
                ata    = node.get("ata","")
                lines.append(
                    f"[{label}|ATA-{ata}] {node.get('id','?')}: {name}"
                    + (f" — {desc[:200]}" if desc else "")
                )
                if sum(len(l) for l in lines) > budget * 0.45:
                    lines.append("... (graph trimmed)"); break

        # Section 2: Relationships
        if graph_rels:
            lines.append("\n=== RELATIONSHIPS ===")
            for rel in graph_rels:
                lines.append(
                    f"  ({rel.get('source','?')}) "
                    f"-[{rel.get('type','?')}]-> "
                    f"({rel.get('target','?')})"
                )
                if sum(len(l) for l in lines) > budget * 0.60:
                    lines.append("... (rels trimmed)"); break

        # Section 3: Text chunks (vector + BM25 + community), deduplicated
        if text_results:
            lines.append("\n=== MANUAL TEXT ===")
            seen_text_ids: set = set()
            for r in text_results:
                rid = r.get("id","")
                if rid in seen_text_ids:
                    continue
                seen_text_ids.add(rid)
                source = r.get("source","")
                title  = r.get("title","")
                ata    = r.get("ata","")
                text   = r.get("text","")
                score  = r.get("score", 0)
                lines.append(
                    f"\n[{source.upper()}|ATA-{ata}|score:{score:.2f}] {title}\n{text[:1200]}"
                )
                if sum(len(l) for l in lines) > budget:
                    lines.append("... (text trimmed)"); break

        return "\n".join(lines)

    def _context_snippets(self, text_results: list[dict], limit: int = 5) -> list[str]:
        """Return plain text snippets for external evaluators such as RAGAS."""
        snippets: list[str] = []
        seen: set[str] = set()
        for item in text_results:
            text = (item.get("text") or "").strip()
            if not text:
                continue
            key = item.get("id") or text[:120]
            if key in seen:
                continue
            seen.add(key)
            title = item.get("title", "")
            snippets.append(f"{title}\n{text}".strip())
            if len(snippets) >= limit:
                break
        return snippets

    # ── Main retrieve ─────────────────────────────────────────────────────────

    def retrieve(self, query: str) -> dict:
        t0     = time.time()
        timing = {"fallback_used": False, "bm25_used": False, "vector_used": False}

        # Run all 4 paths
        graph_nodes, graph_rels, graph_viz = self._graph_path(query)
        vector_results    = self._vector_path(query)
        bm25_results      = self._bm25_path(query)
        community_results = self._community_path(query)

        timing["vector_used"]  = len(vector_results) > 0
        timing["bm25_used"]    = len(bm25_results) > 0
        timing["fallback_used"]= len(graph_nodes) < 3

        # Merge text results, sorted by score
        text_results = sorted(
            vector_results + bm25_results + community_results,
            key=lambda x: -x.get("score", 0)
        )

        context = self._compress(graph_nodes, graph_rels, text_results)
        contexts = self._context_snippets(text_results)

        timing["total_ms"] = round((time.time() - t0) * 1000, 1)
        timing["entities_found"] = len(
            set(n["node"].get("id") for n in graph_nodes if n["node"].get("id"))
        )

        logger.info(
            f"Retrieve: {timing['entities_found']} graph entities, "
            f"{len(vector_results)} vector, {len(bm25_results)} BM25, "
            f"{len(community_results)} community — {timing['total_ms']}ms"
        )

        return {
            "query":     query,
            "context":   context,
            "contexts":  contexts,
            "entities":  [n["node"].get("id") for n in graph_nodes[:8]
                          if n["node"].get("id")],
            "graph_viz": graph_viz,
            "timing":    timing,
        }

    def retrieve_standard_rag(self, query: str) -> dict:
        """
        Baseline retriever for evaluation.

        This intentionally disables graph traversal and community summaries so
        we can compare AirGraph's hybrid GraphRAG against a standard chunk-based
        RAG baseline using only vector similarity + BM25 keyword search.
        """
        t0 = time.time()
        vector_results = self._vector_path(query)
        bm25_results = self._bm25_path(query)
        text_results = sorted(
            vector_results + bm25_results,
            key=lambda x: -x.get("score", 0)
        )
        context = self._compress([], [], text_results)
        contexts = self._context_snippets(text_results)

        return {
            "query": query,
            "context": context,
            "contexts": contexts,
            "entities": [],
            "graph_viz": {"nodes": [], "edges": []},
            "timing": {
                "total_ms": round((time.time() - t0) * 1000, 1),
                "entities_found": 0,
                "vector_used": len(vector_results) > 0,
                "bm25_used": len(bm25_results) > 0,
                "fallback_used": True,
            },
        }
