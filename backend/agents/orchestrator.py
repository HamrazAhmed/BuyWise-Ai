"""
backend/agents/orchestrator.py
Async pipeline orchestrator for the BuyWise AI multi-agent system.

Pipeline (PRD §10):
1. [Sequential] Requirement Agent
2. [Sequential] Product Research Agent
3. [Parallel per product] Spec Verification + Review Analysis + Warranty + Price
4. [Sequential] Evidence Verification Agent
5. [Sequential] Comparison Agent

SSE progress events are emitted at each stage via state.emit_progress().
Results are cached by (request_id + requirements hash) to avoid repeated research.

Demo cache (PRD §23, §29):
  Pre-warmed comparison for the demo scenario is loaded on first request.
  Legacy auto/no-key and explicit demo mode return labeled canned results.
  Explicit fixture mode executes the pipeline on synthetic source records.
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Any, Callable, Coroutine, Optional

from agents.base import RunState
from agents.research import ProductResearchAgent
from agents.spec_verification import SpecVerificationAgent
from agents.review_analysis import ReviewAnalysisAgent
from agents.warranty import WarrantyAgent
from agents.price_value import PriceValueAgent
from agents.evidence import EvidenceVerificationAgent
from agents.comparison import ComparisonAgent
from llm.gemini import get_llm_provider, MockLLMProvider
from models.comparison import Comparison
from models.request import Requirement
from uuid import uuid4
from rag.ingest import ingest_seed_data
from data.demo_cache import build_demo_comparison, DEMO_REQUIREMENTS

logger = logging.getLogger(__name__)

# ─── Simple in-memory result cache ────────────────────────────────────────────
# Keyed by hash of (requirements). Per-process; cleared on cold-start.
# For production, use Supabase to persist across cold-starts.

# ponytail: process-local cache; shared durable storage is P6 work.
_comparison_cache: dict[str, tuple[float, Comparison]] = {}
CACHE_TTL_SECONDS = 3600
MAX_STORED_COMPARISONS = 100

# Comparison objects keyed by comparison_id
_comparison_store: dict[str, Comparison] = {}

# Seed ingestion flag (run once per process startup)
_seed_ingested = False



def _requirements_hash(requirements: list[Requirement]) -> str:
    """Deterministic hash of requirements list for caching."""
    req_data = [r.model_dump(mode="json") for r in requirements]
    return hashlib.sha256(json.dumps(req_data, sort_keys=True).encode()).hexdigest()[:16]


async def _ensure_seed_ingested(llm_provider) -> None:
    """Ingest seed data once per process startup."""
    global _seed_ingested
    if not _seed_ingested:
        try:
            count = await ingest_seed_data(llm_provider)
            logger.info("Seed data ingested: %d chunks", count)
            _seed_ingested = True
        except Exception as e:
            logger.error("Seed ingestion failed (non-fatal): %s", e)


# ─── Main pipeline ─────────────────────────────────────────────────────────────

async def run_pipeline(
    request_id: str,
    requirements: list[Requirement],
    raw_text: str = "",
    progress_callback: Optional[Callable] = None,
    comparison_id: Optional[str] = None,
    persist: bool = True,
) -> Comparison:
    """
    Run the full multi-agent pipeline and return a Comparison.

    :param request_id: Unique ID for this research session.
    :param requirements: Confirmed requirements from Agent 1.
    :param raw_text: Original user text (for context).
    :param progress_callback: Async callable for SSE progress events.
    :returns: Comparison result.
    """
    llm = get_llm_provider()
    try:
        is_mock = isinstance(llm, MockLLMProvider)
        comparison_id = comparison_id or str(uuid4())
        req_hash = hashlib.sha256(json.dumps({
            "version": 6, "market": os.getenv('BUYWISE_MARKET', 'PK'), "requirements": _requirements_hash(requirements),
            "raw_text": raw_text, "mode": getattr(llm, "data_mode", "demo" if is_mock else "live"),
            "model": getattr(llm, "model", "mock"),
        }, sort_keys=True).encode()).hexdigest()
        now = time.monotonic()
        for key in list(_comparison_cache):
            if now - _comparison_cache[key][0] >= CACHE_TTL_SECONDS:
                del _comparison_cache[key]
        if req_hash in _comparison_cache:
            result = _comparison_cache[req_hash][1].model_copy(deep=True)
            result.id, result.request_id = comparison_id, request_id
            if persist: store_comparison(result)
            return result

        if is_mock:
            logger.info(
                "Using pre-warmed demo comparison (%s)",
                "mock mode",
            )
            if progress_callback:
                await progress_callback({"type": "status", "message": "Loading canned demo data; no live research", "step": "demo"})

            demo = build_demo_comparison(request_id=request_id)
            demo.id = comparison_id
            demo.requirements = [r.model_copy(deep=True) for r in DEMO_REQUIREMENTS]
            demo.data_mode = "demo"
            demo.notices = ["Canned example comparison; no live research performed. Prices, claims and requirements are demo data."]
            _cache_result(req_hash, demo)
            if persist: store_comparison(demo)

            if progress_callback:
                await progress_callback({"type": "status", "message": "Demo comparison ready", "step": "done"})
            return demo

        is_fixture = getattr(llm, "data_mode", None) == "fixture"
        if is_fixture:
            from llm.fixture import ingest_fixtures
            await ingest_fixtures(llm)
        else:
            # Regional source ingestion runs in research so notices travel with results.
            if os.getenv('BUYWISE_MARKET', 'PK') != 'PK':
                await _ensure_seed_ingested(llm)

        # Initialize shared state
        state = RunState(
            request_id=request_id,
            comparison_id=comparison_id,
            raw_text=raw_text,
            requirements=requirements,
            _progress_callback=progress_callback,
        )

        if is_fixture:
            # Exercise extraction without overwriting user-confirmed edits.
            from agents.requirement import RequirementAgent
            analysis_state = RunState(raw_text=raw_text or "I need a laptop", _progress_callback=progress_callback)
            await RequirementAgent(llm=llm).run_on_state(analysis_state)
            if analysis_state.category != "laptop":
                raise ValueError("Fixture mode supports laptops only")
            state.agent_runs.extend(analysis_state.agent_runs)

        # ── Stage 1: Product Research (sequential) ────────────────────────────────
        research_agent = ProductResearchAgent(llm=llm)
        state = await research_agent.run(state)

        if not state.candidate_products:
            raise RuntimeError("No candidate products found. Try broadening your requirements.")

        # ── Stage 2: Per-product agents (parallel) ────────────────────────────────
        # Agents 3–6 run concurrently per product to minimize latency.
        # They share state but each writes to different keys (product_id-keyed dicts).

        await state.emit_progress("Verifying specifications and analyzing reviews", step="parallel")

        spec_agent = SpecVerificationAgent(llm=llm)
        review_agent = ReviewAnalysisAgent(llm=llm)
        warranty_agent = WarrantyAgent(llm=llm)
        price_agent = PriceValueAgent(llm=llm)

        # Run all four in parallel
        await asyncio.gather(
            spec_agent.run(state),
            review_agent.run(state),
            warranty_agent.run(state),
            price_agent.run(state),
        )

        # ── Stage 3: Evidence Verification (sequential) ────────────────────────────
        evidence_agent = EvidenceVerificationAgent(llm=llm)
        state = await evidence_agent.run(state)

        # ── Stage 4: Comparison (sequential) ──────────────────────────────────────
        comparison_agent = ComparisonAgent(llm=llm)
        state = await comparison_agent.run(state)

        if state.comparison is None:
            raise RuntimeError("Comparison agent failed to produce a result.")

        state.comparison.result_json = {"agent_runs": [r.model_dump(mode="json") for r in state.agent_runs], "evidence_version": 1}
        if is_fixture:
            state.comparison.data_mode = "fixture"
            state.comparison.notices = list(dict.fromkeys(state.notices)) + ["Synthetic local fixtures; no live AI or commercial research. Lexical embeddings test retrieval plumbing only."]
        else:
            state.comparison.notices = list(dict.fromkeys(state.notices))

        # Cache the result
        _cache_result(req_hash, state.comparison)
        if persist: store_comparison(state.comparison)

        await state.emit_progress("Research complete", step="done")

        logger.info(
            "Pipeline complete: comparison_id=%s, products=%d, agent_runs=%d",
            state.comparison.id,
            len(state.candidate_products),
            len(state.agent_runs),
        )

        return state.comparison

    finally:
        if hasattr(llm, "aclose"):
            await llm.aclose()


def get_comparison(comparison_id: str) -> Optional[Comparison]:
    """Retrieve a stored comparison by ID."""
    from data.runtime import ensure, load_comparison
    ensure()
    return load_comparison(comparison_id)


def store_comparison(comparison: Comparison) -> None:
    """Store a comparison (used after loading from DB)."""
    from data.runtime import ensure, save_comparison
    ensure()
    save_comparison(comparison)
    _comparison_store[comparison.id] = comparison.model_copy(deep=True)
    while len(_comparison_store) > MAX_STORED_COMPARISONS:
        del _comparison_store[next(iter(_comparison_store))]


def _cache_result(key: str, comparison: Comparison) -> None:
    _comparison_cache[key] = (time.monotonic(), comparison.model_copy(deep=True))
    while len(_comparison_cache) > MAX_STORED_COMPARISONS:
        del _comparison_cache[next(iter(_comparison_cache))]


def get_request_comparison(request_id: str) -> Optional[Comparison]:
    from data.runtime import ensure, load_comparison
    ensure()
    return load_comparison(request_id, by_request=True)
