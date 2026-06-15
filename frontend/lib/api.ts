import type { Meta, QueryResponse } from "./types";

const DEFAULT_API_BASE =
  process.env.NODE_ENV === "production"
    ? "https://graphrag-production-b584.up.railway.app"
    : "http://localhost:8000";

function normalizeApiBase(rawUrl?: string): string {
  const trimmed = (rawUrl || DEFAULT_API_BASE).trim().replace(/\/+$/, "");

  if (/^https?:\/\//i.test(trimmed)) {
    return trimmed;
  }

  // Vercel env vars are often entered as "foo.up.railway.app". Without the
  // protocol, fetch treats that as a relative frontend path and returns Vercel's
  // HTML 404 page instead of calling the Railway backend.
  return `https://${trimmed}`;
}

async function getErrorMessage(res: Response): Promise<string> {
  const contentType = res.headers.get("content-type") || "";
  const text = await res.text().catch(() => "");

  if (contentType.includes("text/html")) {
    return `API ${res.status}: received an HTML page instead of API JSON. Check NEXT_PUBLIC_API_URL.`;
  }

  return `API ${res.status}: ${(text || res.statusText).slice(0, 500)}`;
}

export const API_BASE = normalizeApiBase(process.env.NEXT_PUBLIC_API_URL);

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
    throw new Error(await getErrorMessage(res));
  }

  return (await res.json()) as QueryResponse;
}
