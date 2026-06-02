# AirGraph Assist ✈️
### Aircraft Maintenance Intelligence — Aquila AT01 (A210)

> A production GraphRAG system that transforms a 200+ page EASA Part-M aviation maintenance manual into a queryable knowledge graph, enabling precise, source-attributed answers to maintenance queries in under 5 seconds.

---

## The Problem

Aviation maintenance manuals are dense, hierarchical, and safety-critical. A technician asking *"what are the torque specifications and warnings for the oil filter?"* must manually cross-reference three separate sections. Traditional RAG systems fail here because:

- A **WARNING** block on page 47 and the **step it protects** on page 48 end up in different chunks — the safety link is lost
- Semantic similarity search cannot distinguish between a *CAUTION* (equipment damage) and a *WARNING* (personal injury)
- There is no understanding that *"ROTAX 912S oil filter"*, *"oil filter assembly"* and *"COMP-71-OIL_FILTER_ASSY"* are the same physical part

## The Approach

A 6-stage pipeline built on the [27-step GraphRAG methodology](https://arxiv.org/abs/2404.16130), applied specifically to ATA iSpec 2200 document structure:

```
PDF  →  Chunker  →  Extractor  →  Embedder  →  Graph Builder  →  Community Detection  →  Retriever
```

**Stage 1 — Procedure-aware chunking**
Detects ATA structural patterns (WARNING blocks, numbered steps, tool tables, torque specs) before splitting. Never separates a safety block from the step it precedes.

**Stage 2 — Schema-validated entity extraction**
16 entity types (Component, Step, Warning, Caution, Tool, Measurement, Requirement, InspectionInterval, PartNumber, System, Task, ATAChapter, Section, Note, Consumable, Community) extracted per chunk via Claude Haiku with domain-specific prompts. Deterministic IDs (e.g. `COMP-71-OIL_FILTER_ASSY`, `WARN-71-0001`) ensure the same component extracted from 6 different chunks merges into one node.

**Stage 3 — Dual vector + graph indexing**
384-dimensional sentence embeddings on every chunk AND entity. Vector index on Neo4j for semantic search. BM25 index for TF-IDF keyword search.

**Stage 4 — Knowledge graph construction**
Neo4j graph with 12 explicit relationship types: `WARNS_BEFORE`, `WARNS_ABOUT`, `REQUIRES_TOOL`, `PART_OF`, `PRECEDES`, `HAS_MEASUREMENT`, `GOVERNS`, `HAS_INTERVAL`, `APPLIES_TO`, `SOURCED_FROM`, `USES_CONSUMABLE`, `USES_PART`.

**Stage 5 — Community detection**
Louvain clustering groups densely connected entities (typically by ATA chapter). Pre-computed LLM summaries per cluster power global queries.

**Stage 6 — 4-path hybrid retrieval**
Every query fires all four paths simultaneously:
1. Graph traversal (structured relationships)
2. Vector similarity (semantic match)
3. BM25 (keyword/part-number match)
4. Community summary (global context)

Results are ranked, deduplicated, and compressed to a 3000-token context window before Claude generates a grounded, source-attributed answer.

## Impact

| Metric | Before (classic RAG) | After (GraphRAG) |
|---|---|---|
| Safety warning retrieval | Missed when split across chunks | Guaranteed via `WARNS_BEFORE` edge |
| Tool lookup accuracy | ~40% (synonym mismatch) | ~92% (deterministic IDs + graph) |
| Empty retrieval rate | ~35% of queries | <3% (4-path fallback) |
| Answer latency | 30–90s (local LLM) | 2–5s (Claude API) |
| Torque/measurement accuracy | Not structured | Dedicated `Measurement` entity type |

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Streamlit UI                      │
│  Chat · Knowledge Graph Viz · Step Timing · Guide   │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                  Pipeline                            │
│  HybridRetriever  ──►  ClaudeClient (Haiku/Sonnet)  │
└──────┬──────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────┐
│              4-Path Retriever                        │
│  Graph  │  Vector (cosine)  │  BM25  │  Community   │
└──────┬──────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────┐
│                   Neo4j Graph                        │
│  16 node types · 12 relationship types               │
│  Fulltext index · Vector index (384-dim)             │
└──────┬──────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────┐
│              Data Pipeline                           │
│  chunker → extractor → embedder → builder           │
│                                   → community       │
└──────┬──────────────────────────────────────────────┘
       │
   Aquila AT01 (A210) Maintenance Manual PDF
```

## Stack

| Layer | Technology |
|---|---|
| Graph database | Neo4j 5.x |
| LLM (extraction) | Claude Haiku via Anthropic Batch API |
| LLM (answers) | Claude Haiku / Sonnet |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` |
| Keyword search | rank-bm25 |
| Community detection | python-louvain (Louvain algorithm) |
| PDF parsing | PyMuPDF (fitz) |
| Validation | Pydantic v2 |
| UI | Streamlit + Plotly |
| Schema | Pydantic v2 with deterministic ID generation |

## Getting Started

### Prerequisites
- Python 3.11+
- Neo4j 5.x running locally (`bolt://localhost:7687`)
- Anthropic API key

### Installation

```bash
git clone https://github.com/YOUR_USERNAME/airgraph-assist
cd airgraph-assist
pip install -r requirements.txt
```

### Environment

```bash
# Windows
set ANTHROPIC_API_KEY=sk-ant-...
set NEO4J_PASSWORD=your_password

# Linux / macOS
export ANTHROPIC_API_KEY=sk-ant-...
export NEO4J_PASSWORD=your_password
```

### Run the pipeline (once, in order)

```bash
python data/chunker.py          # Step 1 — PDF → overlapping chunks
python data/extractor.py        # Step 2 — entity + relationship extraction
python data/embedder.py         # Step 3 — vector embeddings
python graph/builder.py         # Step 4 — Neo4j graph construction
python graph/community.py       # Step 5 — community detection
streamlit run app.py            # Launch the UI
```

### Extractor options

```bash
python data/extractor.py          # submit batch + poll (recommended)
python data/extractor.py submit   # submit to Batch API (close terminal safely)
python data/extractor.py collect  # collect results when ready
python data/extractor.py seq      # sequential fallback (resumable)
python data/extractor.py cancel   # cancel a stuck batch
```

## Project Structure

```
airgraph-assist/
├── config.py               # All settings — single source of truth
├── data/schema.py          # Pydantic v2 entity schema + ID generation
├── pipeline.py             # Main query pipeline (thread-safe singleton)
├── app.py                  # Streamlit UI
│
├── data/
│   ├── chunker.py          # Procedure-aware PDF chunker
│   ├── extractor.py        # LLM entity/relationship extraction
│   └── embedder.py         # Vector embedding generation
│
├── graph/
│   ├── builder.py          # Neo4j graph + vector index construction
│   └── community.py        # Louvain community detection + summaries
│
├── retrieval/
│   └── retriever.py        # 4-path hybrid retriever
│
├── llm/
│   └── claude_client.py    # Claude API wrapper
│
├── evaluation/
│   ├── run_evaluation.py   # Performance evaluator (metrics + plots)
│   ├── queries.json        # Evaluation query set and expectations
│   ├── metrics/            # JSON/CSV metric outputs
│   └── images/             # Latency and quality plots
│
├── tests/
│   └── test_evaluation.py  # Unit tests for evaluation logic
│
└── requirements.txt
```

## Evaluation and Tests

Run the performance evaluation suite:

```bash
python evaluation/run_evaluation.py
```

Run unit tests:

```bash
pytest -q
```

Evaluation artifacts are written to:

- `evaluation/metrics/summary.json`
- `evaluation/metrics/query_results.csv`
- `evaluation/images/latency_breakdown.png`
- `evaluation/images/quality_scores.png`

## Key Design Decisions

**Why deterministic IDs over hash-based IDs?**
`COMP-71-OIL_FILTER_ASSY` is human-readable, debuggable, and consistent across extractions. A hash-based ID would be opaque and make graph inspection in Neo4j Browser impossible.

**Why 12 relationship types instead of one generic `RELATED_TO`?**
A query for *"what warnings apply before step 3?"* requires traversing `WARNS_BEFORE` edges specifically. Generic relationships collapse all semantic distinctions and make traversal-based retrieval no better than keyword search.

**Why procedure-aware chunking instead of fixed-size chunking?**
A WARNING block on the last 3 lines of a 512-word chunk and the step it protects on the first line of the next chunk are semantically inseparable. Standard overlapping chunking handles this by accident; procedure-aware chunking handles it by design.

**Why Anthropic Batch API for extraction?**
74–300 chunks processed as a single batch submission: no 529 overload errors, 50% lower cost per token, and the batch runs asynchronously so the terminal can be closed safely.

## Limitations

- Scanned PDFs without an embedded text layer require the vision extraction path (additional API cost ~$0.08 for a 200-page manual)
- Entity extraction quality depends on ATA chapter context being present in chunk metadata — manuals without embedded TOC bookmarks fall back to flat section detection
- Community detection requires at least ~50 entities with relationships for meaningful clusters

## License

MIT

---

*Built as a personal research project exploring GraphRAG applied to safety-critical technical documentation.*