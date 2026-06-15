"use client";

import { useMemo, useState } from "react";
import type { GraphViz } from "@/lib/types";
import {
  EDGE_COLORS,
  NODE_COLORS,
  NODE_DESCRIPTIONS,
  NODE_ICONS,
} from "@/lib/constants";

const W = 640;
const H = 460;
const CX = W / 2;
const CY = H / 2 - 10;

interface Placed {
  id: string;
  label: string;
  type: string;
  x: number;
  y: number;
  r: number;
}

export default function GraphView({ viz }: { viz?: GraphViz }) {
  const [hover, setHover] = useState<Placed | null>(null);

  const { placed, edges, byId } = useMemo(() => {
    const nodes = viz?.nodes ?? [];
    const rels = viz?.edges ?? [];
    const positions: Record<string, Placed> = {};

    nodes.forEach((n, i) => {
      let x = CX;
      let y = CY;
      let r = 9;

      if (i === 0) {
        x = CX;
        y = CY;
        r = 15;
      } else if (i < 7) {
        const inner = Math.min(6, nodes.length - 1);
        const angle = (2 * Math.PI * (i - 1)) / Math.max(inner, 1);
        x = CX + Math.cos(angle) * 130;
        y = CY + Math.sin(angle) * 120;
        r = n.type === "Warning" ? 11 : 9;
      } else {
        const outer = nodes.length - 7;
        const offset = Math.PI / Math.max(outer, 1);
        const angle = (2 * Math.PI * (i - 7)) / Math.max(outer, 1) + offset;
        x = CX + Math.cos(angle) * 215;
        y = CY + Math.sin(angle) * 195;
        r = 8;
      }

      positions[n.id] = {
        id: n.id,
        label: n.label || n.id,
        type: n.type || "Node",
        x,
        y,
        r,
      };
    });

    return {
      placed: Object.values(positions),
      edges: rels,
      byId: positions,
    };
  }, [viz]);

  if (!viz || !viz.nodes || viz.nodes.length === 0) {
    return (
      <div className="flex h-[280px] items-center justify-center rounded-xl border border-ink-400/60 bg-ink-900/60 text-sm text-haze">
        Run a query to see the knowledge subgraph.
      </div>
    );
  }

  const usedNodeTypes = Array.from(new Set(placed.map((p) => p.type)));
  const usedEdgeTypes = Array.from(
    new Set(edges.map((e) => e.label || "CONNECTED_TO"))
  );

  return (
    <div className="rounded-xl border border-ink-400/60 bg-ink-900/70 p-2">
      <div className="relative">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="h-auto w-full"
          role="img"
          aria-label="Knowledge subgraph"
        >
          {/* edges */}
          {edges.map((e, i) => {
            const a = byId[e.from];
            const b = byId[e.to];
            if (!a || !b) return null;
            const color = EDGE_COLORS[e.label] || "#64748b";
            const mx = (a.x + b.x) / 2;
            const my = (a.y + b.y) / 2;
            const showLabel = edges.length <= 18;
            return (
              <g key={`e-${i}`}>
                <line
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  stroke={color}
                  strokeWidth={1.4}
                  strokeOpacity={0.6}
                />
                {showLabel && (
                  <text
                    x={mx}
                    y={my}
                    fill={color}
                    fontSize={7.5}
                    fontFamily="var(--font-mono), monospace"
                    textAnchor="middle"
                    className="select-none"
                  >
                    {(e.label || "").replace(/_/g, " ")}
                  </text>
                )}
              </g>
            );
          })}

          {/* nodes */}
          {placed.map((p) => {
            const color = NODE_COLORS[p.type] || "#64748b";
            const short =
              p.label.length > 16 ? `${p.label.slice(0, 16)}\u2026` : p.label;
            return (
              <g
                key={p.id}
                onMouseEnter={() => setHover(p)}
                onMouseLeave={() => setHover(null)}
                className="cursor-pointer"
              >
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={p.r}
                  fill={color}
                  stroke="rgba(255,255,255,0.45)"
                  strokeWidth={1.3}
                  opacity={0.95}
                />
                <text
                  x={p.x}
                  y={p.y - p.r - 5}
                  fill="#c8ddf5"
                  fontSize={8.5}
                  textAnchor="middle"
                  className="select-none"
                >
                  {short}
                </text>
              </g>
            );
          })}
        </svg>

        {hover && (
          <div className="pointer-events-none absolute left-3 top-3 max-w-[260px] rounded-lg border border-ink-400 bg-ink-800/95 px-3 py-2 text-xs shadow-glow">
            <div className="font-mono font-semibold text-frost">
              {NODE_ICONS[hover.type] || "\u25cf"} {hover.type}
            </div>
            <div className="mt-1 text-haze">
              <span className="text-accent-muted">ID:</span> {hover.id}
            </div>
            <div className="text-haze">
              <span className="text-accent-muted">Name:</span> {hover.label}
            </div>
            <div className="mt-1 italic text-haze/80">
              {NODE_DESCRIPTIONS[hover.type] || ""}
            </div>
          </div>
        )}
      </div>

      {/* legend */}
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5 border-t border-ink-500 px-1 pt-2">
        {usedNodeTypes.map((t) => (
          <span key={t} className="flex items-center gap-1.5 text-[11px] text-haze">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ background: NODE_COLORS[t] || "#64748b" }}
            />
            {t}
          </span>
        ))}
        {usedEdgeTypes.map((t) => (
          <span key={t} className="flex items-center gap-1.5 text-[11px] text-haze/80">
            <span
              className="inline-block h-[2px] w-4 rounded"
              style={{ background: EDGE_COLORS[t] || "#64748b" }}
            />
            <span className="font-mono">{t}</span>
          </span>
        ))}
      </div>

      <div className="px-1 pt-1.5 text-[11px] text-haze/70">
        <strong className="text-frost">{viz.nodes.length}</strong> nodes
        {" \u00b7 "}
        <strong className="text-frost">{viz.edges.length}</strong> relationships
        {" \u2014 hover any node for details"}
      </div>
    </div>
  );
}
