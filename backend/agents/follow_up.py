"""
backend/agents/follow_up.py
Follow-up Q&A — grounded in stored comparison, not LLM free-generation.

Responsibilities:
- Answer questions based ONLY on the stored comparison and its evidence.
- Cite evidence IDs in the response.
- Set requires_rerun=True if the question involves changed requirements.
- Return suggested_requirements_patch for budget/requirements changes.

PRD §8 (F11), §18 (POST /api/follow-up)
"""

import logging
import re
from typing import Optional
from pydantic import BaseModel, Field

from models.comparison import Comparison, FollowUpResponse
from models.request import Requirement
from llm.gemini import wrap_context, get_llm_provider
from llm.base import LLMError

logger = logging.getLogger(__name__)


FOLLOW_UP_SYSTEM_PROMPT = """
You are a shopping research assistant for BuyWise AI.
You answer follow-up questions based ONLY on the comparison data provided.

RULES:
1. Only use information from the comparison data below.
2. Do NOT invent specs, prices, or opinions.
3. If the answer requires a new research run (e.g. budget change), say so.
4. Always cite evidence by referencing product names and spec keys.
5. Be concise and factual. Frame around the user's requirements.
"""


class FollowUpLLMOutput(BaseModel):
    answer: str
    evidence_ids: list[str] = Field(default_factory=list)
    requires_rerun: bool = False
    suggested_requirements_patch: list[dict] = Field(default_factory=list)


def _requires_rerun(question: str) -> bool:
    """Heuristic: does this question ask about a changed requirement?"""
    rerun_keywords = [
        "budget", "increase", "decrease", "change", "different", "instead",
        "what if", "suppose", "higher", "lower", "more ram", "bigger",
        "smaller", "under $", "over $", "up to $",
    ]
    q_lower = question.lower()
    return any(kw in q_lower for kw in rerun_keywords)


def _extract_budget_patch(question: str) -> Optional[dict]:
    """Extract a budget requirement patch from a 'what if budget = X?' question."""
    patterns = [
        r"\$\s*(\d[\d,]*)",
        r"(\d[\d,]+)\s*dollars?",
        r"budget\s+(?:of|to|is|=)?\s*\$?\s*(\d[\d,]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, question, re.IGNORECASE)
        if match:
            amount = match.group(1).replace(",", "")
            return {"key": "budget", "operator": "<=", "value": f"{amount} USD"}
    return None


def _comparison_to_context(comparison: Comparison) -> str:
    """Convert comparison data to a structured context string for the LLM."""
    lines = ["=== COMPARISON DATA ==="]
    for product in comparison.products:
        lines.append(f"\nPRODUCT: {product.name}")
        lines.append(f"  Score: {product.score}")
        if product.price_info:
            price = product.price_info.amount
            lines.append(f"  Price: ${price:,.0f}" if price else "  Price: Not available")
        for spec in product.specs[:10]:
            lines.append(f"  {spec.key}: {spec.value} [{spec.status}]")

    lines.append("\n=== REQUIREMENT MATCHES ===")
    for pid, matches in comparison.requirement_matches.items():
        prod = next((p for p in comparison.products if p.id == pid), None)
        if prod:
            lines.append(f"{prod.name}: {', '.join(str(m) for m in matches)}")

    lines.append("\n=== TRADE-OFFS ===")
    for tradeoff in comparison.tradeoffs:
        lines.append(f"- {tradeoff}")

    return "\n".join(lines)


async def answer_follow_up(
    comparison: Comparison,
    question: str,
) -> FollowUpResponse:
    """
    Answer a follow-up question grounded in the stored comparison.

    :param comparison: The stored Comparison from the pipeline.
    :param question: User's follow-up question (≤500 chars, already validated).
    :returns: FollowUpResponse with answer, citations, rerun flag.
    """
    needs_rerun = _requires_rerun(question)
    requirements_patch = []

    if needs_rerun:
        budget_patch = _extract_budget_patch(question)
        if budget_patch:
            requirements_patch = [budget_patch]

    # Try LLM
    llm = get_llm_provider()
    context_str = _comparison_to_context(comparison)
    prompt = f"""
User question: {question}

{context_str}

Answer the question based ONLY on the comparison data above.
If the question asks about a changed budget or requirements that would require a new research run,
set requires_rerun=true and explain what would need to change.
"""

    try:
        output = await llm.generate_json(
            prompt=prompt,
            schema=FollowUpLLMOutput,
            system_prompt=FOLLOW_UP_SYSTEM_PROMPT,
            temperature=0.1,
        )
        return FollowUpResponse(
            answer=output.answer,
            evidence_ids=output.evidence_ids,
            requires_rerun=output.requires_rerun or needs_rerun,
            suggested_requirements_patch=requirements_patch or output.suggested_requirements_patch,
        )
    except LLMError as e:
        logger.error("Follow-up LLM failed: %s — using deterministic fallback", e)
        return _deterministic_follow_up(comparison, question, needs_rerun, requirements_patch)


def _deterministic_follow_up(
    comparison: Comparison,
    question: str,
    requires_rerun: bool,
    patch: list[dict],
) -> FollowUpResponse:
    """Fallback answer when LLM is unavailable."""
    product_names = [p.name for p in comparison.products]
    top = product_names[0] if product_names else "the top product"

    answer = (
        f"Based on the comparison data, {top} best matches your stated requirements "
        f"among the products analyzed. The key trade-offs are: {'; '.join(comparison.tradeoffs[:2])}. "
        f"AI-generated analysis is currently unavailable — please review the evidence table directly."
    )
    if requires_rerun:
        answer += " This question involves changed requirements; regenerate the comparison to see updated results."

    return FollowUpResponse(
        answer=answer,
        evidence_ids=[],
        requires_rerun=requires_rerun,
        suggested_requirements_patch=patch,
    )
