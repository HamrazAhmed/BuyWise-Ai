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

from models.product import Spec
from models.comparison import Comparison, RequirementAnalysis, ProductAssessment
from agents.base import AgentBase, RunState

logger = logging.getLogger(__name__)


# ─── Requirement matching rules ───────────────────────────────────────────────

from agents.matching import match_requirement as _match_requirement


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
            requirement_analyses = [RequirementAnalysis(requirement=req) for req in state.requirements]
            weights = {"must": 4, "high": 3, "preferred": 2, "optional": 1}

            for product in state.candidate_products:
                specs = list(state.verified_specs.get(product.id, product.specs))
                price_data = state.prices.get(product.id, {})
                product.price_info = price_data.get("price_info", product.price_info)
                # Budget is compared against price_info, not an unrelated LLM price spec.
                specs = [s for s in specs if s.key.lower() not in ("price", "budget", "price usd")]
                if product.price_info and product.price_info.amount is not None:
                    info = product.price_info
                    specs.append(Spec(key="budget", value=f"{info.amount} {info.currency}",
                        status="insufficient" if info.is_stale else "supported",
                        evidence_ids=[info.source_id] if info.source_id else []))
                matches = []
                assessments = []

                for index, req in enumerate(state.requirements):
                    match, explanation, ev_ids = _match_requirement(req, specs)
                    matches.append(match)
                    assessments.append(ProductAssessment(
                        product_id=product.id,
                        match=match,
                        explanation=explanation,
                        evidence_ids=ev_ids,
                    ))
                    requirement_analyses[index].product_assessments.append(assessments[-1])

                requirement_matches[product.id] = matches

                # Build product score
                met = sum(1 for m in matches if m == "✓")
                total = len(state.requirements)
                product.score = f"{met} of {total} requirements met"
                must_matches = [m for r, m in zip(state.requirements, matches) if r.priority == "must"]
                product.must_have_status = "not_met" if "✕" in must_matches else "uncertain" if "?" in must_matches else "met"
                total_weight = sum(weights[r.priority] for r in state.requirements)
                product.weighted_match_score = sum(weights[r.priority] for r, m in zip(state.requirements, matches) if m == "✓") / total_weight if total_weight else 0

                # Add verified specs to product
                product.specs = specs

                # Add warranty
                warranty_data = state.warranties.get(product.id)
                if warranty_data:
                    product.warranty, product.return_policy = warranty_data

                # Add reviews
                product.review_themes = state.review_themes.get(product.id, product.review_themes)

                # Build pros/limitations from match results
                product.pros = [a.explanation for a in assessments if a.match == "✓"][:3]
                product.limitations = [a.explanation for a in assessments if a.match != "✓"][:3]

            # Step 2: Generate narrative (LLM), fallback to deterministic
            tradeoffs = await self._generate_narrative(state, requirement_matches)

            # Step 3: Build final Comparison object
            state.comparison = Comparison(
                id=state.comparison_id,
                request_id=state.request_id,
                requirements=state.requirements,
                products=state.candidate_products,
                requirement_matches=requirement_matches,
                tradeoffs=tradeoffs,
                requirement_analysis=requirement_analyses,
                notices=list(dict.fromkeys(state.notices)),
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
        # P3: derive every summary from the checked requirement matrix.
        # Free-form Gemini prose is not evidence; semantic evaluation is P5.
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
