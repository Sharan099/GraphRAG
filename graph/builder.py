import json
import sys
from pathlib import Path
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    DATA_DIR, CHUNKS_FILE, ENTITIES_FILE, EMBEDDINGS_FILE,
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_TIMEOUT,
    NEO4J_VECTOR_INDEX, NEO4J_VECTOR_DIMENSION,
)

try:
    from neo4j import GraphDatabase
except ImportError:
    print("ERROR: pip install neo4j"); sys.exit(1)


# ── Helpers ────────────────────────────────────────────────────────────────────

def san(v):
    """Sanitize a value for Neo4j property storage."""
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, dict):
        return json.dumps(v)
    if isinstance(v, list):
        return [san(i) for i in v]
    return str(v)

def san_props(props: dict) -> dict:
    return {k: san(v) for k, v in props.items() if v is not None and v != ""}


# ── Graph builder ─────────────────────────────────────────────────────────────

class GraphBuilder:

    def __init__(self):
        self.driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD),
            connection_timeout=NEO4J_TIMEOUT
        )
        logger.info(f"Connected: {NEO4J_URI}")

    def close(self):
        self.driver.close()

    def _run(self, session, query: str, **params):
        try:
            session.run(query, **params)
        except Exception as e:
            logger.warning(f"Cypher failed: {e}\nQuery: {query[:120]}")

    # ── Constraints & indexes ─────────────────────────────────────────────────

    def create_constraints(self):
        stmts = [
            # Fulltext index — all text-searchable fields
            """CREATE FULLTEXT INDEX aircraftFulltext IF NOT EXISTS
               FOR (n:Component|System|Tool|Warning|Step|Requirement|Measurement|DocumentSection|Chunk|Community)
               ON EACH [n.id, n.name, n.title, n.description, n.text, n.ata, n.system, n.level_text]""",
            # Unique ID constraints
            "CREATE CONSTRAINT c_comp  IF NOT EXISTS FOR (n:Component)       REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT c_sys   IF NOT EXISTS FOR (n:System)           REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT c_tool  IF NOT EXISTS FOR (n:Tool)             REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT c_warn  IF NOT EXISTS FOR (n:Warning)          REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT c_step  IF NOT EXISTS FOR (n:Step)             REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT c_req   IF NOT EXISTS FOR (n:Requirement)      REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT c_meas  IF NOT EXISTS FOR (n:Measurement)      REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT c_sec   IF NOT EXISTS FOR (n:DocumentSection)  REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT c_chunk IF NOT EXISTS FOR (n:Chunk)            REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT c_comm  IF NOT EXISTS FOR (n:Community)        REQUIRE n.id IS UNIQUE",
        ]
        with self.driver.session() as s:
            for q in stmts:
                try: s.run(q)
                except Exception as e: logger.warning(f"Constraint: {e}")
        logger.info("Constraints ready")

    def create_vector_index(self):
        """Create a vector index on Chunk.embedding for semantic search."""
        q = f"""
        CREATE VECTOR INDEX {NEO4J_VECTOR_INDEX} IF NOT EXISTS
        FOR (n:Chunk) ON n.embedding
        OPTIONS {{
            indexConfig: {{
                `vector.dimensions`: {NEO4J_VECTOR_DIMENSION},
                `vector.similarity_function`: 'cosine'
            }}
        }}
        """
        with self.driver.session() as s:
            try: s.run(q)
            except Exception as e: logger.warning(f"Vector index: {e}")
        logger.info("Vector index ready")

    def clear(self):
        with self.driver.session() as s:
            s.run("MATCH (n) DETACH DELETE n")
        logger.info("Graph cleared")

    # ── Load chunks ────────────────────────────────────────────────────────────

    def load_chunks(self, chunks: list[dict], embeddings: dict):
        count = skip = 0
        with self.driver.session() as s:
            for chunk in chunks:
                cid  = chunk.get("chunk_id")
                if not cid: skip += 1; continue
                emb  = embeddings.get(cid)
                props = san_props({
                    "id":            cid,
                    "text":          chunk.get("text",""),
                    "section_title": chunk.get("section_title",""),
                    "ata":           chunk.get("ata",""),
                    "page_start":    chunk.get("page_start"),
                    "page_end":      chunk.get("page_end"),
                    "word_count":    chunk.get("word_count"),
                    "global_seq":    chunk.get("global_seq"),
                    "section_id":    chunk.get("section_id",""),
                })
                if emb:
                    props["embedding"] = emb
                try:
                    s.run("MERGE (n:Chunk {id:$id}) SET n += $props",
                          id=cid, props=props)
                    count += 1
                except Exception as e:
                    logger.warning(f"Chunk {cid}: {e}"); skip += 1

        # ADJACENT_TO edges between consecutive chunks
        seq_sorted = sorted(chunks, key=lambda c: c.get("global_seq", 0))
        with self.driver.session() as s:
            for i in range(len(seq_sorted) - 1):
                a = seq_sorted[i].get("chunk_id")
                b = seq_sorted[i+1].get("chunk_id")
                if a and b:
                    try:
                        s.run("""
                        MATCH (a:Chunk {id:$a}), (b:Chunk {id:$b})
                        MERGE (a)-[:ADJACENT_TO]->(b)
                        """, a=a, b=b)
                    except Exception: pass

        logger.info(f"Chunks: {count} loaded, {skip} skipped")

    # ── Load entities ──────────────────────────────────────────────────────────

    def load_entities(self, entities: list[dict], embeddings: dict):
        # Map entity type → Neo4j label
        type_label = {
            "Component":   "Component",
            "System":      "System",
            "Tool":        "Tool",
            "Warning":     "Warning",
            "Step":        "Step",
            "Requirement": "Requirement",
            "Measurement": "Measurement",
        }
        count = skip = 0
        with self.driver.session() as s:
            for ent in entities:
                eid    = ent.get("id","").strip()
                etype  = ent.get("type","")
                label  = type_label.get(etype, "Entity")
                if not eid: skip += 1; continue

                props = san_props({k: v for k, v in ent.items()
                                   if k not in ("type","source_chunks")})
                props["id"] = eid
                # Add source_chunks as comma-separated string
                sc = ent.get("source_chunks",[])
                if sc: props["source_chunks"] = ",".join(sc[:10])

                emb = embeddings.get(eid)
                if emb: props["embedding"] = emb

                try:
                    s.run(f"MERGE (n:{label} {{id:$id}}) SET n += $props",
                          id=eid, props=props)
                    count += 1
                except Exception as e:
                    logger.warning(f"Entity {eid}: {e}"); skip += 1

        logger.info(f"Entities: {count} loaded, {skip} skipped")

    # ── Load relationships ─────────────────────────────────────────────────────

    def load_relationships(self, rels: list[dict]):
        count = skip = 0
        with self.driver.session() as s:
            for rel in rels:
                src   = rel.get("source","").strip()
                tgt   = rel.get("target","").strip()
                rtype = (rel.get("type","CONNECTED_TO")
                         .upper().replace(" ","_").replace("-","_"))
                if not src or not tgt: skip += 1; continue
                try:
                    s.run(f"""
                    MATCH (a {{id:$src}})
                    MATCH (b {{id:$tgt}})
                    MERGE (a)-[:{rtype}]->(b)
                    """, src=src, tgt=tgt)
                    count += 1
                except Exception as e:
                    logger.warning(f"Rel {src}→{tgt}: {e}"); skip += 1

        logger.info(f"Relationships: {count} loaded, {skip} skipped")

    # ── CONTAINS edges: Chunk → entities found in that chunk ──────────────────

    def load_chunk_entity_edges(self, entities: list[dict]):
        """Create CONTAINS edges from each Chunk to the entities sourced from it."""
        count = 0
        with self.driver.session() as s:
            for ent in entities:
                eid    = ent.get("id","").strip()
                chunks = ent.get("source_chunks","")
                if isinstance(chunks, str):
                    chunks = [c for c in chunks.split(",") if c]
                for cid in chunks:
                    try:
                        s.run("""
                        MATCH (c:Chunk {id:$cid}), (e {id:$eid})
                        MERGE (c)-[:CONTAINS]->(e)
                        """, cid=cid.strip(), eid=eid)
                        count += 1
                    except Exception: pass
        logger.info(f"CONTAINS edges: {count}")

    # ── DocumentSection hierarchy ──────────────────────────────────────────────

    def load_sections(self, chunks: list[dict]):
        """Create DocumentSection nodes and PART_OF hierarchy from chunk metadata."""
        sections: dict[str, dict] = {}
        for chunk in chunks:
            sid = chunk.get("section_id","")
            if sid and sid not in sections:
                sections[sid] = {
                    "id":    sid,
                    "title": chunk.get("section_title",""),
                    "ata":   chunk.get("ata",""),
                    "level": chunk.get("level", 1),
                }

        with self.driver.session() as s:
            for sec in sections.values():
                s.run("MERGE (n:DocumentSection {id:$id}) SET n += $props",
                      id=sec["id"], props=san_props(sec))

            # Link chunks to their sections
            for chunk in chunks:
                cid = chunk.get("chunk_id")
                sid = chunk.get("section_id")
                if cid and sid:
                    try:
                        s.run("""
                        MATCH (c:Chunk {id:$cid}), (s:DocumentSection {id:$sid})
                        MERGE (c)-[:PART_OF_SECTION]->(s)
                        """, cid=cid, sid=sid)
                    except Exception: pass

        logger.info(f"DocumentSections: {len(sections)}")

    # ── Stats ──────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        with self.driver.session() as s:
            nodes = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            rels  = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        return {"nodes": nodes, "relationships": rels}

    # ── Search interface (used by retriever) ───────────────────────────────────

    def keyword_search(self, query: str, limit: int = 10) -> list[dict]:
        q = """
        CALL db.index.fulltext.queryNodes('aircraftFulltext', $q)
        YIELD node, score
        WHERE score > 0.3
        RETURN node.id AS id, labels(node) AS labels,
               coalesce(node.name, node.title, node.id) AS name, score
        ORDER BY score DESC LIMIT $limit
        """
        with self.driver.session() as s:
            return s.run(q, q=query, limit=limit).data()

    def vector_search(self, embedding: list[float], limit: int = 5) -> list[dict]:
        """Semantic similarity search over Chunk nodes."""
        q = f"""
        CALL db.index.vector.queryNodes('{NEO4J_VECTOR_INDEX}', $limit, $emb)
        YIELD node, score
        WHERE score > 0.3
        RETURN node.id AS id, node.text AS text,
               node.section_title AS section_title,
               node.ata AS ata, score
        ORDER BY score DESC
        """
        with self.driver.session() as s:
            return s.run(q, emb=embedding, limit=limit).data()

    def get_context(self, entity_id: str, hops: int = 2) -> dict:
        q = f"""
        MATCH (root {{id:$eid}})
        OPTIONAL MATCH path = (root)-[*1..{hops}]-(related)
        WHERE NOT related:Chunk
        RETURN root,
               collect(DISTINCT related) AS related_nodes,
               collect(DISTINCT path) AS paths
        """
        with self.driver.session() as s:
            result = s.run(q, eid=entity_id).single()
        if not result:
            return {"node": {}, "related": [], "rels": []}

        root = dict(result["root"])
        root["labels"] = list(result["root"].labels)

        related = []
        for node in result["related_nodes"]:
            if node is None: continue
            item = dict(node)
            item["labels"] = list(node.labels)
            related.append(item)

        rels, seen = [], set()
        for path in result["paths"]:
            if path is None: continue
            for r in path.relationships:
                key = (r.start_node.get("id"), r.end_node.get("id"), r.type)
                if key not in seen:
                    seen.add(key)
                    rels.append({
                        "source": r.start_node.get("id"),
                        "target": r.end_node.get("id"),
                        "type":   r.type,
                    })
        return {"node": root, "related": related, "rels": rels}


# ── Main ──────────────────────────────────────────────────────────────────────

def build_graph():
    for f, name in [(CHUNKS_FILE,"chunks.json"),(ENTITIES_FILE,"entities.json"),
                    (EMBEDDINGS_FILE,"embeddings.json")]:
        if not f.exists():
            logger.error(f"{name} not found — run preceding steps first"); return

    with open(CHUNKS_FILE,    encoding="utf-8") as f: chunk_data  = json.load(f)
    with open(ENTITIES_FILE,  encoding="utf-8") as f: entity_data = json.load(f)
    with open(EMBEDDINGS_FILE,encoding="utf-8") as f: embeddings  = json.load(f)

    chunks    = chunk_data.get("chunks", [])
    entities  = entity_data.get("entities", [])
    rels      = entity_data.get("relationships", [])

    logger.info(f"Input: {len(chunks)} chunks, {len(entities)} entities, {len(rels)} rels")

    builder = GraphBuilder()
    try:
        builder.create_constraints()
        builder.create_vector_index()
        builder.clear()

        builder.load_sections(chunks)
        builder.load_chunks(chunks, embeddings)
        builder.load_entities(entities, embeddings)
        builder.load_relationships(rels)
        builder.load_chunk_entity_edges(entities)

        stats = builder.stats()
        logger.info(f"Graph complete: {stats['nodes']} nodes, {stats['relationships']} relationships")
        return stats
    except Exception as e:
        logger.exception(f"Build failed: {e}"); raise
    finally:
        builder.close()


if __name__ == "__main__":
    build_graph()
