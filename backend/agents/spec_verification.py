"""
backend/agents/spec_verification.py
Agent 3 — Specification Verification Agent.

Responsibilities:
- Verify CPU, GPU, RAM, storage, display, battery, ports, connectivity,
  weight, OS, upgradeability for each candidate product.
- Prefer manufacturer docs (primary sources).
- Flag conflicting values — show both, never silently choose one.
- Missing values → status='insufficient', value='unknown'.

PRD §10, §8 (F5), Agent 3.
"""

import logging
import time
from typing import Optional
from pydantic import BaseModel, Field

from models.product import Spec
from models.common import EvidenceStatus
from agents.base import AgentBase, RunState
from llm.gemini import wrap_context
from rag.retrieve import retrieve, chunks_to_context

logger = logging.getLogger(__name__)

# Key specs to verify per product (PRD §10, Agent 3)
SPEC_KEYS = [
    "CPU", "GPU", "RAM", "Storage", "Display",
    "Battery", "Weight", "OS/Linux support", "Upgradeability",
    "Ports", "Virtualization", "Warranty", "Return policy", "Price",
]


class SpecExtractionOutput(BaseModel):
    """LLM output schema for spec verification."""
    specs: list[dict] = Field(default_factory=list)
    # Each dict: {key, value, status, evidence_ids, conflicting_values?}


SPEC_VERIFICATION_PROMPT = """
You are verifying technical specifications for a laptop product.

PRODUCT: {product_name}
SPEC KEYS TO VERIFY: {spec_keys}

Based ONLY on the context below, extract the value for each spec key.
- If a spec is confirmed by a primary source, set status="verified".
- If confirmed by a secondary source only, set status="supported".
- If two sources conflict, set status="conflicting" and list both values in conflicting_values.
- If not found in context, set status="insufficient" and value="unknown".
- Do NOT invent values. Do NOT guess.

{context}

For each spec, output:
  key: the spec name
  value: the value found (or "unknown")
  status: verified | supported | conflicting | insufficient
  evidence_ids: list of source IDs from the context that support this value
  conflicting_values: (only if conflicting) list of {{value, source_url, source_type}}
"""


class SpecVerificationAgent(AgentBase):
    """
    Agent 3: Spec Verification.
    Runs per-product; meant to run in parallel with Agents 4-6.
    """

    name = "spec_verification"

    async def run(self, state: RunState) -> RunState:
        run = self._start_run(state)
        start = time.perf_counter()

        try:
            await state.emit_progress("Verifying specifications", step="spec_verification")

            import asyncio
            tasks = [
                self._verify_product(product, state)
                for product in state.candidate_products
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for product, result in zip(state.candidate_products, results):
                if isinstance(result, Exception):
                    logger.error("Spec verification failed for %s: %s", product.name, result)
                    # Provide empty specs rather than failing the whole pipeline
                    state.verified_specs[product.id] = []
                else:
                    state.verified_specs[product.id] = result

            self._finish_run(run, start)
        except Exception as e:
            self._fail_run(run, str(e), start)
            raise

        return state

    async def _verify_product(self, product, state: RunState) -> list[Spec]:
        """Verify specs for a single product using RAG + Gemini."""
        if self.llm is None:
            return self._specs_from_seed(product, state)

        # Retrieve relevant chunks (prefer primary sources)
        chunks = await retrieve(
            query=f"{product.name} specifications CPU RAM storage display battery",
            product_id=product.id,
            top_k=8,
            llm_provider=self.llm,
        )

        if not chunks:
            logger.warning("No RAG chunks for %s — using seed specs", product.name)
            return self._specs_from_seed(product, state)

        context = wrap_context(chunks_to_context(chunks))

        prompt = SPEC_VERIFICATION_PROMPT.format(
            product_name=product.name,
            spec_keys=", ".join(SPEC_KEYS),
            context=context,
        )

        try:
            output = await self.llm.generate_json(
                prompt=prompt,
                schema=SpecExtractionOutput,
                temperature=0.0,
            )
            return [self._dict_to_spec(s) for s in output.specs]
        except Exception as e:
            logger.error("Spec LLM call failed for %s: %s", product.name, e)
            return self._specs_from_seed(product, state)

    def _specs_from_seed(self, product, state: RunState) -> list[Spec]:
        """
        Build specs directly from seed data (fallback when RAG/LLM unavailable).
        Status is 'supported' since seed data is secondary-level confidence.
        """
        seed_candidates = getattr(state, "_seed_candidates", [])
        seed = next((c for c in seed_candidates if c["id"] == product.id), None)
        if not seed:
            return []

        raw_specs = seed.get("specs", {})
        specs = []
        for k, v in raw_specs.items():
            if v is None:
                specs.append(Spec(
                    key=k.replace("_", " ").title(),
                    value="unknown",
                    status=EvidenceStatus.insufficient,
                    evidence_ids=[],
                ))
            else:
                specs.append(Spec(
                    key=k.replace("_", " ").title(),
                    value=str(v),
                    status=EvidenceStatus.supported,
                    evidence_ids=[f"seed_{product.id}"],
                ))

        return specs

    def _dict_to_spec(self, d: dict) -> Spec:
        return Spec(
            key=d.get("key", "Unknown"),
            value=d.get("value", "unknown"),
            status=d.get("status", EvidenceStatus.insufficient),
            evidence_ids=d.get("evidence_ids", []),
            conflicting_values=d.get("conflicting_values", []),
        )
