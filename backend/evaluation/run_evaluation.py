import csv
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path
from statistics import mean, median
import sys

import matplotlib.pyplot as plt
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import get_pipeline, query as run_query
from config import (
    GROQ_MODEL, EMBEDDING_MODEL, LLM_TIMEOUT,
    RAGAS_JUDGE_MODEL, RAGAS_JUDGE_MAX_TOKENS,
)


EVAL_DIR = Path(__file__).parent
METRICS_DIR = EVAL_DIR / "metrics"
IMAGES_DIR = EVAL_DIR / "images"
QUERIES_FILE = EVAL_DIR / "queries.json"


def load_queries() -> list[dict]:
    with open(QUERIES_FILE, encoding="utf-8") as handle:
        return json.load(handle)


def keyword_recall(answer: str, expected_keywords: list[str]) -> float:
    if not expected_keywords:
        return 1.0
    answer_lower = (answer or "").lower()
    hits = sum(1 for kw in expected_keywords if kw.lower() in answer_lower)
    return round(hits / len(expected_keywords), 3)


def improvement_percent(baseline: float, candidate: float) -> float:
    """Relative improvement in percent; returns 0 when baseline has no headroom."""
    if baseline >= 1.0:
        return 0.0
    return round(((candidate - baseline) / (1.0 - baseline)) * 100, 1)


def _answer_with_pipeline(
    user_query: str,
    *,
    mode: str,
) -> dict:
    """
    Run either the production GraphRAG path or a standard RAG baseline.

    The baseline intentionally uses only vector + BM25 chunk retrieval and the
    same Claude generation path, isolating the value of graph traversal and
    community summaries.
    """
    if mode == "graphrag":
        return run_query(user_query)

    if mode != "standard_rag":
        raise ValueError(f"Unsupported evaluation mode: {mode}")

    pipeline = get_pipeline()
    started = time.time()
    retrieval = pipeline.retriever.retrieve_standard_rag(user_query)
    context = retrieval.get("context", "").strip()

    llm_started = time.time()
    if not context:
        answer = "No relevant information found in the maintenance documentation."
    elif pipeline.llm is None:
        answer = "LLM is unavailable. Returning retrieval context preview only.\n\n" + context[:1800]
    else:
        answer = pipeline.llm.generate(pipeline.build_prompt(user_query, context))

    timing = {
        **retrieval.get("timing", {}),
        "llm_generation_ms": round((time.time() - llm_started) * 1000, 1),
        "total_ms": round((time.time() - started) * 1000, 1),
    }

    return {
        "answer": answer,
        "entities": [],
        "graph_viz": {"nodes": [], "edges": []},
        "contexts": retrieval.get("contexts", []),
        "timing": timing,
    }


def evaluate_query(item: dict, *, mode: str = "graphrag") -> dict:
    started = time.perf_counter()
    error = ""
    answer = ""
    timing = {}
    entities_found = 0
    contexts: list[str] = []

    try:
        result = _answer_with_pipeline(item["query"], mode=mode)
        answer = result.get("answer", "")
        timing = result.get("timing", {}) or {}
        entities_found = len(result.get("entities", []) or [])
        contexts = result.get("contexts", []) or []
    except Exception as exc:
        error = str(exc)

    wall_ms = round((time.perf_counter() - started) * 1000, 1)
    total_ms = float(timing.get("total_ms", wall_ms))
    llm_ms = float(timing.get("llm_generation_ms", 0.0))
    recall = keyword_recall(answer, item.get("expected_keywords", []))

    return {
        "id": item.get("id", ""),
        "query": item["query"],
        "mode": mode,
        "total_ms": total_ms,
        "llm_generation_ms": llm_ms,
        "retrieval_ms": round(max(total_ms - llm_ms, 0.0), 1),
        "entities_found": entities_found,
        "answer_chars": len(answer or ""),
        "keyword_recall": recall,
        "answer": answer,
        "contexts_json": json.dumps(contexts, ensure_ascii=False),
        "reference_answer": item.get("reference_answer", ""),
        "error": error,
    }


def save_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def save_plots(rows: list[dict]) -> None:
    ids = [r["id"] for r in rows]
    totals = [r["total_ms"] for r in rows]
    retrieval = [r["retrieval_ms"] for r in rows]
    llm = [r["llm_generation_ms"] for r in rows]
    quality = [r["keyword_recall"] for r in rows]

    plt.figure(figsize=(10, 5))
    plt.bar(ids, retrieval, label="Retrieval (ms)")
    plt.bar(ids, llm, bottom=retrieval, label="LLM (ms)")
    plt.ylabel("Milliseconds")
    plt.title("AirGraph Assist Latency Breakdown")
    plt.legend()
    plt.tight_layout()
    plt.savefig(IMAGES_DIR / "latency_breakdown.png", dpi=180)
    plt.close()


def save_comparison_plot(graphrag_rows: list[dict], baseline_rows: list[dict]) -> None:
    ids = [r["id"] for r in graphrag_rows]
    graphrag_quality = [r["keyword_recall"] for r in graphrag_rows]
    baseline_quality = [r["keyword_recall"] for r in baseline_rows]

    x = range(len(ids))
    width = 0.36

    plt.figure(figsize=(10, 4))
    plt.bar([i - width / 2 for i in x], baseline_quality, width=width, label="Standard RAG")
    plt.bar([i + width / 2 for i in x], graphrag_quality, width=width, label="GraphRAG")
    plt.xticks(list(x), ids)
    plt.ylim(0, 1.05)
    plt.ylabel("Keyword recall")
    plt.title("GraphRAG vs Standard RAG")
    plt.legend()
    plt.tight_layout()
    plt.savefig(IMAGES_DIR / "graphrag_vs_standard_rag.png", dpi=180)
    plt.close()


def summarise(rows: list[dict]) -> dict:
    valid = [r for r in rows if not r["error"]]
    return {
        "queries_total": len(rows),
        "queries_successful": len(valid),
        "queries_failed": len(rows) - len(valid),
        "total_ms_p50": round(median([r["total_ms"] for r in valid]), 1) if valid else 0.0,
        "total_ms_avg": round(mean([r["total_ms"] for r in valid]), 1) if valid else 0.0,
        "keyword_recall_avg": round(mean([r["keyword_recall"] for r in valid]), 3) if valid else 0.0,
    }


def save_summary(rows: list[dict], path: Path) -> None:
    summary = {
        **summarise(rows),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)


def save_comparison_summary(
    graphrag_rows: list[dict],
    baseline_rows: list[dict],
    path: Path,
) -> dict:
    graphrag = summarise(graphrag_rows)
    baseline = summarise(baseline_rows)
    quality_gain = improvement_percent(
        baseline["keyword_recall_avg"],
        graphrag["keyword_recall_avg"],
    )
    latency_delta = round(graphrag["total_ms_avg"] - baseline["total_ms_avg"], 1)

    summary = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "graphrag": graphrag,
        "standard_rag": baseline,
        "keyword_recall_absolute_gain": round(
            graphrag["keyword_recall_avg"] - baseline["keyword_recall_avg"], 3
        ),
        "keyword_recall_relative_improvement_pct": quality_gain,
        "avg_latency_delta_ms": latency_delta,
        "note": (
            "Standard RAG baseline uses vector + BM25 only. GraphRAG uses graph "
            "traversal + vector + BM25 + community summaries."
        ),
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    return summary


def _ragas_skip_reason() -> str:
    """Return an empty string if RAGAS can run, else a human-readable reason."""
    try:
        import ragas  # noqa: F401
        import openai  # noqa: F401
        from ragas.metrics import collections  # noqa: F401
    except ImportError as exc:
        return f"Missing optional dependency: {exc}. Install with: pip install -r requirements-eval.txt"
    if not (os.getenv("GROQ_API_KEY") or os.getenv("GROQ_KEY")):
        return "GROQ_API_KEY not set — RAGAS uses Qwen-on-Groq as the evaluator LLM."
    return ""


def _build_ragas_models():
    """
    Build the RAGAS (>=0.4) evaluator LLM + embeddings on the free stack:
      - LLM judge: a fast, non-reasoning Groq model (RAGAS_JUDGE_MODEL) via an
        async OpenAI-compatible client. A separate judge model keeps structured
        scoring fast — Qwen3's "thinking" makes RAGAS calls extremely slow.
      - Embeddings: local all-MiniLM-L6-v2 (no external embedding API).

    The collections metrics run async, so the LLM needs an AsyncOpenAI client.
    """
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory
    from ragas.embeddings import HuggingFaceEmbeddings

    groq_key = (os.getenv("GROQ_API_KEY") or os.getenv("GROQ_KEY") or "").strip()

    client = AsyncOpenAI(
        api_key=groq_key,
        base_url="https://api.groq.com/openai/v1",
        timeout=LLM_TIMEOUT,
        max_retries=2,
    )
    # Larger max_tokens avoids truncated structured outputs (faithfulness can emit
    # many statements/verdicts). The judge model itself does no chain-of-thought.
    llm = llm_factory(
        RAGAS_JUDGE_MODEL,
        provider="openai",
        client=client,
        max_tokens=RAGAS_JUDGE_MAX_TOKENS,
    )
    embeddings = HuggingFaceEmbeddings(model=EMBEDDING_MODEL)
    return llm, embeddings


# Cap contexts passed to RAGAS so evaluator prompts stay small and fast.
_RAGAS_MAX_CONTEXTS = 3
_RAGAS_MAX_CONTEXT_CHARS = 1200


def _trim_contexts(contexts: list[str]) -> list[str]:
    return [c[:_RAGAS_MAX_CONTEXT_CHARS] for c in contexts[:_RAGAS_MAX_CONTEXTS]]


# Hard wall-clock cap per metric so a rate-limited / stuck Groq call degrades to
# None instead of hanging the whole evaluation (Groq free tier throttles bursts).
_RAGAS_METRIC_TIMEOUT = float(os.getenv("RAGAS_METRIC_TIMEOUT", "150"))
_RAGAS_POOL = ThreadPoolExecutor(max_workers=1)


def _metric_score(metric, **kwargs) -> float | None:
    """Run a single RAGAS metric, returning a float score or None on failure."""
    future = _RAGAS_POOL.submit(metric.score, **kwargs)
    try:
        return float(future.result(timeout=_RAGAS_METRIC_TIMEOUT))
    except FuturesTimeout:
        logger.warning(f"RAGAS metric '{getattr(metric, 'name', metric)}' timed out")
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"RAGAS metric failed: {exc}")
        return None


def save_ragas_eval(rows: list[dict], path: Path) -> None:
    """
    Optional RAGAS evaluation (faithfulness, answer relevancy, context precision).

    Runs on the project's free stack — Qwen-on-Groq + local embeddings — using the
    modern RAGAS collections API (per-row async scoring, single completion). Never
    falls back to OpenAI. Skips gracefully if dependencies or the key are missing.
    """
    reason = _ragas_skip_reason()
    if reason:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"skipped": True, "reason": reason}, handle, indent=2)
        return

    try:
        from ragas.metrics.collections import (
            AnswerRelevancy,
            ContextPrecisionWithoutReference,
            Faithfulness,
        )
        llm, embeddings = _build_ragas_models()
        faithfulness = Faithfulness(llm=llm)
        # strictness=1 keeps each call to a single completion (Groq rejects n>1).
        answer_relevancy = AnswerRelevancy(llm=llm, embeddings=embeddings, strictness=1)
        context_precision = ContextPrecisionWithoutReference(llm=llm)
    except Exception as exc:  # noqa: BLE001
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"skipped": True, "reason": str(exc)}, handle, indent=2)
        return

    out_rows: list[dict] = []
    for row in rows:
        user_input = row["query"]
        response = row.get("answer", "")
        contexts = _trim_contexts(json.loads(row.get("contexts_json") or "[]"))

        out_rows.append({
            "query": user_input,
            "faithfulness": _metric_score(
                faithfulness,
                user_input=user_input,
                response=response,
                retrieved_contexts=contexts,
            ),
            "answer_relevancy": _metric_score(
                answer_relevancy,
                user_input=user_input,
                response=response,
            ),
            "context_precision": _metric_score(
                context_precision,
                user_input=user_input,
                response=response,
                retrieved_contexts=contexts,
            ),
        })

    def _avg(key: str) -> float | None:
        vals = [r[key] for r in out_rows if isinstance(r[key], (int, float))]
        return round(sum(vals) / len(vals), 3) if vals else None

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "skipped": False,
                "evaluator": f"groq:{RAGAS_JUDGE_MODEL}",
                "embeddings": EMBEDDING_MODEL,
                "averages": {
                    "faithfulness": _avg("faithfulness"),
                    "answer_relevancy": _avg("answer_relevancy"),
                    "context_precision": _avg("context_precision"),
                },
                "rows": out_rows,
            },
            handle,
            indent=2,
        )


def main() -> None:
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    queries = load_queries()
    graphrag_rows = [evaluate_query(q, mode="graphrag") for q in queries]
    baseline_rows = [evaluate_query(q, mode="standard_rag") for q in queries]

    save_csv(graphrag_rows, METRICS_DIR / "query_results.csv")
    save_csv(baseline_rows, METRICS_DIR / "standard_rag_results.csv")
    save_csv(graphrag_rows + baseline_rows, METRICS_DIR / "comparison_results.csv")
    save_summary(graphrag_rows, METRICS_DIR / "summary.json")
    comparison = save_comparison_summary(
        graphrag_rows,
        baseline_rows,
        METRICS_DIR / "comparison_summary.json",
    )
    save_plots(graphrag_rows)
    save_comparison_plot(graphrag_rows, baseline_rows)
    save_ragas_eval(graphrag_rows, METRICS_DIR / "ragas_graphrag.json")
    save_ragas_eval(baseline_rows, METRICS_DIR / "ragas_standard_rag.json")

    print(f"Saved metrics to: {METRICS_DIR}")
    print(f"Saved plots to:   {IMAGES_DIR}")
    print(
        "Keyword recall improvement: "
        f"{comparison['keyword_recall_relative_improvement_pct']}%"
    )


if __name__ == "__main__":
    main()
