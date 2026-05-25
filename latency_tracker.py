import sys
import time
import json
import statistics
from pathlib import Path
from dataclasses import dataclass, field, asdict
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import TARGET_TOTAL_LATENCY, TARGET_GRAPH_QUERY, TARGET_VECTOR_QUERY


@dataclass
class BenchmarkRun:
    query: str
    entity_extraction_ms: float = 0.0
    graph_query_ms:       float = 0.0
    vector_query_ms:      float = 0.0
    ranking_ms:           float = 0.0
    pruning_ms:           float = 0.0
    compression_ms:       float = 0.0
    llm_ms:               float = 0.0
    total_ms:             float = 0.0
    tokens_used:          int   = 0
    context_tokens:       int   = 0
    entities_found:       int   = 0
    graph_nodes:          int   = 0
    vector_hits:          int   = 0
    passed_target:        bool  = False
    error:                str   = ""


@dataclass
class BenchmarkSuite:
    runs: list = field(default_factory=list)

    def add(self, run: BenchmarkRun):
        self.runs.append(run)

    def summary(self) -> dict:
        if not self.runs:
            return {}
        totals = [r.total_ms for r in self.runs if r.total_ms > 0]
        llms   = [r.llm_ms   for r in self.runs if r.llm_ms > 0]
        return {
            "n_runs":        len(self.runs),
            "pass_rate":     sum(1 for r in self.runs if r.passed_target) / len(self.runs),
            "total_p50_ms":  statistics.median(totals),
            "total_p95_ms":  statistics.quantiles(totals, n=20)[-1] if len(totals) >= 5 else max(totals),
            "llm_p50_ms":    statistics.median(llms) if llms else 0,
            "avg_tokens":    statistics.mean([r.tokens_used for r in self.runs]),
            "bottleneck":    self._identify_bottleneck(),
        }

    def _identify_bottleneck(self) -> str:
        if not self.runs:
            return "no data"
        avg = lambda attr: statistics.mean([getattr(r, attr) for r in self.runs])
        times = {
            "Neo4j graph query":   avg("graph_query_ms"),
            "ChromaDB vector":     avg("vector_query_ms"),
            "LLM generation":      avg("llm_ms"),
            "Context ranking":     avg("ranking_ms") + avg("pruning_ms"),
        }
        bottleneck = max(times, key=times.get)
        return f"{bottleneck} ({round(times[bottleneck], 0)}ms avg)"

    def to_json(self) -> str:
        return json.dumps({
            "runs":    [asdict(r) for r in self.runs],
            "summary": self.summary()
        }, indent=2)


class LatencyBenchmark:
    """
    Runs benchmark queries and tracks every step.
    
    Usage:
        bench = LatencyBenchmark(graph, vector, llm, retriever)
        suite = bench.run_suite(TEST_QUERIES)
        print(suite.summary())
    """

    # Standard benchmark queries for aircraft assembly domain
    TEST_QUERIES = [
        "What are the installation steps for hydraulic pump HPU-22 and common errors?",
        "HPU-22 safety warnings and precautions",
        "What tools do I need to install HPU-22?",
        "Common defects on hydraulic system components",
        "How to depressurise hydraulic system before maintenance?",
        "HPU-22 torque specifications for mounting bolts",
        "What is connected to HPU-22 in the hydraulic system?",
        "Hydraulic fluid contamination check procedure",
    ]

    def __init__(self, graph_builder, vector_store, llm_client, retriever):
        self.graph     = graph_builder
        self.vector    = vector_store
        self.llm       = llm_client
        self.retriever = retriever

    def run_single(self, query: str) -> BenchmarkRun:
        """Run one query end-to-end and record timing for every step."""
        run = BenchmarkRun(query=query)
        t_total = time.time()

        try:
            # ── Step 1: Entity extraction ──
            t0 = time.time()
            entities = self.retriever.extract_entities(query)
            run.entity_extraction_ms = round((time.time() - t0) * 1000, 1)
            run.entities_found = len(entities)

            # ── Step 2: Graph query (isolated timing) ──
            t0 = time.time()
            graph_results = {}
            for eid in entities:
                ctx = self.graph.get_component_context(eid)
                graph_results[eid] = ctx
            run.graph_query_ms = round((time.time() - t0) * 1000, 1)
            run.graph_nodes = sum(
                len(v.get("steps", [])) + len(v.get("defects", []))
                for v in graph_results.values()
            )

            # ── Step 3: Vector query (isolated timing) ──
            t0 = time.time()
            k = self.vector.adaptive_top_k(query)
            vector_results = self.vector.search(query, top_k=k)
            run.vector_query_ms = round((time.time() - t0) * 1000, 1)
            run.vector_hits = len(vector_results)

            # ── Step 4: Ranking ──
            t0 = time.time()
            ranked = self.retriever.rank_nodes(graph_results, vector_results)
            run.ranking_ms = round((time.time() - t0) * 1000, 1)

            # ── Step 5: Pruning ──
            t0 = time.time()
            pruned = self.retriever.prune_context(ranked)
            run.pruning_ms = round((time.time() - t0) * 1000, 1)

            # ── Step 6: Compression ──
            t0 = time.time()
            context = self.retriever.compress_prompt(pruned, query)
            run.compression_ms = round((time.time() - t0) * 1000, 1)
            run.context_tokens = len(context) // 4

            # ── Step 7: LLM ──
            t0 = time.time()
            llm_result = self.llm.generate(query, context)
            run.llm_ms = round((time.time() - t0) * 1000, 1)
            run.tokens_used = llm_result.get("tokens_used", 0)

        except Exception as e:
            run.error = str(e)
            logger.error(f"Benchmark run failed: {e}")

        run.total_ms = round((time.time() - t_total) * 1000, 1)
        run.passed_target = run.total_ms < (TARGET_TOTAL_LATENCY * 1000)
        return run

    def run_suite(
        self,
        queries: list = None,
        warmup: int = 1
    ) -> BenchmarkSuite:
        """
        Run full benchmark suite.
        
        warmup: Number of warmup queries (model needs first call to load weights).
                Warmup results are discarded — they're always slower.
        """
        if queries is None:
            queries = self.TEST_QUERIES

        suite = BenchmarkSuite()

        # Warmup (LLM loads model weights on first call — typically 3-5s extra)
        logger.info(f"🔥 Warming up with {warmup} query...")
        for i in range(warmup):
            self.run_single(queries[0])  # Discard warmup result
            logger.info(f"  Warmup {i+1}/{warmup} done")

        # Actual benchmark
        logger.info(f"📊 Running {len(queries)} benchmark queries...")
        for i, query in enumerate(queries):
            logger.info(f"  [{i+1}/{len(queries)}] {query[:60]}...")
            run = self.run_single(query)
            suite.add(run)

            status = "✅" if run.passed_target else "❌"
            logger.info(
                f"  {status} Total: {run.total_ms}ms | "
                f"Graph: {run.graph_query_ms}ms | "
                f"Vector: {run.vector_query_ms}ms | "
                f"LLM: {run.llm_ms}ms"
            )

        summary = suite.summary()
        logger.info(f"\n{'='*50}")
        logger.info(f"BENCHMARK SUMMARY")
        logger.info(f"  Pass rate (< {TARGET_TOTAL_LATENCY}s): {summary['pass_rate']*100:.0f}%")
        logger.info(f"  P50 latency:  {summary['total_p50_ms']:.0f}ms")
        logger.info(f"  P95 latency:  {summary['total_p95_ms']:.0f}ms")
        logger.info(f"  🔴 Bottleneck: {summary['bottleneck']}")
        logger.info(f"{'='*50}\n")

        # Save results
        out_path = Path(__file__).parent / "benchmark_results.json"
        with open(out_path, "w") as f:
            f.write(suite.to_json())
        logger.info(f"Results saved → {out_path}")

        return suite


def print_bottleneck_guide():
    """
    Printed during benchmark — helps engineer understand what to fix.
    """
    guide = """
╔══════════════════════════════════════════════════════════╗
║          LATENCY BOTTLENECK GUIDE                        ║
╠══════════════════════════════════════════════════════════╣
║ Neo4j > 300ms?                                           ║
║   → Add index: CREATE INDEX ON :Component(id)            ║
║   → Reduce TOP_K_GRAPH_HOPS from 2 to 1                  ║
║   → Use PROFILE query in Neo4j Browser to see slow plan  ║
╠══════════════════════════════════════════════════════════╣
║ ChromaDB > 200ms?                                        ║
║   → Use GPU embedding model (bge-small instead of MiniLM)║
║   → Reduce TOP_K_VECTOR from 5 to 3                      ║
║   → Use HNSW ef_search=32 (default 100)                  ║
╠══════════════════════════════════════════════════════════╣
║ LLM > 1500ms?                                            ║
║   → Switch to: tinyllama:1b (tiny, fast)                 ║
║   → Reduce num_ctx from 2048 to 1024                     ║
║   → Reduce MAX_CONTEXT_TOKENS from 1200 to 800           ║
║   → Use num_gpu=1 if GPU available                       ║
╠══════════════════════════════════════════════════════════╣
║ Context tokens > 1200?                                   ║
║   → Reduce TOP_K_VECTOR                                  ║
║   → Increase prune threshold (score > 0.6)               ║
║   → Truncate step descriptions at 200 chars              ║
╚══════════════════════════════════════════════════════════╝
"""
    print(guide)
