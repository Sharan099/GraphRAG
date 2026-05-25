#!/bin/bash
# setup.sh — works on Windows Git Bash, Mac, Linux
set -e

echo "=============================================="
echo "  AirGraph Assist — Setup Script"
echo "=============================================="

# ── Detect OS ──────────────────────────────────────────────
OS="linux"
case "$(uname -s)" in
  Darwin*) OS="mac" ;;
  MINGW*|MSYS*|CYGWIN*) OS="windows" ;;
esac
echo "Detected OS: $OS"

# ── Step 1: Python deps — pre-built wheels first ──────────
echo ""
echo "[1/5] Installing Python dependencies..."
pip install --only-binary=:all: "pandas>=2.0.3" "numpy>=1.24.0"
pip install -r requirements.txt
echo "    Done."

# ── Step 2: Neo4j via Docker ──────────────────────────────
echo ""
echo "[2/5] Starting Neo4j..."
if ! command -v docker &>/dev/null; then
  echo "ERROR: Docker not found."
  echo "  Windows: https://www.docker.com/products/docker-desktop"
  echo "  Mac:     brew install --cask docker"
  echo "  Linux:   sudo apt install docker.io"
  exit 1
fi

docker stop airgraph-neo4j 2>/dev/null || true
docker rm   airgraph-neo4j 2>/dev/null || true

docker run -d \
  --name airgraph-neo4j \
  -p 7474:7474 \
  -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/airbus2024 \
  -e NEO4J_dbms_memory_heap_max__size=1G \
  neo4j:5.19.0

echo "    Waiting 30s for Neo4j to start..."
sleep 30
echo "    Neo4j ready."

# ── Step 3: Ollama ────────────────────────────────────────
echo ""
echo "[3/5] Setting up Ollama..."
if ! command -v ollama &>/dev/null; then
  if [ "$OS" = "windows" ]; then
    echo "Download Ollama from https://ollama.ai/download and re-run."
    exit 1
  elif [ "$OS" = "mac" ]; then
    brew install ollama 2>/dev/null || curl -fsSL https://ollama.ai/install.sh | sh
  else
    curl -fsSL https://ollama.ai/install.sh | sh
  fi
fi

# Start ollama server in background
ollama serve &>/dev/null &
OLLAMA_PID=$!
sleep 5

echo "    Pulling model (choose based on your RAM):"
echo "      mistral:7b-instruct-q4_0  = 4GB RAM  — best quality"
echo "      tinyllama                  = 1GB RAM  — fastest"

if ollama pull mistral:7b-instruct-q4_0 2>/dev/null; then
  echo "    Using mistral:7b-instruct-q4_0"
else
  echo "    Falling back to tinyllama..."
  ollama pull tinyllama
  sed -i 's/mistral:7b-instruct-q4_0/tinyllama/' config.py
  echo "    config.py updated to use tinyllama"
fi

# ── Step 4: Build data pipeline ───────────────────────────
echo ""
echo "[4/5] Building data pipeline..."

python -m data.synthetic_data  && echo "    Synthetic data: OK"
python -m graph.neo4j_builder  && echo "    Neo4j graph:    OK"
python -m retrieval.vector_store && echo "    Vector index:   OK"

# ── Step 5: Smoke test ────────────────────────────────────
echo ""
echo "[5/5] Smoke test..."
python -c "
from pipeline import query
r = query('What tools do I need for HPU-22?')
print('  Response:', r['answer'][:80], '...')
print('  Latency: ', r['timing']['total_ms'], 'ms')
print('  Entities:', r['entities'])
" && echo "    Smoke test: PASS" || echo "    Smoke test failed — check Neo4j and Ollama are running"

echo ""
echo "=============================================="
echo "  Done! Start the app:"
echo "    streamlit run app.py"
echo ""
echo "  Neo4j browser: http://localhost:7474"
echo "  User: neo4j  Password: airbus2024"
echo "=============================================="