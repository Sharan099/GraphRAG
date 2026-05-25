import json
import threading
import time
from pathlib import Path
from loguru import logger

from graph.builder       import GraphBuilder
from retrieval.retriever import HybridRetriever
from llm.claude_client   import ClaudeClient


class AirGraphPipeline:

    def __init__(self):
        logger.info("Initialising AirGraph pipeline...")
        self.graph     = None
        self.retriever = None
        self.llm       = None

        try:
            self.graph     = GraphBuilder()
            self.retriever = HybridRetriever(self.graph)
            self.llm       = ClaudeClient()
        except Exception:
            if self.graph:
                try: self.graph.close()
                except Exception: pass
            logger.exception("Pipeline init failed")
            raise

        logger.info("Pipeline ready")

    def build_prompt(self, query: str, context: str) -> str:
        return (
            f"USER QUESTION: {query}\n\n"
            "==================================================\n"
            "RETRIEVED CONTEXT:\n"
            f"{context}\n\n"
            "==================================================\n"
            "ANSWER:"
        )

    def query(self, user_query: str) -> dict:
        t0 = time.time()
        try:
            result  = self.retriever.retrieve(user_query)
            context = result.get("context", "").strip()

            if not context:
                return {
                    "answer":    "No relevant information found in the maintenance documentation.",
                    "entities":  result.get("entities", []),
                    "graph_viz": result.get("graph_viz", {}),
                    "timing":    {**result.get("timing", {}),
                                  "total_ms": round((time.time()-t0)*1000, 1)},
                }

            llm_start  = time.time()
            raw_answer = self.llm.generate(self.build_prompt(user_query, context))
            answer     = (raw_answer or "").strip() or \
                         "Model returned an empty response."

            timing = {
                **result.get("timing", {}),
                "llm_generation_ms": round((time.time()-llm_start)*1000, 1),
                "total_ms":          round((time.time()-t0)*1000, 1),
            }
            return {
                "answer":    answer,
                "entities":  result.get("entities", []),
                "graph_viz": result.get("graph_viz", {}),
                "timing":    timing,
            }
        except Exception as e:
            logger.exception("Query failed")
            return {
                "answer":    f"Error: {e}",
                "timing":    {"total_ms": round((time.time()-t0)*1000, 1)},
                "entities":  [], "graph_viz": {},
            }


# ── Thread-safe singleton ─────────────────────────────────────────────────────

_pipeline: AirGraphPipeline | None = None
_lock     = threading.Lock()


def get_pipeline() -> AirGraphPipeline:
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    with _lock:
        if _pipeline is None:
            _pipeline = AirGraphPipeline()
    return _pipeline


def query(user_query: str) -> dict:
    return get_pipeline().query(user_query)
