"""
backend/agents/comparison.py
Agent 8 — Comparison & Decision Support Agent.

Responsibilities:
- Build the comparison table (requirement match matrix).
- Generate per-requirement analysis.
- Produce trade-off narrative ("what changes if priorities change").
- Never say "objectively best" — always relative to user requirements.
- LLM failure → deterministic table without narrative.

PRD §10, §8 (F10), Agent 8.
"""

import logging
import time
from typing import Optional
from pydantic import BaseModel, Field

from models.request import Requirement
from models.product import Product, Spec
from models.comparison import Comparison, RequirementAnalysis, ProductAssessment
from models.common import EvidenceStatus
from agents.base import AgentBase, RunState
from llm.gemini import wrap_context, get_strong_llm
from llm.base import LLMError

logger = logging.getLogger(__name__)


# ─── Requirement matching rules ───────────────────────────────────────────────

def _match_requirement(req: Requirement, specs: list[Spec]) -> tuple[str, str, list[str]]:
    """
    Rule-based requirement matching.
    Returns (match_symbol, explanation, evidence_ids).
    match_symbol: '✓' | '✕' | '?'
    """
    key_lower = req.key.lower().replace("_", " ").replace("-", " ")
    value_lower = req.value.lower()

    # Find relevant spec
    matching_spec = None
    for spec in specs:
        spec_key_lower = spec.key.lower().replace("_", " ")
        if (key_lower in spec_key_lower or spec_key_lower in key_lower or
                # Common aliases
                (key_lower == "ram" and "ram" in spec_key_lower) or
                (key_lower == "memory" and "ram" in spec_key_lower) or
                (key_lower in ("linux", "os compatibility", "os_compatibility") and "linux" in spec_key_lower) or
                (key_lower == "virtualization" and "virtualization" in spec_key_lower) or
                (key_lower == "upgradeability" and "upgrade" in spec_key_lower)):
            matching_spec = spec
            break

    if matching_spec is None:
        return "?", f"No data found for '{req.key}'", []

    val = matching_spec.value.lower()
    ev_ids = matching_spec.evidence_ids

    if matching_spec.status == EvidenceStatus.insufficient:
        return "?", f"'{req.key}' data is insufficient to verify", ev_ids

    if matching_spec.status == EvidenceStatus.conflicting:
        return "?", f"'{req.key}' has conflicting information across sources", ev_ids

    # Budget check
    if key_lower == "budget":
        try:
            req_val = float(value_lower.replace("usd", "").replace("$", "").replace(",", "").strip())
            spec_val_str = "".join(c for c in val if c.isdigit() or c == ".")
            if spec_val_str:
                spec_val = float(spec_val_str)
                if req.operator in ("<=", "<") and spec_val <= req_val:
                    return "✓", f"${spec_val:,.0f} is within the ${req_val:,.0f} budget", ev_ids
                elif req.operator in ("<=", "<"):
                    return "✕", f"${spec_val:,.0f} exceeds the ${req_val:,.0f} budget", ev_ids
        except ValueError:
            pass
        return "?", "Price not confirmed", ev_ids

    # RAM check
    if key_lower in ("ram", "memory"):
        try:
            req_val = float("".join(c for c in value_lower if c.isdigit()))
            spec_val_str = "".join(c for c in val if c.isdigit())
            if spec_val_str:
                spec_val = float(spec_val_str)
                if req.operator in (">=", ">") and spec_val >= req_val:
                    return "✓", f"{spec_val:.0f}GB RAM meets the ≥{req_val:.0f}GB requirement", ev_ids
                elif req.operator in (">=", ">"):
                    return "✕", f"{spec_val:.0f}GB RAM does not meet the ≥{req_val:.0f}GB requirement", ev_ids
        except ValueError:
            pass

    # Linux / OS check
    if key_lower in ("linux", "os compatibility", "os_compatibility", "linux compatibility"):
        if any(w in val for w in ["native", "certified", "strong", "excellent"]):
            return "✓", f"Linux support: {matching_spec.value}", ev_ids
        elif "partial" in val or "mixed" in val:
            return "?", f"Linux support is partial: {matching_spec.value}", ev_ids
        elif "none" in val or "not" in val:
            return "✕", f"Does not support Linux: {matching_spec.value}", ev_ids

    # Virtualization check
    if "virtualization" in key_lower:
        if matching_spec.value and "not supported" not in val:
            return "✓", f"Virtualization: {matching_spec.value}", ev_ids
        else:
            return "✕", "Virtualization not confirmed as supported", ev_ids

    # Upgradeability check
    if "upgrade" in key_lower:
        if "+" in val or "upgradeable" in val or ("ram" in val and "ssd" in val):
            return "✓", f"Upgradeable: {matching_spec.value}", ev_ids
        elif "soldered" in val or "not upgradeable" in val:
            return "✕", "RAM is soldered (not upgradeable)", ev_ids

    # Generic: if we have a value, assume it's present
    if val and val != "unknown":
        return "✓", f"{req.key}: {matching_spec.value}", ev_ids

    return "?", f"'{req.key}' could not be confirmed", ev_ids


# ─── Narrative generation ─────────────────────────────────────────────────────

COMPARISON_NARRATIVE_PROMPT = """
You are writing a comparison analysis for a shopping decision assistant.

USER REQUIREMENTS: {requirements_text}

PRODUCTS BEING COMPARED: {product_names}

REQUIREMENT MATCH RESULTS:
{match_results}

Write 3-5 concise trade-off sentences about what each product does well and what it misses,
relative to the user's stated requirements. 

RULES:
- Never say "objectively best" or "universally recommended".
- Always frame comparisons relative to the user's specific requirements.
- Language: "Based on your requirements, X satisfies Y because Z."
- Be factual and direct. No marketing language.
- If a claim is uncertain, say so.
"""


class NarrativeOutput(BaseModel):
    tradeoffs: list[str] = Field(default_factory=list, max_length=7)


# ─── Agent ────────────────────────────────────────────────────────────────────

class ComparisonAgent(AgentBase):
    """
    Agent 8: Comparison & Decision Support.
    Produces the final comparison result used by the dashboard.
    """

    name = "comparison"

    async def run(self, state: RunState) -> RunState:
        run = self._start_run(state)
        start = time.perf_counter()

        try:
            await state.emit_progress("Generating comparison", step="comparison")

            # Step 1: Build requirement match matrix (deterministic, rule-based)
            requirement_matches: dict[str, list[str]] = {}
            requirement_analyses: list[RequirementAnalysis] = []

            for product in state.candidate_products:
                specs = state.verified_specs.get(product.id, [])
                matches = []
                assessments = []

                for req in state.requirements:
                    match, explanation, ev_ids = _match_requirement(req, specs)
                    matches.append(match)
                    assessments.append(ProductAssessment(
                        product_id=product.id,
                        match=match,
                        explanation=explanation,
                        evidence_ids=ev_ids,
                    ))

                requirement_matches[product.id] = matches

                # Build product score
                met = sum(1 for m in matches if m == "✓")
                total = len(state.requirements)
                product.score = f"{met} of {total} requirements met"

                # Add verified specs to product
                product.specs = state.verified_specs.get(product.id, [])

                # Add price info
                price_data = state.prices.get(product.id, {})
                if price_data:
                    product.price_info = price_data.get("price_info")
                    price_val = product.price_info.amount if product.price_info else None
                    product.price = price_val  # type: ignore[attr-defined]

                # Add warranty
                warranty_data = state.warranties.get(product.id)
                if warranty_data:
                    product.warranty, product.return_policy = warranty_data

                # Add reviews
                product.review_themes = state.review_themes.get(product.id, [])

                # Build pros/limitations from match results
                product.pros = [a.explanation for a in assessments if a.match == "✓"][:3]
                product.limitations = [a.explanation for a in assessments if a.match == "✕"][:3]

            # Step 2: Generate narrative (LLM), fallback to deterministic
            tradeoffs = await self._generate_narrative(state, requirement_matches)

            # Step 3: Build final Comparison object
            state.comparison = Comparison(
                request_id=state.request_id,
                products=state.candidate_products,
                requirement_matches=requirement_matches,
                tradeoffs=tradeoffs,
                requirement_analysis=requirement_analyses,
            )

            self._finish_run(run, start)
        except Exception as e:
            self._fail_run(run, str(e), start)
            raise

        return state

    async def _generate_narrative(
        self,
        state: RunState,
        requirement_matches: dict[str, list[str]],
    ) -> list[str]:
        """
        Generate trade-off narrative with LLM.
        Falls back to deterministic sentences if LLM fails.
        """
        if self.llm is None:
            return self._deterministic_tradeoffs(state, requirement_matches)

        requirements_text = "; ".join(
            f"{r.key} {r.operator} {r.value} ({r.priority})"
            for r in state.requirements
        )
        product_names = ", ".join(p.name for p in state.candidate_products)

        match_lines = []
        for product in state.candidate_products:
            matches = requirement_matches.get(product.id, [])
            for req, match in zip(state.requirements, matches):
                match_lines.append(f"  {product.name} | {req.key}: {match}")

        prompt = COMPARISON_NARRATIVE_PROMPT.format(
            requirements_text=requirements_text,
            product_names=product_names,
            match_results="\n".join(match_lines),
        )

        try:
            # Use strong model for final narrative (Agent 8)
            strong_llm = get_strong_llm()
            output = await strong_llm.generate_json(
                prompt=prompt,
                schema=NarrativeOutput,
                temperature=0.2,
            )
            return output.tradeoffs
        except LLMError as e:
            logger.warning("Narrative generation failed (%s) — using deterministic fallback", e)
            return self._deterministic_tradeoffs(state, requirement_matches)

    def _deterministic_tradeoffs(
        self,
        state: RunState,
        requirement_matches: dict[str, list[str]],
    ) -> list[str]:
        """
        Generate basic trade-off sentences without LLM.
        Used when LLM is unavailable (PRD: "deterministic table without narrative").
        """
        lines = []
        for product in state.candidate_products:
            matches = requirement_matches.get(product.id, [])
            met = [r.key for r, m in zip(state.requirements, matches) if m == "✓"]
            missed = [r.key for r, m in zip(state.requirements, matches) if m == "✕"]
            uncertain = [r.key for r, m in zip(state.requirements, matches) if m == "?"]

            parts = [f"Based on your requirements, {product.name}"]
            if met:
                parts.append(f"satisfies: {', '.join(met)}")
            if missed:
                parts.append(f"does not satisfy: {', '.join(missed)}")
            if uncertain:
                parts.append(f"has uncertain data for: {', '.join(uncertain)}")
            lines.append(". ".join(parts) + ".")

        return lines
