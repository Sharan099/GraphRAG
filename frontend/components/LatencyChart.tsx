"use client";

import type { Timing } from "@/lib/types";

const FRIENDLY: Record<string, string> = {
  total_ms: "\u23f1 Total pipeline",
  llm_generation_ms: "\ud83e\udd16 LLM generation",
  retrieval_ms: "\ud83d\udd0d Retrieval",
};

function barColor(ms: number): string {
  if (ms >= 30000) return "#ef4444";
  if (ms >= 5000) return "#f59e0b";
  return "#34d399";
}

function fmt(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms.toFixed(0)} ms`;
}

export default function LatencyChart({ timing }: { timing?: Timing }) {
  if (!timing) {
    return (
      <div className="rounded-xl border border-ink-400/60 bg-ink-900/60 p-4 text-sm text-haze">
        No timing data yet — run a query first.
      </div>
    );
  }

  const rows = Object.entries(timing)
    .filter(([k, v]) => k.endsWith("_ms") && typeof v === "number")
    .map(([k, v]) => ({
      label: FRIENDLY[k] || k.replace(/_ms$/, "").replace(/_/g, " "),
      ms: Number(v),
    }));

  const max = Math.max(1, ...rows.map((r) => r.ms));

  const total = Number(timing.total_ms || 0);
  const llm = Number(timing.llm_generation_ms || 0);
  const graphPct = total > 0 && llm > 0 ? Math.round(((total - llm) / total) * 100) : null;
  const llmPct = total > 0 && llm > 0 ? Math.round((llm / total) * 100) : null;

  return (
    <div className="space-y-3">
      <div className="space-y-2.5 rounded-xl border border-ink-400/60 bg-ink-900/60 p-4">
        {rows.length === 0 && (
          <div className="text-sm text-haze">No timing keys found.</div>
        )}
        {rows.map((r) => (
          <div key={r.label} className="space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="text-frost/90">{r.label}</span>
              <span className="font-mono text-haze">{fmt(r.ms)}</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-ink-700">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${Math.max(3, (r.ms / max) * 100)}%`,
                  background: barColor(r.ms),
                }}
              />
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <div
          className={`rounded-lg border px-3 py-2 text-xs ${
            timing.fallback_used
              ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
              : "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
          }`}
        >
          {timing.fallback_used
            ? "\u26a1 Document fallback used \u2014 graph results were sparse."
            : "\u2705 Answer sourced from the knowledge graph."}
        </div>
        {graphPct !== null && llmPct !== null && (
          <div className="rounded-lg border border-ink-400/60 bg-ink-700/50 px-3 py-2 text-xs text-haze">
            Graph retrieval <strong className="text-frost">{graphPct}%</strong>
            {" \u00b7 "}
            LLM <strong className="text-frost">{llmPct}%</strong>
          </div>
        )}
      </div>
    </div>
  );
}
