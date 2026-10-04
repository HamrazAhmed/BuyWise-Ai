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

from models.comparison import Comparison, FollowUpResponse

logger = logging.getLogger(__name__)


def _requires_rerun(question: str) -> bool:
    """Heuristic: does this question ask about a changed requirement?"""
    rerun_keywords = [
        "increase", "decrease", "change", "different", "instead",
        "what if", "suppose", "higher", "lower", "more ram", "bigger",
        "smaller", "under $", "over $", "up to $",
    ]
    q_lower = question.lower()
    return any(kw in q_lower for kw in rerun_keywords)


def _extract_budget_patch(question: str, currency: str = 'USD') -> Optional[dict]:
    """Extract a budget requirement patch from a 'what if budget = X?' question."""
    pkr = bool(re.search(r'\b(pkr|rs\.?|rupees)\b', question, re.I))
    usd = bool(re.search(r'\$|\b(usd|dollars?)\b', question, re.I))
    if pkr and usd:
        return None
    explicit = 'PKR' if pkr else 'USD' if usd else None
    if currency not in ('USD', 'PKR') or (explicit and explicit != currency) or re.search(r"\b(eur|gbp|inr|yen|euros|pounds)\b", question, re.IGNORECASE):
        return None
    number = r"((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)(?![\d.,])"
    patterns = [r"(?:\$|PKR|Rs\.?)\s*"+number, number+r"\s*(?:dollars?|USD|PKR|rupees)", r"budget\s+(?:of|to|is|=)?\s*\$?\s*"+number]
    for pattern in patterns:
        match = re.search(pattern, question, re.IGNORECASE)
        if match:
            if re.match(r"\s*(?:-|–|to|or)\s*\$?\d", question[match.end():], re.I):
                return None
            amount = match.group(1).replace(",", "")
            operator = "<" if re.search(r"\b(under|below)\s*(?:\$|PKR|Rs\.?)?\s*$", question[:match.start(1)], re.I) else "<="
            return {"key": "budget", "operator": operator, "value": f"{amount} {currency}"}
    return None


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
    from agents.matching import money, canonical_key
    ceilings = [money(r.value) for r in comparison.requirements if canonical_key(r.key) == 'budget']
    currencies = {m[1] for m in ceilings if m}
    currency = next(iter(currencies)) if len(currencies) == 1 else ('USD' if not ceilings else 'unknown')
    patch = _extract_budget_patch(question, currency) if needs_rerun or re.search(r"\bbudget\b",question,re.I) else None
    needs_rerun = needs_rerun or patch is not None
    if patch:
        return FollowUpResponse(answer=f"Confirm the suggested {currency} ceiling and regenerate to recalculate matches.", requires_rerun=True, suggested_requirements_patch=[patch])
    from llm.fixture import extract_requirements
    extracted = extract_requirements("laptop " + question)["requirements"]
    extracted = [r for r in extracted if canonical_key(r['key']) != 'budget']
    if needs_rerun and extracted:
        return FollowUpResponse(answer="Confirm these requirement changes and regenerate.", requires_rerun=True, suggested_requirements_patch=extracted)
    return _deterministic_follow_up(comparison, question, needs_rerun, [])


def _deterministic_follow_up(
    comparison: Comparison,
    question: str,
    requires_rerun: bool,
    patch: list[dict],
) -> FollowUpResponse:
    """Fallback answer when LLM is unavailable."""
    from agents.matching import canonical_key
    from agents.evidence import verify_spec, snapshot_chunks, resolve, has_value
    from rag.sanitize import is_injection_attempt
    question_lower=question.lower()
    if re.search(r"\b(football|cricket|weather|president|politics|recipe)\b", question_lower):
        return FollowUpResponse(answer="The answer is unknown: this question is outside the checked shopping comparison.")
    keys=[key for key in ("ram", "storage", "weight", "upgradeability", "virtualization", "battery", "cpu", "gpu", "display") if key in question_lower]
    if "linux" in question_lower: keys.append("linux")
    if "memory" in question_lower: keys.append("ram")
    if "upgrade" in question_lower: keys.append("upgradeability")
    if "ssd" in question_lower: keys.append("storage")
    lines=[]; identifiers=[]
    for product in comparison.products:
        records=[e for e in product.evidence if e.product_id==product.id and not is_injection_attempt(e.snippet)]
        chunks=snapshot_chunks(product)
        for key in dict.fromkeys(keys):
            spec=next((s for s in product.specs if canonical_key(s.key)==key),None)
            checked=verify_spec(spec,chunks) if spec else None
            if checked and checked.status != "insufficient":
                details=checked.value
                if checked.status == "conflicting":
                    details=" / ".join(c.value for c in checked.conflicting_values)
                lines.append(f"{product.name}: {key} {details} ({checked.status})")
                identifiers.extend(checked.evidence_ids)
            else:
                lines.append(f"{product.name}: {key} unknown")
        if re.search(r"\b(prices?|costs?|budgets?)\b", question_lower):
            price=product.price_info
            chunk=resolve(chunks, price.source_id) if price else None
            if price and price.amount is not None and chunk and has_value(chunk, 'budget', f'{price.amount} {price.currency}'):
                from datetime import datetime, timezone, timedelta
                try:
                    age=datetime.now(timezone.utc)-datetime.fromisoformat(chunk.fetched_at.replace('Z','+00:00'))
                    stale=age>timedelta(hours=24) or age<timedelta(0)
                except (ValueError, TypeError):
                    stale=True
                lines.append(f"{product.name}: recorded price {price.amount} {price.currency}, observed {chunk.fetched_at or 'unknown date'}; {'stale/unknown age, current budget fit uncertain' if stale else 'within 24 hours; confirm current listing'}")
                identifiers.append(chunk.id)
            else:
                lines.append(f"{product.name}: price unknown")
        if re.search(r"\b(warranty|warranties|returns?|policy|policies)\b", question_lower):
            warranty=product.warranty; returns=product.return_policy
            chunk=resolve(chunks,warranty.source_id) if warranty else None
            if warranty and warranty.duration_months is not None and chunk and has_value(chunk,'warranty_months',warranty.duration_months):
                lines.append(f"{product.name}: warranty {warranty.duration_months} months; confirm regional coverage and conditions")
                identifiers.append(chunk.id)
            else:
                lines.append(f"{product.name}: warranty duration unknown")
            chunk=resolve(chunks,returns.source_id) if returns else None
            if returns and returns.window_days is not None and chunk and has_value(chunk,'return_window_days',returns.window_days):
                lines.append(f"{product.name}: return window {returns.window_days} days; seller-dependent, verify conditions")
                identifiers.append(chunk.id)
            else:
                lines.append(f"{product.name}: return window unknown")
            if returns and chunk and has_value(chunk, 'return_conditions', returns.conditions):
                lines.append(f"{product.name}: recorded seller conditions: {returns.conditions}")
                identifiers.append(chunk.id)
        if re.search(r"\b(reviews?|opinions?)\b", question_lower):
            opinions=[]
            for review in product.review_themes:
                chunk=resolve(chunks,review.source_id)
                summary=review.summary.removeprefix('Opinion: ')
                if chunk and chunk.kind=='reviews' and has_value(chunk,'opinion '+review.theme,summary):
                    opinions.append('Opinion: '+summary)
                    identifiers.append(chunk.id)
            lines.append(product.name+': '+('; '.join(opinions) if opinions else 'review opinion data unknown'))
        if re.search(r"\b(best|recommend)\b|requirement.*match|match.*requirement", question_lower):
            lines.append(f"{product.name}: {product.score}; must-have status {product.must_have_status}" if records else f"{product.name}: requirement fit unknown; no checked sources in this snapshot")
            identifiers.extend(e for s in product.specs for e in s.evidence_ids if any(r.id==e for r in records))
    if not lines:
        answer="The answer is unknown from the checked comparison data. Supported questions concern stored specifications, requirement matches and requirement changes."
    else:
        answer="; ".join(lines)+"."
    if comparison.data_mode != "live": answer="Synthetic demo/fixture data. "+answer
    if requires_rerun: answer+=" Confirm any changed criteria and regenerate to recalculate the comparison."
    return FollowUpResponse(answer=answer,evidence_ids=list(dict.fromkeys(identifiers)),requires_rerun=requires_rerun,suggested_requirements_patch=patch)
