"use client";

import { useEffect, useRef, useState } from "react";
import { getMeta, postQuery } from "@/lib/api";
import { FALLBACK_SAMPLE_QUESTIONS } from "@/lib/constants";
import type { ChatMessage, Meta } from "@/lib/types";
import Answer from "@/components/Answer";
import GraphView from "@/components/GraphView";
import LatencyChart from "@/components/LatencyChart";
import InfoPanel from "@/components/InfoPanel";

type Tab = "graph" | "latency" | "guide";

let idSeq = 0;
const nextId = () => `m-${Date.now()}-${idSeq++}`;

export default function Home() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<Tab>("graph");

  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getMeta().then((m) => {
      setMeta(m);
      setOnline(m !== null);
    });
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  const lastResult = [...messages]
    .reverse()
    .find((m) => m.role === "assistant" && m.result)?.result;

  const sampleQuestions = meta?.sample_questions?.length
    ? meta.sample_questions
    : FALLBACK_SAMPLE_QUESTIONS;

  async function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;

    setInput("");
    setBusy(true);

    const userMsg: ChatMessage = { id: nextId(), role: "user", content: q };
    const pendingMsg: ChatMessage = {
      id: nextId(),
      role: "assistant",
      content: "",
      pending: true,
    };
    setMessages((prev) => [...prev, userMsg, pendingMsg]);

    try {
      const result = await postQuery(q);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === pendingMsg.id
            ? { ...m, pending: false, content: result.answer, result }
            : m
        )
      );
      if (result.graph_viz?.nodes?.length) setTab("graph");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Could not reach the backend.";
      setMessages((prev) =>
        prev.map((m) =>
          m.id === pendingMsg.id
            ? {
                ...m,
                pending: false,
                content: `**Connection error.** ${message}\n\nMake sure the backend is running and \`NEXT_PUBLIC_API_URL\` points to it.`,
              }
            : m
        )
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-[1400px] flex-col px-4 py-5 sm:px-6">
      {/* Header */}
      <header className="rounded-2xl border border-ink-400/70 bg-gradient-to-br from-ink-800 via-ink-600 to-[#0a2e50] px-6 py-5 shadow-glow">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="font-mono text-2xl font-semibold tracking-tight text-[#e8f2ff]">
              ✈️ AirGraph Assist
            </h1>
            <p className="mt-1 text-sm text-haze">
              GraphRAG over the Aquila AT01 (A210) aircraft maintenance manual.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Tag>Hybrid GraphRAG</Tag>
              <Tag>Graph + Vector + BM25</Tag>
              <Tag>Neo4j · FastAPI · Claude</Tag>
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            <StatusPill online={online} />
            {meta?.model && (
              <span className="rounded-full border border-ink-400 bg-ink-900/60 px-3 py-1 font-mono text-[11px] text-accent-soft">
                {meta.model}
              </span>
            )}
          </div>
        </div>
      </header>

      {/* Body */}
      <div className="mt-5 grid flex-1 grid-cols-1 gap-5 lg:grid-cols-12">
        {/* Chat */}
        <section className="flex min-h-[60vh] flex-col rounded-2xl border border-ink-400/70 bg-ink-800/40 lg:col-span-7">
          <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-5">
            {messages.length === 0 ? (
              <EmptyState
                questions={sampleQuestions}
                onPick={send}
                disabled={busy}
              />
            ) : (
              messages.map((m) => <Bubble key={m.id} msg={m} />)
            )}
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="border-t border-ink-500 p-3"
          >
            <div className="flex items-end gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send(input);
                  }
                }}
                rows={1}
                placeholder="Ask a maintenance question…"
                className="max-h-32 min-h-[44px] flex-1 resize-none rounded-xl border border-ink-400 bg-ink-900/70 px-4 py-2.5 text-sm text-frost outline-none placeholder:text-haze/60 focus:border-accent/70"
              />
              <button
                type="submit"
                disabled={busy || !input.trim()}
                className="h-[44px] shrink-0 rounded-xl bg-accent px-5 text-sm font-semibold text-white transition hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-40"
              >
                {busy ? "…" : "Send"}
              </button>
            </div>
          </form>
        </section>

        {/* Inspector */}
        <aside className="flex flex-col rounded-2xl border border-ink-400/70 bg-ink-800/40 lg:col-span-5">
          <div className="flex gap-1 border-b border-ink-500 p-2">
            <TabBtn active={tab === "graph"} onClick={() => setTab("graph")}>
              Knowledge Graph
            </TabBtn>
            <TabBtn active={tab === "latency"} onClick={() => setTab("latency")}>
              Latency
            </TabBtn>
            <TabBtn active={tab === "guide"} onClick={() => setTab("guide")}>
              How it works
            </TabBtn>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            {tab === "graph" && <GraphView viz={lastResult?.graph_viz} />}
            {tab === "latency" && <LatencyChart timing={lastResult?.timing} />}
            {tab === "guide" && <InfoPanel />}
          </div>
        </aside>
      </div>

      <footer className="mt-5 text-center text-[11px] text-haze/60">
        Backend on Railway · Frontend on Vercel · Answers grounded in the
        maintenance manual graph.
      </footer>
    </div>
  );
}

/* ── Small presentational pieces ───────────────────────────────────────────── */

function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full border border-accent/30 bg-accent/15 px-2.5 py-0.5 font-mono text-[11px] text-accent-soft">
      {children}
    </span>
  );
}

function StatusPill({ online }: { online: boolean | null }) {
  const label =
    online === null ? "connecting" : online ? "backend online" : "backend offline";
  const color =
    online === null
      ? "bg-amber-400"
      : online
        ? "bg-emerald-400"
        : "bg-red-400";
  return (
    <span className="flex items-center gap-2 rounded-full border border-ink-400 bg-ink-900/60 px-3 py-1 text-[11px] text-haze">
      <span
        className={`h-2 w-2 rounded-full ${color} ${
          online === null ? "animate-pulse-dot" : ""
        }`}
      />
      {label}
    </span>
  );
}

function TabBtn({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 rounded-lg px-3 py-2 text-xs font-medium transition ${
        active
          ? "bg-accent/15 text-accent-soft"
          : "text-haze hover:bg-ink-700/60 hover:text-frost"
      }`}
    >
      {children}
    </button>
  );
}

function EmptyState({
  questions,
  onPick,
  disabled,
}: {
  questions: string[];
  onPick: (q: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-5 py-10 text-center">
      <div className="text-4xl">🛩️</div>
      <div>
        <h2 className="font-mono text-lg font-semibold text-frost">
          Ask about the maintenance manual
        </h2>
        <p className="mx-auto mt-1 max-w-md text-sm text-haze">
          Every answer is grounded in a Neo4j knowledge graph built from the
          aircraft maintenance documentation. Try one of these:
        </p>
      </div>
      <div className="grid w-full max-w-2xl grid-cols-1 gap-2 sm:grid-cols-2">
        {questions.map((q) => (
          <button
            key={q}
            disabled={disabled}
            onClick={() => onPick(q)}
            className="rounded-xl border border-ink-400/70 bg-ink-900/50 px-4 py-3 text-left text-sm text-frost/90 transition hover:border-accent/60 hover:bg-ink-700/60 disabled:opacity-50"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

function Bubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex animate-fade-up ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[88%] rounded-2xl border px-4 py-3 ${
          isUser
            ? "border-accent/40 bg-accent/15 text-frost"
            : "border-ink-400/70 bg-ink-900/50"
        }`}
      >
        {isUser ? (
          <p className="text-sm">{msg.content}</p>
        ) : msg.pending ? (
          <Thinking />
        ) : (
          <>
            <Answer text={msg.content} />
            {msg.result?.timing?.total_ms ? (
              <div className="mt-2 border-t border-ink-500 pt-2 font-mono text-[11px] text-haze/70">
                {(Number(msg.result.timing.total_ms) / 1000).toFixed(2)}s
                {msg.result.entities?.length
                  ? ` · ${msg.result.entities.length} graph entities`
                  : ""}
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}

function Thinking() {
  return (
    <div className="flex items-center gap-2 text-sm text-haze">
      <span className="flex gap-1">
        <Dot d="0ms" />
        <Dot d="150ms" />
        <Dot d="300ms" />
      </span>
      Traversing the knowledge graph…
    </div>
  );
}

function Dot({ d }: { d: string }) {
  return (
    <span
      className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-accent-soft"
      style={{ animationDelay: d }}
    />
  );
}
