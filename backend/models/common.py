"""
backend/models/common.py
Shared Pydantic schemas used across all agents and API routes.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel


class EvidenceStatus(str, Enum):
    """Four-level evidence quality system (see PRD §20)."""
    verified = "verified"
    supported = "supported"
    conflicting = "conflicting"
    insufficient = "insufficient"


class ApiErrorCode(str, Enum):
    """Canonical error codes returned in the API error envelope."""
    invalid_input = "INVALID_INPUT"
    not_found = "NOT_FOUND"
    schema_error = "SCHEMA_ERROR"
    rate_limited = "RATE_LIMITED"
    upstream_failure = "UPSTREAM_FAILURE"
    timeout = "TIMEOUT"
    unsupported_category = "UNSUPPORTED_CATEGORY"
    quota_exhausted = "QUOTA_EXHAUSTED"
    internal_error = "INTERNAL_ERROR"


class ApiError(BaseModel):
    """Error detail object nested inside the error envelope."""
    code: ApiErrorCode
    message: str
    retry_after: Optional[int] = None  # seconds until retry is safe


class ApiErrorResponse(BaseModel):
    """
    Standard error response shape for all API errors (PRD §18).
    Example: {"error": {"code": "RATE_LIMITED", "message": "...", "retry_after": 30}}
    """
    error: ApiError


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    mock_mode: bool = False
