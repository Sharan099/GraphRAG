"use client";

import {
  EDGE_COLORS,
  EDGE_DESCRIPTIONS,
  NODE_COLORS,
  NODE_DESCRIPTIONS,
  NODE_ICONS,
  PIPELINE_STEPS,
} from "@/lib/constants";

const NODE_GUIDE_ORDER = [
  "Component",
  "Warning",
  "Tool",
  "Defect",
  "Requirement",
  "MaintenanceStep",
];

const EDGE_GUIDE_ORDER = [
  "USED_IN",
  "REQUIRES_TOOL",
  "WARNS_ABOUT",
  "FIXES_DEFECT",
  "GOVERNS",
];

function Heading({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-2 mt-1 font-mono text-[0.72rem] uppercase tracking-[0.12em] text-accent-muted">
      {children}
    </div>
  );
}

export default function InfoPanel() {
  return (
    <div className="space-y-6 text-sm text-frost/85">
      <section>
        <h3 className="mb-2 font-mono text-base font-semibold text-frost">
          What is GraphRAG?
        </h3>
        <p className="leading-relaxed text-haze">
          Classic RAG splits documents into chunks, embeds them, and finds the
          closest chunk by similarity. For maintenance manuals that loses two
          things: cross-chunk <strong className="text-frost">connections</strong>{" "}
          (a warning lives in a different chunk from its procedure) and the{" "}
          <strong className="text-frost">relationship type</strong> between facts.
          AirGraph stores the manual as a typed knowledge graph instead.
        </p>
      </section>

      <section>
        <Heading>Node types in the knowledge graph</Heading>
        <div className="divide-y divide-ink-500">
          {NODE_GUIDE_ORDER.map((t) => (
            <div key={t} className="flex items-start gap-3 py-2">
              <span
                className="mt-1.5 inline-block h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ background: NODE_COLORS[t] }}
              />
              <div>
                <div className="font-semibold text-frost">
                  {NODE_ICONS[t]} {t}
                </div>
                <div className="text-xs text-haze">{NODE_DESCRIPTIONS[t]}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section>
        <Heading>Relationship types (graph edges)</Heading>
        <div className="divide-y divide-ink-500">
          {EDGE_GUIDE_ORDER.map((t) => (
            <div key={t} className="flex items-center gap-3 py-2">
              <span
                className="inline-block h-[3px] w-5 shrink-0 rounded"
                style={{ background: EDGE_COLORS[t] }}
              />
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="font-mono text-xs text-frost">{t}</span>
                <span className="text-xs text-haze">{EDGE_DESCRIPTIONS[t]}</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section>
        <Heading>How a question is answered</Heading>
        <div className="space-y-2">
          {PIPELINE_STEPS.map(([icon, name, desc], i) => (
            <div
              key={name}
              className="flex items-start gap-3 rounded-lg border border-ink-500 bg-ink-900/50 p-3"
            >
              <span className="text-lg leading-none">{icon}</span>
              <div>
                <div className="text-sm font-semibold text-frost">
                  Step {i + 1} — {name}
                </div>
                <div className="text-xs leading-relaxed text-haze">{desc}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-ink-500 bg-ink-900/50 p-3">
          <div className="mb-1.5 text-sm font-semibold text-haze">Classic RAG</div>
          <ul className="space-y-1 text-xs text-haze/90">
            <li>• Finds similar text</li>
            <li>• Misses cross-chunk links</li>
            <li>• No relationship context</li>
            <li>• Can hallucinate connections</li>
          </ul>
        </div>
        <div className="rounded-lg border border-accent/40 bg-accent/10 p-3">
          <div className="mb-1.5 text-sm font-semibold text-accent-soft">
            GraphRAG (this system)
          </div>
          <ul className="space-y-1 text-xs text-frost/90">
            <li>• Follows explicit typed edges</li>
            <li>• Guarantees warning retrieval</li>
            <li>• Knows <em>why</em> nodes relate</li>
            <li>• Traceable to graph nodes</li>
          </ul>
        </div>
      </section>
    </div>
  );
}
