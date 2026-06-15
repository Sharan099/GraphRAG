# AirGraph Assist — Backend (FastAPI)

GraphRAG API over the Aquila AT01 (A210) maintenance manual. Deployed to **Railway**.

## Stack

- **FastAPI** + Uvicorn — REST API
- **Neo4j** — knowledge graph (use [Neo4j Aura](https://neo4j.com/cloud/aura/) free tier in the cloud)
- **Qwen 3 32B on [Groq](https://console.groq.com/)** — answer generation (free, OpenAI-compatible API)
- Hybrid retrieval: Graph traversal + Vector + BM25 + Community summaries

## API

| Method | Path           | Description                          |
| ------ | -------------- | ------------------------------------ |
| GET    | `/api/health`  | Liveness + pipeline/LLM status       |
| GET    | `/api/meta`    | Model, method, sample questions      |
| POST   | `/api/query`   | `{ "query": "..." }` → answer + graph |

Interactive docs at `/docs`.

## Local development

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
copy .env.example .env          # then fill in your keys
uvicorn main:app --reload --port 8000
```

Open http://localhost:8000/docs to try it.

## Environment variables

Copy `.env.example` to `.env` and fill it in. The important ones:

- `GROQ_API_KEY` — required for answers ([get a free key](https://console.groq.com/keys))
- `GROQ_MODEL` — defaults to `qwen/qwen3-32b`
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` — graph database
- `ALLOWED_ORIGINS` — set to your Vercel URL in production
- `PORT` — provided automatically by Railway

## Rebuilding the knowledge graph (optional)

The committed `data/*.json` artefacts let the API run without re-running the
pipeline. To rebuild from the PDF:

```bash
python data/chunker.py
python data/extractor.py
python data/embedder.py
python graph/builder.py
python graph/community.py
```

## Deploy to Railway (Docker)

The backend ships with a `Dockerfile` and `railway.json` configured to build via
Docker — Railway uses them automatically.

1. Push this repo to GitHub.
2. On [railway.app](https://railway.app) → **New Project → Deploy from GitHub repo**.
3. Set the **Root Directory** to `backend` (so Railway finds the `Dockerfile`).
4. Add the environment variables from `.env.example` (at minimum `GROQ_API_KEY`
   and the `NEO4J_*` values). `PORT` is injected by Railway automatically.
5. Deploy. Railway builds the image and health-checks `/api/health`.

The image is optimized for fast cold starts: CPU-only PyTorch and the
`all-MiniLM-L6-v2` embedding model are baked in at build time, so the first
request doesn't wait on a model download.

### Run the container locally

```bash
cd backend
docker build -t airgraph-backend .
docker run --rm -p 8000:8000 --env-file .env airgraph-backend
```

Then open http://localhost:8000/docs. (Point `NEO4J_URI` at a reachable Neo4j —
e.g. Neo4j Aura — since `localhost` inside the container is the container itself.)

## Evaluation

```bash
python evaluation/run_evaluation.py
pytest -q
```

The evaluator now runs two paths:

- **GraphRAG**: graph traversal + vector + BM25 + community summaries.
- **Standard RAG baseline**: vector + BM25 only, using the same Claude answer generation.

Outputs:

- `evaluation/metrics/query_results.csv` — GraphRAG query-level results.
- `evaluation/metrics/standard_rag_results.csv` — baseline query-level results.
- `evaluation/metrics/comparison_results.csv` — combined rows for both systems.
- `evaluation/metrics/comparison_summary.json` — keyword-recall gain and latency delta.
- `evaluation/images/graphrag_vs_standard_rag.png` — visual baseline comparison.

Optional RAGAS metrics:

```bash
pip install -r requirements-eval.txt
python evaluation/run_evaluation.py
```

When `ragas` and evaluator credentials are available, the script writes
`ragas_graphrag.json` and `ragas_standard_rag.json` with faithfulness and answer
relevancy. Context precision is included when evaluation queries provide
reference answers.
