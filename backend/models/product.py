"""
backend/models/product.py
Pydantic schemas for Product, Spec, Evidence, and related entities.
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator
from .request import Requirement
from .common import EvidenceStatus


class ConflictingValue(BaseModel):
    """Used when a spec has two sources reporting different values."""
    value: str
    source_url: str
    source_type: str  # 'primary' | 'secondary'


class Spec(BaseModel):
    """
    A product specification claim with evidence backing.
    Maps to ProductSpecification in the data model.
    """
    key: str  # e.g. 'CPU', 'RAM', 'Battery'
    value: str  # e.g. 'Ryzen 7 7840U', '32GB DDR5'
    # When conflicting, value contains the primary-source value (or first found).
    status: EvidenceStatus
    evidence_ids: list[str] = Field(default_factory=list)
    # Populated only when status == 'conflicting'
    conflicting_values: list[ConflictingValue] = Field(default_factory=list)


class SourceClaim(BaseModel):
    key: str
    value: str


class Evidence(BaseModel):
    """
    A piece of evidence backing a specific claim.
    Maps to the Evidence entity in the data model.
    """
    id: str
    product_id: Optional[str] = None
    chunk_id: Optional[str] = None
    origin: Literal["web", "curated", "fixture"] = "web"
    kind: str = "specs"
    source_id: Optional[str] = None
    title: str
    source_url: str
    source_type: str  # 'primary' | 'secondary'
    claims: list[SourceClaim] = Field(default_factory=list)
    snippet: str       # Sanitized source excerpt; stored for citation display
    fetched_at: str    # ISO date string


class ReviewTheme(BaseModel):
    """
    A review theme extracted by Agent 4.
    Labeled as opinion — never presented as verified fact.
    """
    theme: str  # e.g. 'Performance', 'Battery life'
    sentiment: str  # 'positive' | 'negative' | 'mixed' | 'neutral'
    summary: str    # Short opinion summary; no fabricated quotes
    source_id: Optional[str] = None


class Warranty(BaseModel):
    """Warranty information extracted by Agent 5."""
    duration_months: Optional[int] = None
    coverage: Optional[str] = None
    conditions: Optional[str] = None
    source_id: Optional[str] = None
    # 'complete' | 'partial' | 'unknown'
    completeness: str = "unknown"


class ReturnPolicy(BaseModel):
    """Return policy information extracted by Agent 5."""
    window_days: Optional[int] = None
    conditions: Optional[str] = None
    seller_dependent: bool = True
    source_id: Optional[str] = None


class PriceInfo(BaseModel):
    """Price data with timestamp, extracted by Agent 6."""
    amount: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)  # null if unknown
    currency: str = "USD"
    seller: Optional[str] = None
    fetched_at: Optional[str] = None  # ISO datetime string
    is_stale: bool = False  # True if >24h old
    source_id: Optional[str] = None


class Product(BaseModel):
    """
    A product candidate with all verified data.
    Populated progressively as agents 3-6 complete.
    """
    id: str
    name: str
    brand: Optional[str] = None
    category: Optional[str] = None
    model_number: Optional[str] = None
    canonical_url: Optional[str] = None

    # Human-readable requirement satisfaction summary
    score: str = ""
    # Display initials/emoji for UI cards
    image: str = ""

    # Agents 3–6 output
    specs: list[Spec] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    review_themes: list[ReviewTheme] = Field(default_factory=list)
    warranty: Optional[Warranty] = None
    return_policy: Optional[ReturnPolicy] = None
    price_info: Optional[PriceInfo] = None

    # Shorthand pros/limitations for the card view
    pros: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    must_have_status: Literal["met", "not_met", "uncertain"] = "uncertain"
    weighted_match_score: float = 0.0


class ResearchProductsRequest(BaseModel):
    """POST /api/research-products — request body."""
    request_id: str = Field(min_length=1, max_length=100)
    requirements: list[Requirement] = Field(min_length=1, max_length=20)
    raw_text: str = Field(default="", max_length=1000)

    @field_validator("request_id", "raw_text", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class ResearchProductsResponse(BaseModel):
    """POST /api/research-products — initial response (SSE stream follows)."""
    comparison_id: str
    status: str = "processing"
    stream_url: str


class CompareProductsRequest(BaseModel):
    """POST /api/compare-products — request body."""
    request_id: str = Field(min_length=1, max_length=100)
    product_ids: list[str] = Field(min_length=2, max_length=5)
    comparison_id: Optional[str] = None

    @field_validator("request_id", "comparison_id", mode="before")
    @classmethod
    def strip_id(cls, value):
        if value is None:
            return None
        if isinstance(value, str) and value.strip():
            return value.strip()
        raise ValueError("Identifier cannot be empty")

    @field_validator("product_ids")
    @classmethod
    def validate_ids(cls, values):
        values = [value.strip() for value in values]
        if any(not value or len(value) > 100 for value in values) or len(set(values)) != len(values):
            raise ValueError("Product identifiers must be nonempty and unique")
        return values
