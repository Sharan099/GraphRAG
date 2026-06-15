# AirGraph Assist — Frontend (Next.js)

Chat UI + live knowledge-graph visualisation for the AirGraph Assist GraphRAG
backend. Deployed to **Vercel**.

## Stack

- **Next.js 14** (App Router) + **React 18** + **TypeScript**
- **Tailwind CSS** — aerospace dark theme
- Dependency-free SVG graph + latency visualisations

## Local development

```bash
cd frontend
npm install
copy .env.example .env.local      # Windows
# cp .env.example .env.local      # macOS / Linux
npm run dev
```

Open http://localhost:3000. Make sure the backend is running and
`NEXT_PUBLIC_API_URL` points to it (defaults to `http://localhost:8000`).

## Environment variables

| Variable              | Description                                  |
| --------------------- | -------------------------------------------- |
| `NEXT_PUBLIC_API_URL` | Base URL of the FastAPI backend (Railway).   |

## Deploy to Vercel

1. Push this repo to GitHub.
2. On [vercel.com](https://vercel.com) → **Add New → Project** → import the repo.
3. Set the **Root Directory** to `frontend`.
4. Add the env var `NEXT_PUBLIC_API_URL` = your Railway backend URL.
5. Deploy. Vercel auto-detects Next.js (`npm run build`).

After the backend is live, set `ALLOWED_ORIGINS` on Railway to your Vercel URL.
