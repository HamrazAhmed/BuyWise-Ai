"""
backend/models/product.py
Pydantic schemas for Product, Spec, Evidence, and related entities.
"""

from typing import Optional
from pydantic import BaseModel, Field
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


class Evidence(BaseModel):
    """
    A piece of evidence backing a specific claim.
    Maps to the Evidence entity in the data model.
    """
    id: str
    source_id: Optional[str] = None
    title: str
    source_url: str
    source_type: str  # 'primary' | 'secondary'
    snippet: str       # Short excerpt; stored for citation display
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
    amount: Optional[float] = None  # null if unknown or stale
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
    review_themes: list[ReviewTheme] = Field(default_factory=list)
    warranty: Optional[Warranty] = None
    return_policy: Optional[ReturnPolicy] = None
    price_info: Optional[PriceInfo] = None

    # Shorthand pros/limitations for the card view
    pros: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ResearchProductsRequest(BaseModel):
    """POST /api/research-products — request body."""
    request_id: str
    requirements: list = Field(default_factory=list)  # list[Requirement] — validated at route level


class ResearchProductsResponse(BaseModel):
    """POST /api/research-products — initial response (SSE stream follows)."""
    comparison_id: str
    status: str = "processing"
    stream_url: str


class CompareProductsRequest(BaseModel):
    """POST /api/compare-products — request body."""
    request_id: str
    product_ids: list[str] = Field(..., min_length=2, max_length=5)
