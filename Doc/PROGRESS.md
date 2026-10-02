# BuyWise AI — Progress

> Updated after every session. Check "Next 5 steps" to know where to continue.
> Commands recorded in each step section.

---

## Step checklist

| Step | Description | Status | Commit |
|------|-------------|--------|--------|
| **Step 0** | Handoff docs (CONTEXT, ARCHITECTURE, PROGRESS, .env.example, .gitignore) | ✅ Done | `step-0: add handoff docs` |
| **Step 1** | Verify frontend (install, dev server, prod build) | ✅ Done | `step-1: frontend verified` |
| **Step 2** | Align types and API client (`lib/types.ts`, `lib/api.ts`, mock flag) | ✅ Done | `step-2: align types and api client` |
| **Step 3** | Backend foundation (FastAPI, health, CORS, validation, rate limit) | 🔲 Todo | — |
| **Step 4** | Requirement Analysis Agent + `/api/analyze-requirements` | 🔲 Todo | — |
| **Step 5** | Data + RAG (seed dataset, pgvector/Chroma, ingestion, retrieval, rerank) | 🔲 Todo | — |
| **Step 6** | Agents 2–8 + full pipeline + SSE + caching | 🔲 Todo | — |
| **Step 7** | Follow-up + Regenerate (`/api/follow-up`, chat panel, budget regen) | 🔲 Todo | — |
| **Step 8** | Hardening (error handling PRD §21, secure headers §19, quota guard, demo cache) | 🔲 Todo | — |
| **Step 9** | Deployment prep (vercel.json, README, Definition of Done check) | 🔲 Todo | — |

---

## Step 0 — Handoff docs

**Status:** ✅ Done

**Files created:**
- `doc/CONTEXT.md` — product description, rules, stack, routes, env vars, key files
- `doc/ARCHITECTURE.md` — 8-agent pipeline, backend folder structure, API contract, data model
- `doc/PROGRESS.md` — this file
- `.env.example` — env var names only
- `.gitignore` updated — added `.env` (all variants)

---

## Step 1 — Frontend verification

**Status:** ✅ Done

**Package manager detected:** `pnpm` (from `pnpm-lock.yaml`, `"packageManager": "pnpm@12.3.4"`)

**Commands run:**
```powershell
pnpm install
pnpm run build
pnpm run dev
```

**Result:** Build passes (TypeScript errors ignored via `ignoreBuildErrors: true` in `next.config.mjs`). Dev server runs on http://localhost:3000.

**Notes:**
- Single-page app in `app/page.tsx` doing client-side routing via `window.location.pathname`
- Routes `/start`, `/research`, `/results/:id`, `/product/:id` are URL rewrites to `/` in `next.config.mjs`
- All mock data in `lib/mock-data.ts`; API client in `lib/api.ts` wraps mock functions

---

## Step 2 — Types and API client

**Status:** ✅ Done

**Files created/modified:**
- `lib/types.ts` — canonical TypeScript types matching PRD §18 contracts (Requirement, Product, Spec, Evidence, Comparison, etc.)
- `lib/api.ts` — expanded with real API calls + mock fallback, switched via `NEXT_PUBLIC_USE_MOCKS`
- `lib/mock-data.ts` — unchanged (still used when mocks are on)

**Mock mode:** Set `NEXT_PUBLIC_USE_MOCKS=true` (default) to use mock data. Set to `false` to hit the real backend at `NEXT_PUBLIC_API_URL`.

---

## Step 3 — Backend foundation

**Status:** 🔲 Todo

**Planned files:**
- `backend/main.py`
- `backend/requirements.txt`
- `backend/api/health.py`
- `backend/llm/base.py`, `backend/llm/gemini.py`
- `backend/models/common.py`
- `vercel.json`

**Needs from user before going live:**
- `GEMINI_API_KEY` — get from https://aistudio.google.com/app/apikey (free)
- `DATABASE_URL` — Supabase project connection string (free at supabase.com)

---

## Step 4 — Requirement Analysis Agent

**Status:** 🔲 Todo

---

## Step 5 — Data + RAG

**Status:** 🔲 Todo

**Seed dataset target:** ~15–20 laptop records with source URLs, source types, real specs (no invented prices; unknown → null).

---

## Step 6 — Agents and pipeline

**Status:** 🔲 Todo

---

## Step 7 — Follow-up and Regenerate

**Status:** 🔲 Todo

---

## Step 8 — Hardening

**Status:** 🔲 Todo

---

## Step 9 — Deployment prep

**Status:** 🔲 Todo

---

## Notes & decisions

- `next.config.mjs` has `ignoreBuildErrors: true` — leave it; v0-generated code has type issues that are cosmetic, not blocking.
- The single `app/page.tsx` contains all components inline (v0 style). Don't refactor unless needed.
- `doc/` (lowercase) is the new home for docs; original PRD is in `Doc/` (capital D) — both exist, don't move the PRD.
- `pnpm-workspace.yaml` exists but is empty (no monorepo packages yet). Backend will be a separate Python project.
- Mock mode default is `true` so the UI works at all times without a backend.

---

## [VERIFY] items

- [ ] Gemini API: free RPM/RPD limits, model names for JSON mode and embeddings
- [ ] Supabase: pgvector on free plan, row limits, connection string format
- [ ] Vercel Hobby: Python function max execution time (60s?), max bundle size
- [ ] Search API: identify which free API to use for product discovery
- [ ] Render free tier: cold-start time, exec limits (fallback backend option)

---

## Next 5 steps

1. **Step 3a** — Create `backend/main.py` with FastAPI, CORS, health route, error handlers
2. **Step 3b** — Add `backend/llm/base.py` (LLMProvider interface) + `backend/llm/gemini.py` (GeminiProvider stub)
3. **Step 3c** — Add `backend/models/common.py` (Pydantic schemas for error responses, evidence status)
4. **Step 3d** — Add `backend/requirements.txt` and `vercel.json`
5. **Step 4** — Implement Requirement Analysis Agent and `POST /api/analyze-requirements`
