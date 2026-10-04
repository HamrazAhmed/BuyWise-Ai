"""
backend/agents/warranty.py
Agent 5 — Warranty & Return Agent.

Responsibilities:
- Extract warranty duration, coverage, conditions.
- Extract return window and seller-dependence.
- Incomplete data → mark "seller-dependent / verify".

PRD §10, §8 (F7)
"""

import logging
import time
from typing import Optional
from pydantic import BaseModel, Field

from models.product import Warranty, ReturnPolicy
from agents.base import AgentBase, RunState

logger = logging.getLogger(__name__)


class WarrantyReturnOutput(BaseModel):
    warranty_months: Optional[int] = None
    warranty_coverage: Optional[str] = None
    warranty_conditions: Optional[str] = None
    return_window_days: Optional[int] = None
    return_conditions: Optional[str] = None
    seller_dependent: bool = True
    completeness: str = "unknown"  # 'complete' | 'partial' | 'unknown'


WARRANTY_PROMPT = """
You are extracting warranty and return policy information for a laptop.

PRODUCT: {product_name}

Extract:
- Warranty duration (in months)
- Warranty coverage description
- Warranty conditions (what's covered/excluded)
- Return window (days)
- Return conditions
- Whether return policy is seller-dependent

Based ONLY on this context. If not found, use null.

{context}
"""


class WarrantyAgent(AgentBase):
    """Agent 5: Warranty & Return Policy extraction."""

    name = "warranty"

    async def run(self, state: RunState) -> RunState:
        run = self._start_run(state)
        start = time.perf_counter()

        try:
            await state.emit_progress("Checking warranty & returns", step="warranty")

            import asyncio
            tasks = [
                self._extract_warranty(p, state)
                for p in state.candidate_products
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for product, result in zip(state.candidate_products, results):
                if isinstance(result, Exception):
                    logger.error("Warranty extraction failed for %s: %s", product.name, result)
                    state.warranties[product.id] = None
                else:
                    state.warranties[product.id] = result

            self._finish_run(run, start)
        except Exception as e:
            self._fail_run(run, str(e), start)
            raise

        return state

    async def _extract_warranty(self, product, state: RunState) -> tuple[Warranty, ReturnPolicy]:
        """Extract warranty and return policy from seed data or LLM."""
        if getattr(self.llm, "data_mode", None) == "fixture":
            from rag.retrieve import retrieve, chunks_to_context
            from llm.gemini import wrap_context
            chunks = await retrieve(query=f"{product.name} warranty return policy", product_id=product.id, llm_provider=self.llm, notices=state.notices)
            output = await self.llm.generate_json(WARRANTY_PROMPT.format(product_name=product.name, context=wrap_context(chunks_to_context(chunks))), WarrantyReturnOutput)
            return (Warranty(duration_months=output.warranty_months, coverage=output.warranty_coverage, conditions=output.warranty_conditions, source_id=f"{product.id}_policy", completeness=output.completeness),
                    ReturnPolicy(window_days=output.return_window_days, conditions=output.return_conditions, seller_dependent=output.seller_dependent, source_id=f"{product.id}_policy"))
        # Try seed data first
        seed_candidates = getattr(state, "_seed_candidates", [])
        seed = next((c for c in seed_candidates if c["id"] == product.id), None)

        if seed and seed.get('online'):
            return Warranty(completeness='unknown'), ReturnPolicy(conditions='No source-backed seller return policy found; confirm before purchase', seller_dependent=True)

        if seed and seed.get('market') == 'PK':
            from data.pakistan import RETURN_CONDITIONS
            return (Warranty(duration_months=seed['warranty_months'], coverage=seed['warranty_coverage'], conditions=seed['warranty_conditions'], completeness='partial', source_id=product.id + '__warranty'),
                    ReturnPolicy(window_days=None, conditions=RETURN_CONDITIONS, seller_dependent=True, source_id=product.id + '__returns'))

        warranty_months = None
        warranty_coverage = None

        if seed:
            warranty_months = seed.get("warranty_months")
            warranty_coverage = seed.get("warranty_coverage")

        warranty = Warranty(
            duration_months=warranty_months,
            coverage=warranty_coverage,
            conditions=None,
            completeness="partial" if warranty_months else "unknown",
        )
        return_policy = ReturnPolicy(
            window_days=None,
            conditions="Seller-dependent — verify before purchase",
            seller_dependent=True,
        )
        return warranty, return_policy
