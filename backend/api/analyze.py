"""
backend/api/analyze.py
POST /api/analyze-requirements
Runs the Requirement Analysis Agent (Agent 1) and returns structured requirements.

This endpoint is the entry point for the research flow. It:
1. Validates the input text.
2. Calls Agent 1 to extract requirements using Gemini.
3. Returns extracted requirements + clarifying questions.
4. Falls back to mock requirements if Gemini is unavailable.
"""

import logging
import asyncio
from fastapi import APIRouter, HTTPException, Request

from models.request import AnalyzeRequirementsRequest, AnalyzeRequirementsResponse
from models.common import ApiError, ApiErrorCode, ApiErrorResponse
from agents.requirement import RequirementAgent
from llm.gemini import get_llm_provider, GeminiProvider
from llm.base import LLMRateLimitError, LLMError

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/analyze-requirements",
    response_model=AnalyzeRequirementsResponse,
    responses={
        400: {"model": ApiErrorResponse, "description": "Invalid input"},
        422: {"model": ApiErrorResponse, "description": "Schema validation error"},
        429: {"model": ApiErrorResponse, "description": "Rate limited"},
        502: {"model": ApiErrorResponse, "description": "LLM upstream failure"},
    },
    tags=["pipeline"],
)
async def analyze_requirements(
    body: AnalyzeRequirementsRequest,
    request: Request,
) -> AnalyzeRequirementsResponse:
    """
    Extract structured, prioritized requirements from a natural-language request.

    - Separates user-stated requirements from inferred ones.
    - Returns missing_info questions for clarification.
    - Falls back to mock data if GEMINI_API_KEY is not set.
    """
    logger.info("analyze-requirements: text_len=%d ip=%s", len(body.text), request.client.host if request.client else "unknown")

    llm = get_llm_provider()
    agent = RequirementAgent(llm=llm)

    try:
        result = await agent.run(body.text)
        from data.runtime import save_request
        await asyncio.to_thread(save_request, result)
        return result
    except LLMRateLimitError as e:
        raise HTTPException(
            status_code=429,
            detail=ApiErrorResponse(
                error=ApiError(
                    code=ApiErrorCode.rate_limited,
                    message="AI analysis rate limit reached. Please try again shortly.",
                    retry_after=e.retry_after,
                )
            ).model_dump(),
        )
    except LLMError as e:
        logger.error("LLM failure in analyze-requirements: %s", e)
        if isinstance(llm, GeminiProvider):
            raise HTTPException(status_code=502, detail=ApiErrorResponse(error=ApiError(
                code=ApiErrorCode.upstream_failure,
                message=str(e),
            )).model_dump())
        # Key-free demo provider retains its explicitly labeled fallback.
        agent = RequirementAgent(llm=None)  # uses built-in fallback
        try:
            return await agent.run_mock(body.text)
        except Exception as fallback_err:
            logger.error("Mock fallback also failed: %s", fallback_err)
            raise HTTPException(
                status_code=502,
                detail=ApiErrorResponse(
                    error=ApiError(
                        code=ApiErrorCode.upstream_failure,
                        message="AI analysis is temporarily unavailable. Please try again.",
                    )
                ).model_dump(),
            )
    except Exception as e:
        logger.exception("Unexpected error in analyze-requirements")
        raise HTTPException(
            status_code=500,
            detail=ApiErrorResponse(
                error=ApiError(
                    code=ApiErrorCode.internal_error,
                    message="An unexpected error occurred.",
                )
            ).model_dump(),
        )

    finally:
        if hasattr(llm, "aclose"):
            await llm.aclose()
