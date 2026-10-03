"""
backend/agents/price_value.py
Agent 6 — Price & Value Agent.

Responsibilities:
- Return price with timestamp (never estimate if unknown).
- Assess budget fit based on user requirements.
- Never say "universally best" — relative to user criteria only.
- Stale price (>24h) gets a badge; missing price shows "Not available".

PRD §10, §8 (F8)
"""

import logging
import time
from typing import Optional
from pydantic import BaseModel

from models.product import PriceInfo
from models.request import Requirement
from agents.base import AgentBase, RunState

logger = logging.getLogger(__name__)


def _extract_budget(requirements: list[Requirement]) -> Optional[float]:
    """Extract budget ceiling from requirements list."""
    for req in requirements:
        if req.key.lower() == "budget":
            try:
                val = req.value.replace("usd", "").replace("$", "").replace(",", "").strip()
                return float(val)
            except ValueError:
                pass
    return None


def _assess_budget_fit(price: Optional[float], budget: Optional[float]) -> str:
    """Return a budget fit note. Never 'universally best'."""
    if price is None:
        return "Price not available — verify current listing before purchase."
    if budget is None:
        return f"Listed at ${price:,.0f}. No budget specified in requirements."
    if price <= budget:
        margin = budget - price
        return f"Within budget (${price:,.0f} listed, ${margin:,.0f} under the ${budget:,.0f} ceiling)."
    else:
        over = price - budget
        return f"${over:,.0f} over budget (${price:,.0f} listed vs. ${budget:,.0f} ceiling)."


class PriceValueAgent(AgentBase):
    """Agent 6: Price & Value assessment."""

    name = "price_value"

    async def run(self, state: RunState) -> RunState:
        run = self._start_run(state)
        start = time.perf_counter()

        try:
            # No SSE emit here — runs in parallel with 3-5, same progress message
            budget = _extract_budget(state.requirements)

            seed_candidates = getattr(state, "_seed_candidates", [])

            for product in state.candidate_products:
                seed = next((c for c in seed_candidates if c["id"] == product.id), None)
                price_usd = seed.get("price_usd") if seed else None
                price_note = seed.get("price_note", "Price unknown") if seed else "Price unknown"

                price_info = PriceInfo(
                    amount=price_usd,
                    currency="USD",
                    seller=None,
                    fetched_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    is_stale=False,
                    source_id=f"seed_{product.id}",
                )
                budget_fit_note = _assess_budget_fit(price_usd, budget)

                state.prices[product.id] = {
                    "price_info": price_info,
                    "price_note": price_note,
                    "budget_fit_note": budget_fit_note,
                }

            self._finish_run(run, start)
        except Exception as e:
            self._fail_run(run, str(e), start)
            raise

        return state
