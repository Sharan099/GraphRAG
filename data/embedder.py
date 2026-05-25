"""
data/embedder.py — Step 3

Generate 384-dimensional embeddings for every chunk and entity description.
Uses sentence-transformers (free, local, CPU-friendly).

Why dual embedding (chunks + entities)
---------------------------------------
- Chunk embeddings: semantic search over raw manual text. When graph
  traversal finds no matching entities, vector search always returns
  something relevant. This is what prevents empty retrieval.
- Entity embeddings: find semantically similar entities even when the
  query wording differs (e.g. "hydraulic actuator" matches "actuator (hydraulic)").

Output: data/embeddings.json  →  {chunk_id: [0.1, 0.2, ...], entity_id: [...]}
"""

import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)
def p(msg): print(msg, flush=True)

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    DATA_DIR, CHUNKS_FILE, ENTITIES_FILE, EMBEDDINGS_FILE,
    EMBEDDING_MODEL, EMBEDDING_BATCH,
)


def load_model():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        p("ERROR: pip install sentence-transformers"); sys.exit(1)
    p(f"Loading embedding model: {EMBEDDING_MODEL} ...")
    model = SentenceTransformer(EMBEDDING_MODEL)
    p(f"  Embedding dimension: {model.get_sentence_embedding_dimension()}")
    return model


def encode_in_batches(model, texts: list[str], batch_size: int = EMBEDDING_BATCH) -> list[list[float]]:
    """Encode a list of texts in batches. Returns list of embedding vectors."""
    all_embeddings = []
    total = len(texts)
    for i in range(0, total, batch_size):
        batch = texts[i: i + batch_size]
        vecs  = model.encode(batch, show_progress_bar=False, convert_to_numpy=True)
        all_embeddings.extend(vecs.tolist())
        if (i // batch_size + 1) % 5 == 0 or i + batch_size >= total:
            p(f"  Encoded {min(i+batch_size, total)}/{total}")
    return all_embeddings


def main():
    # Load chunks
    if not CHUNKS_FILE.exists():
        p(f"ERROR: {CHUNKS_FILE} not found — run chunker.py first"); sys.exit(1)
    with open(CHUNKS_FILE, encoding="utf-8") as f:
        chunk_data = json.load(f)
    chunks = chunk_data.get("chunks", [])
    p(f"Chunks loaded: {len(chunks)}")

    # Load entities
    if not ENTITIES_FILE.exists():
        p(f"ERROR: {ENTITIES_FILE} not found — run extractor.py first"); sys.exit(1)
    with open(ENTITIES_FILE, encoding="utf-8") as f:
        entity_data = json.load(f)
    entities = entity_data.get("entities", [])
    p(f"Entities loaded: {len(entities)}")

    # Load model
    model = load_model()

    embeddings: dict[str, list[float]] = {}

    # ── Embed chunks ──────────────────────────────────────────────────────────
    p(f"\nEmbedding {len(chunks)} chunks...")
    chunk_ids   = [c["chunk_id"] for c in chunks]
    chunk_texts = [
        f"[ATA {c.get('ata','00')}] {c.get('section_title','')}\n{c.get('text','')}"
        for c in chunks
    ]
    chunk_vecs = encode_in_batches(model, chunk_texts)
    for cid, vec in zip(chunk_ids, chunk_vecs):
        embeddings[cid] = vec

    # ── Embed entities ────────────────────────────────────────────────────────
    p(f"\nEmbedding {len(entities)} entities...")
    ent_ids, ent_texts = [], []
    for ent in entities:
        eid  = ent.get("id","")
        if not eid: continue
        # Build rich text for embedding: type + name + description/text
        name = ent.get("name","") or ent.get("text","") or eid
        desc = ent.get("description","") or ent.get("text","") or ""
        ata  = ent.get("ata","")
        sys_ = ent.get("system","")
        text = f"[{ent.get('type','')} ATA-{ata}] {name}. {desc} {sys_}".strip()
        ent_ids.append(eid)
        ent_texts.append(text)

    if ent_texts:
        ent_vecs = encode_in_batches(model, ent_texts)
        for eid, vec in zip(ent_ids, ent_vecs):
            embeddings[eid] = vec

    # Save
    with open(EMBEDDINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(embeddings, f, ensure_ascii=False)

    p(f"\n=== Embedding complete ===")
    p(f"  Total vectors : {len(embeddings)}")
    p(f"  Chunk vectors : {len(chunk_ids)}")
    p(f"  Entity vectors: {len(ent_ids)}")
    p(f"  Saved → {EMBEDDINGS_FILE}")
    p("Next: python graph/builder.py")


if __name__ == "__main__":
    main()
