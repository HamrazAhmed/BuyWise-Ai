"""
backend/models/comparison.py
Pydantic schemas for Comparison and AgentRun entities.
"""

from typing import Any, Optional
from datetime import datetime, timezone
from uuid import uuid4
from pydantic import BaseModel, Field
from .request import Requirement


class RequirementMatch(str):
    """How a product meets a single requirement: met / not met / uncertain."""
    # Values: '✓' | '✕' | '?'


class ProductAssessment(BaseModel):
    """How a single product performs on a single requirement."""
    product_id: str
    match: str  # '✓' | '✕' | '?'
    explanation: str
    evidence_ids: list[str] = Field(default_factory=list)


class RequirementAnalysis(BaseModel):
    """Cross-product analysis for a single requirement."""
    requirement: Requirement
    product_assessments: list[ProductAssessment] = Field(default_factory=list)


class Comparison(BaseModel):
    """
    Full comparison result produced by Agent 8.
    Stored as JSONB in the comparison table and served via GET /api/comparison/{id}.
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    request_id: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # Snapshot of all products compared
    products: list[Any] = Field(default_factory=list)  # list[Product]
    # {product_id: ['✓', '✓', '✕', '?', ...]} — one entry per requirement
    requirement_matches: dict[str, list[str]] = Field(default_factory=dict)
    # Key trade-off sentences for the "Key differences" card
    tradeoffs: list[str] = Field(default_factory=list)
    # Per-requirement cross-product analysis
    requirement_analysis: list[RequirementAnalysis] = Field(default_factory=list)
    # Full result JSON blob (passed through to the frontend as-is)
    result_json: Optional[dict] = None


class FollowUpRequest(BaseModel):
    """POST /api/follow-up — request body."""
    comparison_id: str
    question: str = Field(..., min_length=1, max_length=500)


class FollowUpResponse(BaseModel):
    """POST /api/follow-up — success response."""
    answer: str
    evidence_ids: list[str] = Field(default_factory=list)
    # True if the answer requires a new research run (e.g. budget change)
    requires_rerun: bool = False
    # Suggested requirement patches so the user can regenerate
    suggested_requirements_patch: list[dict] = Field(default_factory=list)


class AgentRunStatus(str):
    pending = "pending"
    running = "running"
    done = "done"
    error = "error"
    skipped = "skipped"


class AgentRun(BaseModel):
    """Telemetry record for a single agent execution."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    request_id: str
    agent: str          # Agent name (e.g. 'requirement', 'spec_verification')
    status: str = "pending"
    duration_ms: Optional[int] = None
    tokens: Optional[int] = None
    error: Optional[str] = None
