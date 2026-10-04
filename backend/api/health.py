"""
backend/api/health.py
GET /api/health — liveness probe.
"""

import os
import asyncio
from fastapi import HTTPException
from fastapi import APIRouter
from models.common import HealthResponse

router = APIRouter()

VERSION = "0.1.0"


@router.get('/ready', tags=['infra'])
async def ready():
    def probe():
        from data import runtime
        runtime.ensure()
        with runtime.connect() as db: db.execute('SELECT version FROM bw_migrations WHERE version=1').fetchone()
        return 'postgresql' if runtime.postgres() else 'local-sqlite'
    try:
        storage = await asyncio.to_thread(probe)
    except Exception:
        raise HTTPException(503, detail={'error': {'code': 'STORAGE_UNAVAILABLE', 'message': 'Research storage is unavailable.'}})
    return {'status': 'ok', 'storage': storage, 'market': os.getenv('BUYWISE_MARKET', 'PK'), 'worker_mode': 'inline' if os.getenv('BUYWISE_INLINE_WORKER', 'true').lower() == 'true' else 'external-required'}


@router.get("/health", response_model=HealthResponse, tags=["infra"])
async def health() -> HealthResponse:
    """
    Simple health check used by Vercel and monitoring tools.
    Returns 200 when the service is up.
    """
    return HealthResponse(
        status="ok",
        version=VERSION,
        mock_mode=os.getenv("BUYWISE_MODE", "auto").strip().lower() in ("fixture", "demo") or not bool(os.getenv("GEMINI_API_KEY")),
    )
