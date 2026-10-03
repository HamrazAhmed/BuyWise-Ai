"""
backend/api/follow_up.py
POST /api/follow-up — grounded Q&A on a stored comparison.
POST /api/compare-products — generate comparison for specific product IDs.
"""

import logging
from fastapi import APIRouter, HTTPException

from models.comparison import FollowUpRequest, FollowUpResponse
from models.common import ApiError, ApiErrorCode, ApiErrorResponse
from agents.orchestrator import get_comparison
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


@router.post("/compare-products", tags=["pipeline"])
async def compare_products(body: dict):
    """
    Trigger a comparison for specific product IDs within an existing request.
    Simplified: for MVP, use /research-products which handles the full pipeline.
    """
    # For MVP: re-use existing comparison if available
    request_id = body.get("request_id")
    product_ids = body.get("product_ids", [])

    if not product_ids or len(product_ids) < 2:
        raise HTTPException(
            status_code=400,
            detail=ApiErrorResponse(
                error=ApiError(
                    code=ApiErrorCode.invalid_input,
                    message="At least 2 product_ids are required.",
                )
            ).model_dump(),
        )

    # For MVP: just return a pointer to research-products
    return {
        "message": "Use /api/research-products with your requirements to trigger the full pipeline.",
        "hint": "The pipeline automatically selects and compares 3-5 products based on your requirements.",
    }
