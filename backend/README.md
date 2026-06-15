# AirGraph Assist — Backend (FastAPI)

GraphRAG API over the Aquila AT01 (A210) maintenance manual. Deployed to **Railway**.

## Stack

- **FastAPI** + Uvicorn — REST API
- **Neo4j** — knowledge graph (use [Neo4j Aura](https://neo4j.com/cloud/aura/) free tier in the cloud)
- **Anthropic Claude** — answer generation
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

See `.env.example`. The important ones:

- `ANTHROPIC_API_KEY` — required for answers
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

## Deploy to Railway

1. Push this repo to GitHub.
2. On [railway.app](https://railway.app) → **New Project → Deploy from GitHub repo**.
3. Set the **Root Directory** to `backend`.
4. Add the environment variables from `.env.example`.
5. Railway auto-detects Python and runs the `Procfile` start command.

## Evaluation

```bash
python evaluation/run_evaluation.py
pytest -q
```
