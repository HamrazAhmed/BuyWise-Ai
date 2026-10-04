"""
backend/api/follow_up.py
POST /api/follow-up — grounded Q&A on a stored comparison.
POST /api/compare-products — generate comparison for specific product IDs.
"""

import logging
from fastapi import APIRouter, HTTPException

from models.comparison import FollowUpRequest, FollowUpResponse, Comparison
from models.product import CompareProductsRequest
from agents.base import RunState
from agents.comparison import ComparisonAgent
from models.common import ApiError, ApiErrorCode, ApiErrorResponse
from agents.orchestrator import get_comparison, get_request_comparison, store_comparison
from agents.follow_up import answer_follow_up
from llm.base import LLMRateLimitError, LLMError

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/follow-up", response_model=FollowUpResponse, tags=["pipeline"])
async def follow_up(body: FollowUpRequest):
    """
    Answer a follow-up question grounded in a stored comparison.
    - Answers cite evidence from the comparison.
    - Sets requires_rerun=True for questions about changed requirements.
    - Returns suggested_requirements_patch for budget changes.
    """
    comparison = get_comparison(body.comparison_id)
    if not comparison:
        raise HTTPException(
            status_code=404,
            detail=ApiErrorResponse(
                error=ApiError(
                    code=ApiErrorCode.not_found,
                    message=f"Comparison '{body.comparison_id}' not found. Run a new research session first.",
                )
            ).model_dump(),
        )

    try:
        return await answer_follow_up(comparison=comparison, question=body.question)
    except LLMRateLimitError as e:
        raise HTTPException(
            status_code=429,
            detail=ApiErrorResponse(
                error=ApiError(
                    code=ApiErrorCode.rate_limited,
                    message="Rate limit reached. Please wait before asking another question.",
                    retry_after=e.retry_after,
                )
            ).model_dump(),
        )
    except Exception as e:
        logger.exception("Follow-up failed")
        raise HTTPException(
            status_code=502,
            detail=ApiErrorResponse(
                error=ApiError(
                    code=ApiErrorCode.upstream_failure,
                    message="Follow-up answer unavailable. Please try again.",
                )
            ).model_dump(),
        )


@router.post("/compare-products", response_model=Comparison, tags=["pipeline"])
async def compare_products(body: CompareProductsRequest):
    source = get_comparison(body.comparison_id) if body.comparison_id else get_request_comparison(body.request_id)
    if not source or source.request_id != body.request_id:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Research comparison for this request was not found."}})
    products = {p.id: p for p in source.products}
    if any(pid not in products for pid in body.product_ids):
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Selected product is not in this comparison."}})
    if not source.requirements:
        raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_INPUT", "message": "Comparison has no stored requirements; run research again."}})
    selected = [products[pid] for pid in body.product_ids]
    state = RunState(request_id=body.request_id, requirements=source.requirements, candidate_products=selected)
    state.verified_specs = {p.id: p.specs for p in selected}
    state.prices = {p.id: {"price_info": p.price_info} for p in selected}
    state.review_themes = {p.id: p.review_themes for p in selected}
    state.warranties = {p.id: (p.warranty, p.return_policy) for p in selected}
    if source.data_mode != "demo":
        from agents.evidence import EvidenceVerificationAgent
        await EvidenceVerificationAgent().run(state, snapshot=True)
    await ComparisonAgent().run(state)
    result = state.comparison
    result.data_mode = source.data_mode
    result.notices = list(dict.fromkeys(source.notices + state.notices))
    store_comparison(result)
    return result
