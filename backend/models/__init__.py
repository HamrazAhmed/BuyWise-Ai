"""
backend/models/__init__.py
Package marker — import common models here for convenience.
"""

from .common import EvidenceStatus, ApiErrorCode, ApiError, ApiErrorResponse, HealthResponse
from .request import Priority, RequirementSource, Requirement, AnalyzeRequirementsRequest, AnalyzeRequirementsResponse, ShoppingRequest
from .product import Spec, Evidence, ReviewTheme, Warranty, ReturnPolicy, PriceInfo, Product
from .comparison import Comparison, FollowUpRequest, FollowUpResponse, AgentRun

__all__ = [
    "EvidenceStatus", "ApiErrorCode", "ApiError", "ApiErrorResponse", "HealthResponse",
    "Priority", "RequirementSource", "Requirement", "AnalyzeRequirementsRequest",
    "AnalyzeRequirementsResponse", "ShoppingRequest",
    "Spec", "Evidence", "ReviewTheme", "Warranty", "ReturnPolicy", "PriceInfo", "Product",
    "Comparison", "FollowUpRequest", "FollowUpResponse", "AgentRun",
]
