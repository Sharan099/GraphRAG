# ──────────────────────────────────────────────────────────────────────────────
# AirGraph Assist — Backend (FastAPI / GraphRAG)
# Single-stage image tuned for Railway. Builds small and starts fast:
#   • CPU-only PyTorch (sentence-transformers otherwise pulls the ~2GB CUDA build)
#   • Embedding model baked in at build time (no HF download / rate-limit at runtime)
#   • Honors Railway's injected $PORT
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.11.9-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/app/.cache/huggingface \
    PORT=8000

WORKDIR /app

# curl is handy for debugging container health from the Railway shell.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install CPU-only PyTorch first so sentence-transformers does not drag in the
# enormous CUDA wheel. This is the single biggest image-size / build-time win.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Python dependencies (own layer → cached unless requirements.txt changes).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model so the first /api/query is fast and the
# container never depends on the Hugging Face Hub being reachable at runtime.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Application code + committed graph artefacts (data/*.json).
COPY . .

EXPOSE 8000

# Liveness probe (Railway also has its own healthcheck via railway.json).
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/api/health" || exit 1

# Shell form so ${PORT} expands at runtime (Railway sets PORT dynamically).
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
