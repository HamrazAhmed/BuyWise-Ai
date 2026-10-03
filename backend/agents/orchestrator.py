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
  When GEMINI_API_KEY is absent (MockLLMProvider), ALL requests return the
  demo comparison so the full UI flow works without any API key.
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
from rag.ingest import ingest_seed_data
from data.demo_cache import build_demo_comparison, DEMO_REQUIREMENTS

logger = logging.getLogger(__name__)

# ─── Simple in-memory result cache ────────────────────────────────────────────
# Keyed by hash of (requirements). Per-process; cleared on cold-start.
# For production, use Supabase to persist across cold-starts.

_comparison_cache: dict[str, Comparison] = {}

# Comparison objects keyed by comparison_id
_comparison_store: dict[str, Comparison] = {}

# Seed ingestion flag (run once per process startup)
_seed_ingested = False

# Pre-warm: compute the demo requirements hash at import time
_DEMO_REQ_HASH = None


def _requirements_hash(requirements: list[Requirement]) -> str:
    """Deterministic hash of requirements list for caching."""
    req_data = [
        {"key": r.key, "operator": r.operator, "value": r.value, "priority": r.priority}
        for r in sorted(requirements, key=lambda r: r.key)
    ]
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
) -> Comparison:
    """
    Run the full multi-agent pipeline and return a Comparison.

    :param request_id: Unique ID for this research session.
    :param requirements: Confirmed requirements from Agent 1.
    :param raw_text: Original user text (for context).
    :param progress_callback: Async callable for SSE progress events.
    :returns: Comparison result.
    """
    # Check cache first
    req_hash = _requirements_hash(requirements)
    if req_hash in _comparison_cache:
        logger.info("Cache hit for requirements hash %s", req_hash)
        cached = _comparison_cache[req_hash]
        _comparison_store[cached.id] = cached
        return cached

    llm = get_llm_provider()

    # ── Demo cache / mock mode fallback (PRD §23, §29) ────────────────────────
    # If running without a real LLM key, or if this matches the demo scenario,
    # return the pre-warmed demo comparison instantly.
    global _DEMO_REQ_HASH
    if _DEMO_REQ_HASH is None:
        _DEMO_REQ_HASH = _requirements_hash(DEMO_REQUIREMENTS)

    is_mock = isinstance(llm, MockLLMProvider)
    is_demo_query = req_hash == _DEMO_REQ_HASH

    if is_mock or is_demo_query:
        logger.info(
            "Using pre-warmed demo comparison (%s)",
            "mock mode" if is_mock else "demo query match",
        )
        if progress_callback:
            await progress_callback({"type": "status", "message": "Understanding requirements", "step": "requirements"})
            await asyncio.sleep(0.3)
            await progress_callback({"type": "status", "message": "Finding products", "step": "research"})
            await asyncio.sleep(0.3)
            await progress_callback({"type": "status", "message": "Verifying specifications", "step": "specs"})
            await asyncio.sleep(0.3)
            await progress_callback({"type": "status", "message": "Analyzing reviews", "step": "reviews"})
            await asyncio.sleep(0.3)
            await progress_callback({"type": "status", "message": "Checking warranty & pricing", "step": "warranty"})
            await asyncio.sleep(0.3)
            await progress_callback({"type": "status", "message": "Verifying evidence", "step": "evidence"})
            await asyncio.sleep(0.3)
            await progress_callback({"type": "status", "message": "Building comparison", "step": "comparison"})
            await asyncio.sleep(0.2)

        demo = build_demo_comparison(request_id=request_id)
        _comparison_cache[req_hash] = demo
        _comparison_store[demo.id] = demo

        if progress_callback:
            await progress_callback({"type": "status", "message": "Research complete", "step": "done"})
        return demo

    await _ensure_seed_ingested(llm)

    # Initialize shared state
    state = RunState(
        request_id=request_id,
        raw_text=raw_text,
        requirements=requirements,
        _progress_callback=progress_callback,
    )

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

    # Cache the result
    _comparison_cache[req_hash] = state.comparison
    _comparison_store[state.comparison.id] = state.comparison

    await state.emit_progress("Research complete", step="done")

    logger.info(
        "Pipeline complete: comparison_id=%s, products=%d, agent_runs=%d",
        state.comparison.id,
        len(state.candidate_products),
        len(state.agent_runs),
    )

    return state.comparison


def get_comparison(comparison_id: str) -> Optional[Comparison]:
    """Retrieve a stored comparison by ID."""
    return _comparison_store.get(comparison_id)


def store_comparison(comparison: Comparison) -> None:
    """Store a comparison (used after loading from DB)."""
    _comparison_store[comparison.id] = comparison
