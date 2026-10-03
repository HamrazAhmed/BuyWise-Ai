"""
backend/api/health.py
GET /api/health — liveness probe.
"""

import os
from fastapi import APIRouter
from models.common import HealthResponse

router = APIRouter()

VERSION = "0.1.0"


@router.get("/health", response_model=HealthResponse, tags=["infra"])
async def health() -> HealthResponse:
    """
    Simple health check used by Vercel and monitoring tools.
    Returns 200 when the service is up.
    """
    return HealthResponse(
        status="ok",
        version=VERSION,
        mock_mode=not bool(os.getenv("GEMINI_API_KEY")),
    )
