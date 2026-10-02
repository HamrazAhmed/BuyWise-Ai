# BuyWise AI — Context & Handoff Guide

> **Read this, PRD.md, ARCHITECTURE.md, and PROGRESS.md before changing anything.**
> **Update PROGRESS.md at the end of every session.**

---

## What the product is

BuyWise AI is an evidence-backed shopping decision assistant (hackathon MVP).
A user describes their needs in natural language; BuyWise converts them into structured,
editable requirements, researches candidate products, verifies specs against primary sources,
analyzes reviews and policies, and presents a transparent comparison with citations and
trade-offs. It never says "buy X"; it says which products satisfy which of *your*
requirements, and why.

**MVP focus:** laptops + selected consumer electronics.

---

## Hard constraints

| Rule | Detail |
|------|--------|
| **$0 budget** | Free tiers only: Gemini API free tier, Supabase free Postgres+pgvector, Vercel Hobby, free search/data options. Anything depending on current quotas/terms is marked **[VERIFY]** in docs. |
| **No secrets in git** | Keys only in env vars. `.env*` is gitignored. Only `.env.example` (names, no values) is committed. |
| **Untrusted content** | All retrieved web/product content is untrusted data. Prompt-injection defenses must be active (see PRD §19). |
| **No redesign** | Do NOT change the existing v0-generated visual design. Only fix build/type errors. |
| **MVP scope** | MUST HAVE first, then SHOULD HAVE. See PRD §24. |
| **Self-explanatory repo** | Quota may run out mid-session. Docs must let a new agent pick up from any point. |

---

## Technology stack

| Layer | Choice |
|-------|--------|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4, shadcn/ui |
| Backend | Python FastAPI (Vercel Python functions) |
| Orchestration | Async Python pipeline (no LangGraph) |
| DB + Vector | Supabase Postgres + pgvector (free); local fallback: Chroma/FAISS in-memory |
| LLM | Gemini API (free tier) via `LLMProvider` abstraction |
| Source control | GitHub |
| Deployment | Vercel Hobby (frontend + Python functions) |
| Package manager | pnpm (see `pnpm-lock.yaml`) |

---

## Routes

| Route | Component | Notes |
|-------|-----------|-------|
| `/` | `Home` | Landing page with NL input |
| `/start` | `Requirements` | Requirement review/editing (rewrite → `/`) |
| `/research` | `Research` | Progress stepper (rewrite → `/`) |
| `/results/[id]` | `Results` | Comparison dashboard (rewrite → `/`) |
| `/product/[id]` | `ProductDetail` | Product detail with evidence drawer |

All routes are rewrites to `/` in `next.config.mjs`; the single `page.tsx` does
client-side routing via `window.location.pathname`.

---

## Environment variables

| Variable | Where used | Notes |
|----------|-----------|-------|
| `GEMINI_API_KEY` | Backend only | Never in client bundle |
| `DATABASE_URL` | Backend only | Supabase connection string |
| `SEARCH_API_KEY` | Backend only | Free search API key |
| `NEXT_PUBLIC_USE_MOCKS` | Frontend + Backend | `true` = mock mode; `false` = live API |
| `NEXT_PUBLIC_API_URL` | Frontend | Base URL for FastAPI backend |
| `ALLOWED_ORIGIN` | Backend | CORS origin (frontend URL) |

---

## Key files

| File | Purpose |
|------|---------|
| `Doc/Buywise-PRD.md` | Full product requirements |
| `doc/ARCHITECTURE.md` | Architecture, agent pipeline, API contract, data model |
| `doc/PROGRESS.md` | Step-by-step checklist with status |
| `lib/types.ts` | Shared TypeScript types (PRD §18 contracts) |
| `lib/api.ts` | API client (mock-switchable via env flag) |
| `lib/mock-data.ts` | Mock data for frontend development |
| `backend/main.py` | FastAPI entry point |
| `backend/agents/` | 8-agent pipeline |
| `backend/llm/` | LLMProvider abstraction + GeminiProvider |
| `backend/rag/` | RAG service (retrieval, chunking, rerank) |
| `backend/models/` | Pydantic schemas |
| `.env.example` | Env var names only (no secrets) |

---

## Instructions for next session

1. Read `doc/PROGRESS.md` to find current step and status.
2. Read `doc/ARCHITECTURE.md` for the API contract and data model.
3. Read `Doc/Buywise-PRD.md` for full requirements.
4. Continue from "Next 5 steps" in `PROGRESS.md`.
5. Update `PROGRESS.md` when done.
6. Commit with a clear message after each step.
