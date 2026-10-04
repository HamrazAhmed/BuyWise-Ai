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

from models.product import ResearchProductsRequest, ResearchProductsResponse
from models.common import ApiError, ApiErrorCode, ApiErrorResponse
from agents.orchestrator import run_pipeline, get_comparison
from llm.base import LLMRateLimitError, LLMError

logger = logging.getLogger(__name__)
router = APIRouter()

# Jobs/events are durable; each subscriber has its own replay cursor.
from data import jobs
import os
import time
import weakref

_workers = weakref.WeakKeyDictionary()


def ensure_local_worker():
    if os.getenv('BUYWISE_INLINE_WORKER', 'true').lower() != 'true':
        return
    if os.getenv('VERCEL'):
        raise RuntimeError('Vercel API requires BUYWISE_INLINE_WORKER=false and a separate worker')
    loop = asyncio.get_running_loop()
    task = _workers.get(loop)
    if task is None or task.done():
        from worker import serve
        _workers[loop] = asyncio.create_task(serve())


@router.post('/research-products', response_model=ResearchProductsResponse, tags=['pipeline'])
async def research_products(body: ResearchProductsRequest):
    identifier = str(uuid.uuid4())
    try:
        await asyncio.to_thread(jobs.submit, identifier, body.model_dump(mode='json'))
    except ValueError:
        raise HTTPException(429, detail={'error': {'code': 'RATE_LIMITED', 'message': 'Research queue is full; retry later.', 'retry_after': 60}})
    ensure_local_worker()
    return {'comparison_id': identifier, 'status': 'processing', 'stream_url': f'/api/stream/{identifier}'}


@router.get('/research-status/{comparison_id}', tags=['pipeline'])
async def research_status(comparison_id: str):
    record = await asyncio.to_thread(jobs.status, comparison_id)
    if not record:
        raise HTTPException(404, detail={'error': {'code': 'NOT_FOUND', 'message': 'Research job not found.'}})
    if record['status'] == 'error':
        events = await asyncio.to_thread(jobs.events, comparison_id)
        record['error'] = next((event for _, event in reversed(events) if event.get('type') == 'error'), None)
    return record


@router.get('/stream/{comparison_id}', tags=['pipeline'])
async def stream_progress(comparison_id: str, request: Request):
    if not await asyncio.to_thread(jobs.status, comparison_id):
        raise HTTPException(404, detail={'error': {'code': 'NOT_FOUND', 'message': 'Stream not found.'}})
    try:
        after = int(request.headers.get('last-event-id', '0'))
        if after < 0 or after > 100: raise ValueError()
    except ValueError:
        raise HTTPException(400, detail={'error': {'code': 'INVALID_INPUT', 'message': 'Invalid stream cursor.'}})
    async def event_generator():
        cursor, started, last_keepalive = after, time.monotonic(), time.monotonic()
        while time.monotonic() - started < 210:
            if await request.is_disconnected():
                return
            events = await asyncio.to_thread(jobs.events, comparison_id, cursor)
            for seq, event in events:
                cursor = seq
                yield f"id: {seq}\nevent: {event.get('type', 'message')}\ndata: {json.dumps(event)}\n\n"
            record = await asyncio.to_thread(jobs.status, comparison_id)
            if not record or record['status'] in ('done', 'error'):
                # Re-read after terminal state; completion/events commit together.
                for seq, event in await asyncio.to_thread(jobs.events, comparison_id, cursor):
                    yield f"id: {seq}\nevent: {event.get('type', 'message')}\ndata: {json.dumps(event)}\n\n"
                yield 'event: end\ndata: {}\n\n'
                return
            if time.monotonic() - last_keepalive >= 10:
                yield ': keepalive\n\n'
                last_keepalive = time.monotonic()
            await asyncio.sleep(.25)
        yield 'event: end\ndata: {}\n\n'
    return StreamingResponse(event_generator(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


# ─── GET /api/product/{id} ────────────────────────────────────────────────────

@router.get("/product/{product_id}", tags=["data"])
async def get_product(product_id: str, comparison_id: str):
    """Require comparison scope so repeated SKUs cannot leak another snapshot."""
    comparison = await asyncio.to_thread(get_comparison, comparison_id)
    if comparison:
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
    comparison = await asyncio.to_thread(get_comparison, comparison_id)
    if not comparison:
        raise HTTPException(
            status_code=404,
            detail=ApiErrorResponse(
                error=ApiError(code=ApiErrorCode.not_found, message=f"Comparison '{comparison_id}' not found.")
            ).model_dump(),
        )
    return comparison.model_dump()


@router.get("/comparison/{comparison_id}/evidence/{evidence_id}", tags=["data"])
async def get_evidence(comparison_id: str, evidence_id: str):
    comparison = await asyncio.to_thread(get_comparison, comparison_id)
    if comparison:
        for product in comparison.products:
            for record in product.evidence:
                if record.id == evidence_id and record.product_id == product.id:
                    return record.model_dump()
    raise HTTPException(status_code=404, detail={"error":{"code":"NOT_FOUND","message":"Evidence not found in this comparison."}})
