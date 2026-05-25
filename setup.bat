@echo off
REM ============================================================
REM  AirGraph Assist — Windows Setup Script
REM  Run from Git Bash: bash setup.bat
REM  OR double-click in Windows Explorer
REM ============================================================

echo.
echo ==============================================
echo   AirGraph Assist — Windows Setup
echo   Estimated time: 15-20 minutes
echo ==============================================

REM ── Step 1: Python packages (pre-built wheels only) ─────────
echo.
echo [1/5] Installing Python dependencies...
pip install --only-binary=:all: pandas numpy
pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo ERROR: pip install failed. See above.
    pause
    exit /b 1
)
echo     Done.

REM ── Step 2: Check Docker ────────────────────────────────────
echo.
echo [2/5] Starting Neo4j via Docker...
docker --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Docker not found.
    echo Install Docker Desktop from https://www.docker.com/products/docker-desktop
    pause
    exit /b 1
)

REM Stop existing container if running
docker stop airgraph-neo4j >nul 2>&1
docker rm   airgraph-neo4j >nul 2>&1

docker run -d ^
  --name airgraph-neo4j ^
  -p 7474:7474 ^
  -p 7687:7687 ^
  -e NEO4J_AUTH=neo4j/airbus2024 ^
  -e NEO4J_dbms_memory_heap_max__size=1G ^
  neo4j:5.19.0

echo     Waiting 30 seconds for Neo4j to start...
timeout /t 30 /nobreak >nul
echo     Neo4j ready.

REM ── Step 3: Ollama ──────────────────────────────────────────
echo.
echo [3/5] Setting up Ollama...
ollama --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Ollama not found. Download from https://ollama.ai/download
    echo After installing, re-run this script.
    start https://ollama.ai/download
    pause
    exit /b 1
)

echo     Pulling Mistral 7B Q4 model (4 GB — takes 5-10 min)...
echo     Tip: use tinyllama for testing on slow machines
ollama pull mistral:7b-instruct-q4_0
if %ERRORLEVEL% neq 0 (
    echo     Mistral failed, trying tinyllama fallback...
    ollama pull tinyllama
    python -c "import re; content=open('config.py').read(); open('config.py','w').write(content.replace('mistral:7b-instruct-q4_0','tinyllama'))"
)

REM ── Step 4: Build data pipeline ─────────────────────────────
echo.
echo [4/5] Building data pipeline...

python -m data.synthetic_data
if %ERRORLEVEL% neq 0 ( echo ERROR in synthetic_data.py & pause & exit /b 1 )

python -m graph.neo4j_builder
if %ERRORLEVEL% neq 0 ( echo ERROR in neo4j_builder.py & pause & exit /b 1 )

python -m retrieval.vector_store
if %ERRORLEVEL% neq 0 ( echo ERROR in vector_store.py & pause & exit /b 1 )

REM ── Step 5: Smoke test ──────────────────────────────────────
echo.
echo [5/5] Running smoke test...
python -c "from pipeline import query; r=query('What tools for HPU-22?'); print('OK — latency:', r['timing']['total_ms'], 'ms')"

echo.
echo ==============================================
echo   Setup complete!
echo.
echo   Start the app:
echo     streamlit run app.py
echo.
echo   Neo4j browser:
echo     http://localhost:7474
echo     User: neo4j   Password: airbus2024
echo ==============================================
pause
