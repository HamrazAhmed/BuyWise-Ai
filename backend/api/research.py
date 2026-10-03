"""
backend/api/research.py
POST /api/research-products — kick off the research pipeline with SSE progress.
GET  /api/product/{id}     — fetch product detail.
GET  /api/comparison/{id}  — fetch stored comparison.

SSE streaming: returns {comparison_id, status, stream_url} immediately,
then the client connects to /api/stream/{id} for progress events.
"""

import asyncio
import json
import logging
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from models.request import Requirement
from models.common import ApiError, ApiErrorCode, ApiErrorResponse
from agents.orchestrator import run_pipeline, get_comparison
from llm.base import LLMRateLimitError, LLMError

logger = logging.getLogger(__name__)
router = APIRouter()

# ─── In-memory SSE event queues (per comparison_id) ───────────────────────────
_sse_queues: dict[str, asyncio.Queue] = {}


async def _sse_callback(comparison_id: str, event: dict) -> None:
    """Push an SSE event into the queue for the given comparison."""
    queue = _sse_queues.get(comparison_id)
    if queue:
        await queue.put(event)


# ─── POST /api/research-products ──────────────────────────────────────────────

@router.post("/research-products", tags=["pipeline"])
async def research_products(body: dict, request: Request):
    """
    Kick off the multi-agent research pipeline.
    Returns immediately with comparison_id + stream_url.
    The pipeline runs in the background and pushes SSE events.
    """
    request_id = body.get("request_id") or str(uuid.uuid4())
    raw_requirements = body.get("requirements", [])

    if not raw_requirements:
        raise HTTPException(
            status_code=400,
            detail=ApiErrorResponse(
                error=ApiError(code=ApiErrorCode.invalid_input, message="requirements is required and cannot be empty.")
            ).model_dump(),
        )
    if len(raw_requirements) > 20:
        raise HTTPException(
            status_code=400,
            detail=ApiErrorResponse(
                error=ApiError(code=ApiErrorCode.invalid_input, message="Too many requirements (max 20).")
            ).model_dump(),
        )

    # Parse requirements
    try:
        requirements = [Requirement(**r) if isinstance(r, dict) else r for r in raw_requirements]
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=ApiErrorResponse(
                error=ApiError(code=ApiErrorCode.schema_error, message=f"Invalid requirement format: {e}")
            ).model_dump(),
        )

    comparison_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _sse_queues[comparison_id] = queue

    async def progress_callback(event: dict):
        await _sse_callback(comparison_id, event)

    # Run pipeline in background task
    async def run_and_notify():
        try:
            comparison = await run_pipeline(
                request_id=request_id,
                requirements=requirements,
                progress_callback=progress_callback,
            )
            # Override comparison ID to match what we told the client
            comparison.id = comparison_id
            await queue.put({"type": "done", "comparison_id": comparison_id})
        except LLMRateLimitError as e:
            await queue.put({"type": "error", "code": "RATE_LIMITED", "message": str(e), "retry_after": e.retry_after})
        except Exception as e:
            logger.exception("Pipeline failed for comparison %s", comparison_id)
            await queue.put({"type": "error", "code": "PIPELINE_ERROR", "message": str(e)})
        finally:
            # Signal end of stream
            await queue.put(None)

    asyncio.create_task(run_and_notify())

    return {
        "comparison_id": comparison_id,
        "status": "processing",
        "stream_url": f"/api/stream/{comparison_id}",
    }


# ─── GET /api/stream/{comparison_id} ──────────────────────────────────────────

@router.get("/stream/{comparison_id}", tags=["pipeline"])
async def stream_progress(comparison_id: str):
    """
    Server-Sent Events stream for pipeline progress.
    Events: status, partial_result, done, error.
    """
    queue = _sse_queues.get(comparison_id)
    if not queue:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Stream not found."}})

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=90.0)
                if event is None:
                    yield "event: end\ndata: {}\n\n"
                    break
                yield f"event: {event.get('type', 'message')}\ndata: {json.dumps(event)}\n\n"
        except asyncio.TimeoutError:
            yield 'event: error\ndata: {"code":"TIMEOUT","message":"Pipeline timed out."}\n\n'
        finally:
            _sse_queues.pop(comparison_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ─── GET /api/product/{id} ────────────────────────────────────────────────────

@router.get("/product/{product_id}", tags=["data"])
async def get_product(product_id: str):
    """Fetch a product from the most recently completed comparison."""
    # Search all stored comparisons for this product
    from agents.orchestrator import _comparison_store
    for comparison in _comparison_store.values():
        for product in comparison.products:
            if product.id == product_id:
                return product.model_dump()

    raise HTTPException(
        status_code=404,
        detail=ApiErrorResponse(
            error=ApiError(code=ApiErrorCode.not_found, message=f"Product '{product_id}' not found.")
        ).model_dump(),
    )


# ─── GET /api/comparison/{id} ──────────────────────────────────────────────────

@router.get("/comparison/{comparison_id}", tags=["data"])
async def get_comparison_endpoint(comparison_id: str):
    """Fetch a stored comparison by ID."""
    comparison = get_comparison(comparison_id)
    if not comparison:
        raise HTTPException(
            status_code=404,
            detail=ApiErrorResponse(
                error=ApiError(code=ApiErrorCode.not_found, message=f"Comparison '{comparison_id}' not found.")
            ).model_dump(),
        )
    return comparison.model_dump()
