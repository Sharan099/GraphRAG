"""
config.py — AirGraph Assist
Single source of truth for every setting across all 9 pipeline files.
"""

import os
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent
DATA_DIR      = BASE_DIR / "data"
CACHE_DIR     = DATA_DIR / ".cache"

# Pipeline artefact files (produced in order)
CHUNKS_FILE      = DATA_DIR / "chunks.json"          # Step 1 output
ENTITIES_FILE    = DATA_DIR / "entities.json"         # Step 2 output
EMBEDDINGS_FILE  = DATA_DIR / "embeddings.json"       # Step 3 output
COMMUNITY_FILE   = DATA_DIR / "communities.json"      # Step 5 output

# ── Neo4j ──────────────────────────────────────────────────────────────────────
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "airbus2024")
NEO4J_TIMEOUT  = 30

# Vector index — must match embedding dimension below
NEO4J_VECTOR_INDEX     = "chunk_vector_index"
NEO4J_VECTOR_DIMENSION = 384        # all-MiniLM-L6-v2 output dimension

# ── Step 1 — Chunking ──────────────────────────────────────────────────────────
CHUNK_SIZE    = 512     # target words per chunk  (≈ 2048 chars ≈ 512 tokens)
CHUNK_OVERLAP = 100     # overlap words between consecutive chunks
MIN_CHUNK_LEN = 80      # discard chunks shorter than this (words)

# ── Step 2 — Entity extraction ─────────────────────────────────────────────────
EXTRACTION_MODEL     = "claude-haiku-4-5-20251001"
EXTRACTION_MAX_TOKENS = 8192      # max for Haiku — eliminates truncation on dense chunks
BATCH_ID_FILE        = DATA_DIR / ".batch_id"
PROGRESS_FILE        = DATA_DIR / ".seq_progress.json"

# ── Step 3 — Embeddings ────────────────────────────────────────────────────────
EMBEDDING_MODEL = "all-MiniLM-L6-v2"   # free, local, 384-dim, fast on CPU
# Batch size for encoding — keep low on 8GB RAM
EMBEDDING_BATCH = 32

# ── Step 4 — Graph ─────────────────────────────────────────────────────────────
MAX_GRAPH_NODES         = 50
MAX_GRAPH_RELATIONSHIPS = 80

# ── Step 5 — Community detection ──────────────────────────────────────────────
COMMUNITY_RESOLUTION      = 1.0    # Louvain resolution (higher = more communities)
COMMUNITY_MIN_SIZE        = 3      # skip communities smaller than this
COMMUNITY_SUMMARY_MODEL   = "claude-haiku-4-5-20251001"
COMMUNITY_SUMMARY_TOKENS  = 512

# ── Step 6 — Retrieval ─────────────────────────────────────────────────────────
TOP_K_GRAPH_HOPS    = 2
TOP_K_VECTOR        = 5     # top chunks from vector search
TOP_K_BM25          = 4     # top chunks from BM25
TOP_K_COMMUNITY     = 2     # top community summaries
MAX_CONTEXT_TOKENS  = 3000
VECTOR_SCORE_MIN    = 0.35  # discard very low similarity results

# ── Claude API (answers) ───────────────────────────────────────────────────────
# claude-haiku-4-5-20251001  → fast (2-3s), cheap  ← default
# claude-sonnet-4-6          → better quality (4-6s), more expensive
CLAUDE_MODEL       = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
LLM_MAX_TOKENS     = 800
LLM_TEMPERATURE    = 0.0

# ── System prompt ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are an expert aerospace maintenance assistant for the Aquila AT01 (A210) aircraft.\n"
    "Answer using ONLY the provided context. Never invent facts, part numbers, or procedures.\n\n"
    "Structure your answer:\n"
    "1. SAFETY (list any WARNING or CAUTION that applies — always first)\n"
    "2. ANSWER (step-by-step if the question asks about a procedure)\n"
    "3. SOURCE (state: Graph Context / Manual Chunk / Community Summary)\n\n"
    "If the context is insufficient, reply exactly:\n"
    "'Information not found in technical documentation.'"
)

# ── ATA chapter reference ──────────────────────────────────────────────────────
ATA_CHAPTERS = {
    "00": "General",        "05": "Time Limits",
    "06": "Dimensions",     "07": "Lifting / Shoring",
    "08": "Levelling",      "09": "Towing",
    "10": "Parking",        "11": "Placards",
    "12": "Servicing",      "20": "Standard Practices",
    "21": "Air Conditioning","22": "Auto Flight",
    "23": "Communications", "24": "Electrical Power",
    "25": "Equipment",      "26": "Fire Protection",
    "27": "Flight Controls","28": "Fuel",
    "29": "Hydraulic",      "30": "Ice Protection",
    "31": "Instruments",    "32": "Landing Gear",
    "33": "Lights",         "34": "Navigation",
    "35": "Oxygen",         "36": "Pneumatic",
    "51": "Structures",     "52": "Doors",
    "53": "Fuselage",       "54": "Nacelles",
    "55": "Stabilisers",    "56": "Windows",
    "57": "Wings",          "61": "Propeller",
    "71": "Power Plant",    "72": "Engine",
    "73": "Engine Fuel",    "74": "Ignition",
    "75": "Air",            "76": "Engine Controls",
    "77": "Engine Indicating","78": "Exhaust",
    "79": "Oil",            "80": "Starting",
}

# ── Node type priority for retrieval ranking ───────────────────────────────────
NODE_PRIORITY = {
    "Warning":         1.00,
    "Requirement":     0.97,
    "Defect":          0.90,
    "Step":            0.87,
    "Component":       0.80,
    "System":          0.75,
    "Measurement":     0.72,
    "Tool":            0.65,
    "Chunk":           0.50,
    "Community":       0.60,
}