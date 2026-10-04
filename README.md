# BuyWise AI

Evidence-backed laptop shopping assistant built with Next.js, FastAPI, Gemini and RAG. Users confirm extracted requirements, research candidates, inspect scoped citations, compare selected products and regenerate from budget changes or follow-up questions.

Backend, frontend, live Gemini and hosted Supabase checks passed. Deployment verification remains pending. See the [PRD](Doc/Buywise-PRD.md) for product requirements.

Current Pakistan catalog has three attributed Paklap SKUs. Blocked refreshes retain stale/undated snapshots; unknown reviews, manufacturer verification, warranty durations and return windows remain explicit. This is bounded coverage, not a complete market search.

## Setup

Install frontend dependencies with pnpm and backend requirements in a Python virtual environment. Copy `.env.example` to `.env` only for a fresh setup; preserve existing keys. Gemini credentials stay server-side. Fixture mode needs no credentials; Gemini mode uses real extraction and semantic embeddings.

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
pnpm install
.venv/bin/python -m uvicorn main:app --app-dir backend --env-file .env --reload --port 8000
```

In another terminal, run `pnpm dev`. Default API URL is localhost:8000; frontend defaults to real backend calls. Set BUYWISE_MODE=fixture for synthetic test data or gemini for live provider calls. Local storage defaults to ignored `.local/runtime.sqlite3`. DATABASE_URL activates shared PostgreSQL/pgvector.

## API

Open `/api/docs` on the API host. Endpoints include `/api/health`, `/api/ready`, `/api/analyze-requirements`, `/api/research-products`, `/api/research-status/{id}`, `/api/stream/{id}`, `/api/comparison/{id}`, `/api/product/{id}?comparison_id=...` and `/api/follow-up`.

## Hosting and checks

Vercel configuration deploys Next.js only. FastAPI and a separate persistent worker connect to shared PostgreSQL. Hosted Supabase migrations, pgvector queries and job recovery have been verified. Set the public external API URL at frontend build time; database and Gemini keys belong on API/worker hosts. Deployment and the separate production Gemini key are pending.

Run migrations with `PYTHONPATH=backend .venv/bin/python -m data.runtime`. For a separate worker, set `BUYWISE_INLINE_WORKER=false` on API and worker, then run `PYTHONPATH=backend .venv/bin/python -m worker`. Both services require the same database and Gemini configuration.

Run backend checks with `.venv/bin/python -m unittest discover -s tests -q` and the frontend contract check with `node scripts/check_api_contract.mjs`. Build with `pnpm exec next build --webpack`. Never point `P6_TEST_DATABASE_URL` at a client database: those tests clear runtime tables. Live checks consume Gemini quota; browser scripts require their local QA ports and saved results.

Backend code lives in `backend/`; UI in `app/` and `lib/`; regression/browser checks in `tests/` and `scripts/`. Internal planning and reports stay local and are ignored by Git.

MIT — see LICENSE.
