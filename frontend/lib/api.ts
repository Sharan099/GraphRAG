import type { Meta, QueryResponse } from "./types";

export const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
).replace(/\/$/, "");

export async function getMeta(): Promise<Meta | null> {
  try {
    const res = await fetch(`${API_BASE}/api/meta`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as Meta;
  } catch {
    return null;
  }
}

export async function postQuery(query: string): Promise<QueryResponse> {
  const res = await fetch(`${API_BASE}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text || res.statusText}`);
  }

  return (await res.json()) as QueryResponse;
}
