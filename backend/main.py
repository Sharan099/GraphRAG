"""
main.py — AirGraph Assist API (FastAPI)

Exposes the GraphRAG pipeline as a small REST API so the Next.js frontend
(deployed on Vercel) can talk to this backend (deployed on Railway).

Endpoints
  GET  /                 → service banner
  GET  /api/health       → liveness + pipeline status
  GET  /api/meta         → model + method metadata and sample questions
  POST /api/query        → run a maintenance question through the pipeline
"""

import os
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from loguru import logger

from config import LLM_MODEL

# ──────────────────────────────────────────────────────────────────────────────
# App + CORS
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AirGraph Assist API",
    description="GraphRAG over the Aquila AT01 (A210) aircraft maintenance manual.",
    version="1.0.0",
)

# Comma-separated list of allowed origins, e.g.
#   ALLOWED_ORIGINS="https://airgraph.vercel.app,http://localhost:3000"
# Defaults to "*" so a fresh deploy works before you lock it down.
_origins_env = os.getenv("ALLOWED_ORIGINS", "*").strip()
allow_origins = ["*"] if _origins_env in ("", "*") else [
    o.strip() for o in _origins_env.split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────────────────────────────────────
# Lazy pipeline singleton — never crash the process on a bad Neo4j / API key.
# ──────────────────────────────────────────────────────────────────────────────

_pipeline = None
_pipeline_error = ""


def _get_pipeline():
    """Build the pipeline on first use; cache the error if it fails."""
    global _pipeline, _pipeline_error
    if _pipeline is not None:
        return _pipeline
    try:
        from pipeline import get_pipeline
        _pipeline = get_pipeline()
        _pipeline_error = ""
    except Exception as exc:  # noqa: BLE001
        _pipeline = None
        _pipeline_error = str(exc)
        logger.exception("Pipeline initialisation failed")
    return _pipeline


# ──────────────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)


class QueryResponse(BaseModel):
    answer: str
    entities: list = []
    graph_viz: dict = {}
    timing: dict = {}
    error: str = ""


SAMPLE_QUESTIONS = [
    "What are the torque specifications and warnings for the oil filter?",
    "What tools are required before starting the engine oil servicing task?",
    "Which maintenance step comes immediately after draining engine oil?",
    "List all safety warnings that apply before fuel system maintenance.",
    "What airworthiness or inspection interval requirements are mentioned for engine servicing?",
]


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "service": "AirGraph Assist API",
        "status": "ok",
        "docs": "/docs",
    }


@app.get("/api/health")
def health():
    pipeline = _get_pipeline()
    return {
        "status": "ok" if pipeline is not None else "degraded",
        "pipeline_ready": pipeline is not None,
        "llm_ready": bool(pipeline and pipeline.llm is not None),
        "error": _pipeline_error,
        "model": LLM_MODEL,
    }


@app.get("/api/meta")
def meta():
    return {
        "model": LLM_MODEL,
        "method": "Hybrid GraphRAG (Graph + Vector + BM25 + Community)",
        "architecture": "Neo4j + FastAPI + Qwen 3 32B (Groq)",
        "sample_questions": SAMPLE_QUESTIONS,
    }


@app.post("/api/query", response_model=QueryResponse)
def run_query(req: QueryRequest):
    pipeline = _get_pipeline()
    if pipeline is None:
        return QueryResponse(
            answer="The backend pipeline is not available. Check Neo4j and API "
                   "credentials on the server.",
            error=_pipeline_error or "pipeline_unavailable",
        )

    started = time.time()
    try:
        result = pipeline.query(req.query)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Query failed")
        return QueryResponse(
            answer=f"Error while answering: {exc}",
            error=str(exc),
            timing={"total_ms": round((time.time() - started) * 1000, 1)},
        )

    return QueryResponse(
        answer=result.get("answer", "No answer was returned."),
        entities=result.get("entities", []) or [],
        graph_viz=result.get("graph_viz", {}) or {},
        timing=result.get("timing", {}) or {},
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
