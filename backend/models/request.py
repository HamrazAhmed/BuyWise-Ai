"""
backend/models/request.py
Pydantic schemas for ShoppingRequest and Requirement entities.
"""

from enum import Enum
from typing import Optional, Literal
from uuid import UUID, uuid4
from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator


class Priority(str, Enum):
    """Importance levels for requirements."""
    must = "must"
    high = "high"
    preferred = "preferred"
    optional = "optional"


class RequirementSource(str, Enum):
    """Whether a requirement was stated by the user or inferred."""
    user = "user"
    inferred = "inferred"


class Requirement(BaseModel):
    """
    A structured requirement extracted from the user's request.
    Agents 1 and beyond share this schema.
    """
    id: Optional[str] = Field(default_factory=lambda: str(uuid4()))
    # Canonical key (e.g. 'budget', 'ram', 'os_compatibility')
    key: str = Field(..., min_length=1, max_length=100)
    # Comparison operator (e.g. '<=', '>=', '=', 'supports')
    operator: Literal["<=", "<", ">=", ">", "=", "==", "supports", "contains"]
    # Value string (e.g. '1000 USD', '32 GB', 'Linux')
    value: str = Field(..., min_length=1, max_length=200)
    priority: Priority
    source: RequirementSource = RequirementSource.user
    confirmed: bool = False

    @field_validator("key", "value", mode="before")
    @classmethod
    def strip_fields(cls, value):
        return value.strip() if isinstance(value, str) else value


class AnalyzeRequirementsRequest(BaseModel):
    """POST /api/analyze-requirements — request body."""
    text: str = Field(..., min_length=10, max_length=1000,
                      description="Natural-language shopping request (10–1000 chars).")

    @field_validator("text", mode="before")
    @classmethod
    def strip_text(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class AnalyzeRequirementsResponse(BaseModel):
    """POST /api/analyze-requirements — success response."""
    request_id: str
    category: str
    requirements: list[Requirement]
    # Clarifying questions to present to the user (0–3)
    missing_info: list[str] = Field(default_factory=list)
    data_mode: Literal["live", "demo", "fixture"] = "live"
    notices: list[str] = Field(default_factory=list)


class ShoppingRequestStatus(str, Enum):
    pending = "pending"
    analyzing = "analyzing"
    researching = "researching"
    comparing = "comparing"
    done = "done"
    error = "error"


class ShoppingRequest(BaseModel):
    """Stored record of a research session."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    raw_text: str
    status: ShoppingRequestStatus = ShoppingRequestStatus.pending
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    requirements: list[Requirement] = Field(default_factory=list)
