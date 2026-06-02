import csv
import json
import time
from pathlib import Path
from statistics import mean, median

import matplotlib.pyplot as plt

from pipeline import query as run_query


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


def evaluate_query(item: dict) -> dict:
    started = time.perf_counter()
    error = ""
    answer = ""
    timing = {}
    entities_found = 0

    try:
        result = run_query(item["query"])
        answer = result.get("answer", "")
        timing = result.get("timing", {}) or {}
        entities_found = len(result.get("entities", []) or [])
    except Exception as exc:
        error = str(exc)

    wall_ms = round((time.perf_counter() - started) * 1000, 1)
    total_ms = float(timing.get("total_ms", wall_ms))
    llm_ms = float(timing.get("llm_generation_ms", 0.0))
    recall = keyword_recall(answer, item.get("expected_keywords", []))

    return {
        "id": item.get("id", ""),
        "query": item["query"],
        "total_ms": total_ms,
        "llm_generation_ms": llm_ms,
        "retrieval_ms": round(max(total_ms - llm_ms, 0.0), 1),
        "entities_found": entities_found,
        "answer_chars": len(answer or ""),
        "keyword_recall": recall,
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

    plt.figure(figsize=(10, 4))
    plt.bar(ids, quality)
    plt.ylim(0, 1.05)
    plt.ylabel("Keyword recall")
    plt.title("AirGraph Assist Answer Quality (Keyword Recall)")
    plt.tight_layout()
    plt.savefig(IMAGES_DIR / "quality_scores.png", dpi=180)
    plt.close()


def save_summary(rows: list[dict], path: Path) -> None:
    valid = [r for r in rows if not r["error"]]
    summary = {
        "queries_total": len(rows),
        "queries_successful": len(valid),
        "queries_failed": len(rows) - len(valid),
        "total_ms_p50": round(median([r["total_ms"] for r in valid]), 1) if valid else 0.0,
        "total_ms_avg": round(mean([r["total_ms"] for r in valid]), 1) if valid else 0.0,
        "keyword_recall_avg": round(mean([r["keyword_recall"] for r in valid]), 3) if valid else 0.0,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)


def main() -> None:
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    queries = load_queries()
    rows = [evaluate_query(q) for q in queries]

    save_csv(rows, METRICS_DIR / "query_results.csv")
    save_summary(rows, METRICS_DIR / "summary.json")
    save_plots(rows)

    print(f"Saved metrics to: {METRICS_DIR}")
    print(f"Saved plots to:   {IMAGES_DIR}")


if __name__ == "__main__":
    main()
