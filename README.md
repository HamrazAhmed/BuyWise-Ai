# BuyWise AI

**Evidence-backed shopping decision assistant** — Hackathon MVP

> Tell us what you're looking for. We'll research the options.

BuyWise AI converts a natural-language shopping request into structured requirements, researches 3–5 candidate products, verifies specs against primary sources, and presents a transparent comparison with citations and trade-offs.

---

## Quick start (local development)

### Prerequisites

- Node.js 22+ and pnpm 12+
- Python 3.11+
- A Gemini API key (free — get one at [aistudio.google.com](https://aistudio.google.com/app/apikey))

### 1. Clone and configure

```bash
git clone <repo-url>
cd buy-wise-ai-commerce-app

# Create your local env file from the template
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

### 2. Run the frontend (Next.js)

```bash
# Install (pnpm shim may need node path — see doc/PROGRESS.md if pnpm not found)
pnpm install
pnpm dev
# → http://localhost:3000
```

The frontend works immediately in mock mode (`NEXT_PUBLIC_USE_MOCKS=true` by default).
No backend required for demo/UI development.

### 3. Run the backend (FastAPI)

```bash
cd backend
pip install -r requirements.txt

# With GEMINI_API_KEY set in .env:
uvicorn main:app --reload --port 8000
# → http://localhost:8000/api/docs
```

### 4. Switch to live mode

In `.env`:
```
NEXT_PUBLIC_USE_MOCKS=false
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Then restart the frontend dev server.

---

## API documentation

When the backend is running, open: **http://localhost:8000/api/docs**

Key endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Liveness probe |
| `POST` | `/api/analyze-requirements` | Extract requirements from text |
| `POST` | `/api/research-products` | Run research pipeline (returns SSE stream URL) |
| `GET` | `/api/stream/{id}` | SSE progress events |
| `GET` | `/api/comparison/{id}` | Fetch stored comparison |
| `GET` | `/api/product/{id}` | Fetch product detail |
| `POST` | `/api/follow-up` | Ask follow-up question |

---

## Deployment (Vercel)

### Environment variables to set in Vercel dashboard

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google Gemini API key (server-side only) |
| `DATABASE_URL` | Supabase Postgres connection string |
| `SEARCH_API_KEY` | Free search API key |
| `ALLOWED_ORIGIN` | Your Vercel frontend URL (for CORS) |
| `NEXT_PUBLIC_USE_MOCKS` | `false` for production |
| `NEXT_PUBLIC_API_URL` | Your Vercel deployment URL |

### Deploy

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy (first time)
vercel --prod

# Set secrets (do not commit .env)
vercel env add GEMINI_API_KEY
vercel env add DATABASE_URL
```

> **[VERIFY]** Check current Vercel Hobby plan limits for Python function execution time and bundle size before deploying.

---

## Project structure

```
buy-wise-ai-commerce-app/
├── app/                    # Next.js app directory
│   ├── page.tsx            # Single-page app (all UI components)
│   ├── layout.tsx
│   └── globals.css
├── lib/
│   ├── types.ts            # Canonical TypeScript types (PRD §18)
│   ├── api.ts              # API client (mock/live switchable)
│   └── mock-data.ts        # Mock data for UI development
├── backend/
│   ├── main.py             # FastAPI app entry point
│   ├── requirements.txt
│   ├── agents/             # 8-agent pipeline
│   ├── api/                # Route handlers
│   ├── llm/                # LLM provider abstraction
│   ├── models/             # Pydantic schemas
│   ├── rag/                # RAG service (ingest, retrieve, rerank)
│   └── data/seed/          # Curated seed dataset (~15 laptop records)
├── doc/
│   ├── Buywise-PRD.md      # Full product requirements
│   ├── CONTEXT.md          # Handoff guide for next engineer/agent
│   ├── ARCHITECTURE.md     # System design and API contract
│   └── PROGRESS.md         # Step-by-step progress tracker
├── .env.example            # Env var names (no secrets)
├── vercel.json             # Vercel deployment config
└── next.config.mjs         # Next.js config
```

---

## Architecture overview

```
User Browser
  │
  ▼
Next.js (Vercel Hobby)  ──►  FastAPI (Vercel Python Functions)
                                  │
                    ┌─────────────┼────────────────────┐
                    ▼             ▼                    ▼
               Gemini API   Supabase pgvector    Seed Dataset
                            (free tier)          (laptops.json)
```

**8-agent pipeline:**
1. Requirement Analysis (Gemini JSON mode)
2. Product Research (seed dataset scoring)
3. Spec Verification (RAG + Gemini)
4. Review Analysis (RAG + Gemini, labeled as opinion)
5. Warranty & Return (rule-based + seed data)
6. Price & Value (seed data + budget matching)
7. Evidence Verification (rule-based + LLM)
8. Comparison (requirement matching + LLM narrative)

---

## Cost model

Everything runs on free tiers:
- **Vercel Hobby** — frontend + Python functions
- **Gemini API free tier** — ~15 RPM / 1,500 RPD **[VERIFY current limits]**
- **Supabase free tier** — Postgres + pgvector **[VERIFY row/storage limits]**
- No paid APIs in the current implementation

---

## [VERIFY] items before production

- [ ] Gemini API free tier: RPM/RPD limits, model names for JSON mode
- [ ] Supabase: pgvector on free plan, connection limits, row limits
- [ ] Vercel Hobby: Python function max execution time (60s?), bundle size
- [ ] Identify and add a free search API for product discovery (Step 6 extension)
- [ ] Review ToS for any data sources used in the seed dataset

---

## License

MIT — see LICENSE file.
