"""
backend/data/demo_cache.py
Pre-warmed demo comparison cache (PRD §23: "Pre-warm cache for the demo scenario").

The demo scenario (PRD §29):
  "I need a laptop under $1,000 for cybersecurity. I use Linux and run
   multiple VMs. I want at least 32GB RAM."

This module produces a pre-built Comparison for that exact query.
When the orchestrator detects a requirements hash matching the demo query,
it returns this cached result instantly — no LLM calls, zero latency.

Also serves as a fallback when GEMINI_API_KEY is absent (mock mode).
"""

import json
import logging
from datetime import datetime, timezone

from models.request import Requirement
from models.product import (
    Product, Spec, Evidence, ReviewTheme, Warranty,
    ReturnPolicy, PriceInfo,
)
from models.comparison import (
    Comparison, RequirementAnalysis, ProductAssessment,
)
from models.common import EvidenceStatus

logger = logging.getLogger(__name__)


# ─── Demo requirements (PRD §29) ─────────────────────────────────────────────

DEMO_REQUIREMENTS = [
    Requirement(key="budget", operator="<=", value="1000 USD", priority="must", source="user"),
    Requirement(key="ram", operator=">=", value="32 GB", priority="must", source="user"),
    Requirement(key="os_compatibility", operator="=", value="Linux", priority="high", source="user"),
    Requirement(key="virtualization", operator="=", value="high", priority="high", source="user"),
    Requirement(key="upgradeability", operator="=", value="preferred", priority="preferred", source="inferred"),
]


# ─── Demo evidence entries ────────────────────────────────────────────────────

def _evidence(eid: str, title: str, url: str, source_type: str, snippet: str) -> Evidence:
    return Evidence(
        id=eid,
        title=title,
        source_url=url,
        source_type=source_type,
        snippet=snippet,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )


# ─── Demo products (selected from seed data) ─────────────────────────────────

def _build_demo_products() -> list[Product]:
    """Build 3 demo products with full spec/review/warranty/price data."""

    # Product 1: Framework Laptop 16
    fw16 = Product(
        id="framework-laptop-16",
        name="Framework Laptop 16",
        brand="Framework",
        category="laptop",
        model_number="FL16-AMD",
        canonical_url="https://frame.work/products/laptop-16",
        image="FL",
        score="4/5 requirements met",
        specs=[
            Spec(key="CPU", value="AMD Ryzen 7 7840HS", status=EvidenceStatus.verified,
                 evidence_ids=["e_fw_1"]),
            Spec(key="GPU", value="AMD Radeon 780M (integrated)", status=EvidenceStatus.verified,
                 evidence_ids=["e_fw_1"]),
            Spec(key="RAM", value="32GB DDR5-5600", status=EvidenceStatus.verified,
                 evidence_ids=["e_fw_1"]),
            Spec(key="RAM Upgradeable", value="Yes (2 SO-DIMM slots, up to 64GB)", status=EvidenceStatus.verified,
                 evidence_ids=["e_fw_1"]),
            Spec(key="Storage", value="1TB NVMe SSD", status=EvidenceStatus.supported,
                 evidence_ids=["e_fw_2"]),
            Spec(key="Display", value='16" 2560x1600 IPS, 165Hz', status=EvidenceStatus.verified,
                 evidence_ids=["e_fw_1"]),
            Spec(key="Battery", value="85Wh", status=EvidenceStatus.verified,
                 evidence_ids=["e_fw_1"]),
            Spec(key="Weight", value="5.29 lbs", status=EvidenceStatus.verified,
                 evidence_ids=["e_fw_1"]),
            Spec(key="OS", value="Linux (native support)", status=EvidenceStatus.verified,
                 evidence_ids=["e_fw_1"]),
            Spec(key="Virtualization", value="AMD-V supported", status=EvidenceStatus.verified,
                 evidence_ids=["e_fw_1"]),
            Spec(key="Ports", value="Modular expansion bay system (user-configurable)", status=EvidenceStatus.verified,
                 evidence_ids=["e_fw_1"]),
        ],
        review_themes=[
            ReviewTheme(theme="Upgradeability", sentiment="positive",
                        summary="Users praise the modular design — RAM, storage, ports, and even GPU modules are user-replaceable. (Opinion)"),
            ReviewTheme(theme="Linux support", sentiment="positive",
                        summary="Framework officially supports Linux; users report excellent out-of-box experience with Ubuntu and Fedora. (Opinion)"),
            ReviewTheme(theme="Weight", sentiment="negative",
                        summary="At 5.29 lbs, several reviewers note it's heavier than expected for daily carry. (Opinion)"),
        ],
        warranty=Warranty(duration_months=12, coverage="Limited hardware warranty", conditions="User-upgradeable parts covered", completeness="complete"),
        return_policy=ReturnPolicy(window_days=30, conditions="Unopened or defective", seller_dependent=False),
        price_info=PriceInfo(amount=949.0, currency="USD", seller="Framework Direct",
                             fetched_at=datetime.now(timezone.utc).isoformat(), is_stale=False),
        pros=["Fully upgradeable RAM/storage/ports", "Native Linux support", "32GB DDR5 within budget", "Strong virtualization support"],
        limitations=["Heavier than ultrabooks (5.29 lbs)", "Integrated GPU only (no dGPU in base config)", "Newer company — limited long-term track record"],
    )

    # Product 2: System76 Pangolin
    sys76 = Product(
        id="system76-pangolin",
        name="System76 Pangolin",
        brand="System76",
        category="laptop",
        model_number="pang13",
        canonical_url="https://system76.com/laptops/pangolin",
        image="SP",
        score="4/5 requirements met",
        specs=[
            Spec(key="CPU", value="AMD Ryzen 7 7840U", status=EvidenceStatus.verified,
                 evidence_ids=["e_s76_1"]),
            Spec(key="GPU", value="AMD Radeon 780M", status=EvidenceStatus.verified,
                 evidence_ids=["e_s76_1"]),
            Spec(key="RAM", value="32GB DDR5-5600", status=EvidenceStatus.verified,
                 evidence_ids=["e_s76_1"]),
            Spec(key="RAM Upgradeable", value="Yes (2 SO-DIMM slots, up to 64GB)", status=EvidenceStatus.verified,
                 evidence_ids=["e_s76_1"]),
            Spec(key="Storage", value="500GB NVMe SSD", status=EvidenceStatus.supported,
                 evidence_ids=["e_s76_1"]),
            Spec(key="Display", value='15.6" 1920x1200 IPS, 144Hz', status=EvidenceStatus.verified,
                 evidence_ids=["e_s76_1"]),
            Spec(key="Battery", value="54Wh", status=EvidenceStatus.supported,
                 evidence_ids=["e_s76_2"]),
            Spec(key="Weight", value="4.2 lbs", status=EvidenceStatus.verified,
                 evidence_ids=["e_s76_1"]),
            Spec(key="OS", value="Pop!_OS (Linux)", status=EvidenceStatus.verified,
                 evidence_ids=["e_s76_1"]),
            Spec(key="Virtualization", value="AMD-V supported", status=EvidenceStatus.verified,
                 evidence_ids=["e_s76_1"]),
            Spec(key="Ports", value="USB-C, 2x USB-A, HDMI, microSD, headphone jack", status=EvidenceStatus.verified,
                 evidence_ids=["e_s76_1"]),
        ],
        review_themes=[
            ReviewTheme(theme="Linux experience", sentiment="positive",
                        summary="Ships with Pop!_OS pre-installed; firmware updates through System76's own tool. (Opinion)"),
            ReviewTheme(theme="Build quality", sentiment="mixed",
                        summary="Some reviewers note the plastic chassis feels less premium than metal competitors, but say it's durable. (Opinion)"),
            ReviewTheme(theme="Battery life", sentiment="negative",
                        summary="54Wh battery is on the smaller side; reviewers report 4-5 hours of mixed use. (Opinion)"),
        ],
        warranty=Warranty(duration_months=12, coverage="Limited hardware warranty", conditions="Standard System76 warranty", completeness="complete"),
        return_policy=ReturnPolicy(window_days=30, conditions="Minus restocking fee if opened", seller_dependent=False),
        price_info=PriceInfo(amount=899.0, currency="USD", seller="System76 Direct",
                             fetched_at=datetime.now(timezone.utc).isoformat(), is_stale=False),
        pros=["Ships with Linux (Pop!_OS)", "Upgradeable RAM up to 64GB", "Within budget at $899", "Strong virtualization support", "Lighter than Framework 16"],
        limitations=["Plastic chassis (less premium feel)", "Smaller battery (54Wh)", "Lower resolution display (1080p)"],
    )

    # Product 3: Lenovo ThinkPad E16 Gen 2 (AMD)
    tp_e16 = Product(
        id="lenovo-thinkpad-e16-gen2",
        name="ThinkPad E16 Gen 2 (AMD)",
        brand="Lenovo",
        category="laptop",
        model_number="21M5001TUS",
        canonical_url="https://www.lenovo.com/us/en/p/laptops/thinkpad/thinkpade/thinkpad-e16-gen-2-16-inch-amd/",
        image="TE",
        score="3/5 requirements met",
        specs=[
            Spec(key="CPU", value="AMD Ryzen 7 7730U", status=EvidenceStatus.verified,
                 evidence_ids=["e_tp_1"]),
            Spec(key="GPU", value="AMD Radeon Graphics", status=EvidenceStatus.verified,
                 evidence_ids=["e_tp_1"]),
            Spec(key="RAM", value="16GB DDR4-3200 (configurable to 32GB)", status=EvidenceStatus.supported,
                 evidence_ids=["e_tp_1", "e_tp_2"]),
            Spec(key="RAM Upgradeable", value="Yes (1 SO-DIMM slot)", status=EvidenceStatus.verified,
                 evidence_ids=["e_tp_1"]),
            Spec(key="Storage", value="512GB NVMe SSD", status=EvidenceStatus.verified,
                 evidence_ids=["e_tp_1"]),
            Spec(key="Display", value='16" 1920x1200 IPS', status=EvidenceStatus.verified,
                 evidence_ids=["e_tp_1"]),
            Spec(key="Battery", value="47Wh", status=EvidenceStatus.supported,
                 evidence_ids=["e_tp_2"]),
            Spec(key="Weight", value="4.41 lbs", status=EvidenceStatus.verified,
                 evidence_ids=["e_tp_1"]),
            Spec(key="OS", value="Windows 11 Pro (Linux: strong community support)", status=EvidenceStatus.verified,
                 evidence_ids=["e_tp_1"]),
            Spec(key="Virtualization", value="VT-x, VT-d supported", status=EvidenceStatus.verified,
                 evidence_ids=["e_tp_1"]),
            Spec(key="Ports", value="USB-C, 2x USB-A, HDMI, headphone jack", status=EvidenceStatus.verified,
                 evidence_ids=["e_tp_1"]),
        ],
        review_themes=[
            ReviewTheme(theme="Keyboard", sentiment="positive",
                        summary="ThinkPad keyboard consistently rated as best-in-class for typing comfort. (Opinion)"),
            ReviewTheme(theme="Price/value", sentiment="positive",
                        summary="Often found under $700, making it one of the best-value ThinkPads. (Opinion)"),
            ReviewTheme(theme="Linux compatibility", sentiment="positive",
                        summary="Community reports strong Linux compatibility, though not officially certified. (Opinion)"),
        ],
        warranty=Warranty(duration_months=12, coverage="Depot repair", conditions="Standard Lenovo warranty", completeness="complete"),
        return_policy=ReturnPolicy(window_days=30, conditions="Standard Lenovo return policy", seller_dependent=True),
        price_info=PriceInfo(amount=689.0, currency="USD", seller="Lenovo.com",
                             fetched_at=datetime.now(timezone.utc).isoformat(), is_stale=False),
        pros=["Excellent keyboard", "Best price ($689)", "ThinkPad reliability & durability", "Upgradeable RAM slot"],
        limitations=["Ships with Windows (Linux not pre-installed)", "Base config is 16GB RAM (must upgrade)", "Smaller 47Wh battery", "Older Ryzen 7730U (Zen 3 refresh)"],
    )

    return [fw16, sys76, tp_e16]


# ─── Demo evidence ────────────────────────────────────────────────────────────

DEMO_EVIDENCE = {
    "e_fw_1": _evidence("e_fw_1", "Framework Laptop 16 Specs", "https://frame.work/products/laptop-16", "primary",
                         "AMD Ryzen 7 7840HS, up to 64GB DDR5 RAM, modular expansion bay system"),
    "e_fw_2": _evidence("e_fw_2", "Framework Laptop 16 Listing", "https://frame.work/products/laptop-16", "primary",
                         "Storage: 1TB WD_BLACK SN770 NVMe SSD, user-replaceable"),
    "e_s76_1": _evidence("e_s76_1", "System76 Pangolin Specs", "https://system76.com/laptops/pangolin", "primary",
                          "AMD Ryzen 7 7840U, 32GB DDR5-5600 (2 SO-DIMM, up to 64GB), Pop!_OS"),
    "e_s76_2": _evidence("e_s76_2", "System76 Pangolin Battery", "https://system76.com/laptops/pangolin", "primary",
                          "54Wh 4-cell battery; approximately 4-6 hours mixed use"),
    "e_tp_1": _evidence("e_tp_1", "ThinkPad E16 Gen 2 PSREF", "https://psref.lenovo.com/Product/ThinkPad/ThinkPad_E16_Gen_2_AMD", "primary",
                         "Ryzen 7 7730U, up to 32GB DDR4, 1x SO-DIMM slot, VT-x/VT-d"),
    "e_tp_2": _evidence("e_tp_2", "ThinkPad E16 Gen 2 Listing", "https://www.lenovo.com/us/en/p/laptops/thinkpad/thinkpade/thinkpad-e16-gen-2-16-inch-amd/", "primary",
                         "47Wh battery, 16GB base RAM configurable, starting at $689"),
}


# ─── Build the full demo comparison ──────────────────────────────────────────

def build_demo_comparison(comparison_id: str = "cmp_demo", request_id: str = "req_demo") -> Comparison:
    """Build a complete pre-warmed Comparison for the demo scenario."""
    products = _build_demo_products()

    requirement_analysis = [
        RequirementAnalysis(
            requirement=DEMO_REQUIREMENTS[0],  # budget <= 1000 USD
            product_assessments=[
                ProductAssessment(product_id="framework-laptop-16", match="✓",
                                  explanation="$949 — within the $1,000 budget.", evidence_ids=["e_fw_1"]),
                ProductAssessment(product_id="system76-pangolin", match="✓",
                                  explanation="$899 — well within budget, leaving room for upgrades.", evidence_ids=["e_s76_1"]),
                ProductAssessment(product_id="lenovo-thinkpad-e16-gen2", match="✓",
                                  explanation="$689 — most affordable option, $311 under budget.", evidence_ids=["e_tp_2"]),
            ],
        ),
        RequirementAnalysis(
            requirement=DEMO_REQUIREMENTS[1],  # ram >= 32 GB
            product_assessments=[
                ProductAssessment(product_id="framework-laptop-16", match="✓",
                                  explanation="32GB DDR5 standard, upgradeable to 64GB.", evidence_ids=["e_fw_1"]),
                ProductAssessment(product_id="system76-pangolin", match="✓",
                                  explanation="32GB DDR5 standard, upgradeable to 64GB.", evidence_ids=["e_s76_1"]),
                ProductAssessment(product_id="lenovo-thinkpad-e16-gen2", match="?",
                                  explanation="Ships with 16GB; configurable to 32GB but may push above base price.", evidence_ids=["e_tp_1"]),
            ],
        ),
        RequirementAnalysis(
            requirement=DEMO_REQUIREMENTS[2],  # Linux
            product_assessments=[
                ProductAssessment(product_id="framework-laptop-16", match="✓",
                                  explanation="Official Linux support; ships without OS or with Linux option.", evidence_ids=["e_fw_1"]),
                ProductAssessment(product_id="system76-pangolin", match="✓",
                                  explanation="Ships with Pop!_OS (Linux); System76 is a Linux-first vendor.", evidence_ids=["e_s76_1"]),
                ProductAssessment(product_id="lenovo-thinkpad-e16-gen2", match="✓",
                                  explanation="Ships with Windows; strong Linux community support but not officially certified for Linux.", evidence_ids=["e_tp_1"]),
            ],
        ),
        RequirementAnalysis(
            requirement=DEMO_REQUIREMENTS[3],  # virtualization
            product_assessments=[
                ProductAssessment(product_id="framework-laptop-16", match="✓",
                                  explanation="AMD-V supported; Ryzen 7 7840HS handles VMs well.", evidence_ids=["e_fw_1"]),
                ProductAssessment(product_id="system76-pangolin", match="✓",
                                  explanation="AMD-V supported; designed for developer workloads including VMs.", evidence_ids=["e_s76_1"]),
                ProductAssessment(product_id="lenovo-thinkpad-e16-gen2", match="✓",
                                  explanation="VT-x and VT-d supported; older Ryzen 7730U may be slower with heavy VMs.", evidence_ids=["e_tp_1"]),
            ],
        ),
        RequirementAnalysis(
            requirement=DEMO_REQUIREMENTS[4],  # upgradeability
            product_assessments=[
                ProductAssessment(product_id="framework-laptop-16", match="✓",
                                  explanation="Industry-leading upgradeability: RAM, storage, ports, GPU module, battery all user-replaceable.", evidence_ids=["e_fw_1"]),
                ProductAssessment(product_id="system76-pangolin", match="✓",
                                  explanation="RAM and storage user-upgradeable (2 SO-DIMM slots).", evidence_ids=["e_s76_1"]),
                ProductAssessment(product_id="lenovo-thinkpad-e16-gen2", match="?",
                                  explanation="1 SO-DIMM slot (partial upgradeability); storage upgradeable.", evidence_ids=["e_tp_1"]),
            ],
        ),
    ]

    requirement_matches = {
        "framework-laptop-16": ["✓", "✓", "✓", "✓", "✓"],
        "system76-pangolin": ["✓", "✓", "✓", "✓", "✓"],
        "lenovo-thinkpad-e16-gen2": ["✓", "?", "✓", "✓", "?"],
    }

    tradeoffs = [
        "The Framework Laptop 16 offers the best upgradeability (modular design) but is heaviest at 5.29 lbs and closest to the budget ceiling at $949.",
        "The System76 Pangolin delivers the best out-of-box Linux experience (Pop!_OS) at a mid-range price ($899) with excellent virtualization support, but has a smaller battery and plastic build.",
        "The ThinkPad E16 Gen 2 is the most affordable ($689) with the best keyboard, but ships with only 16GB RAM and Windows — requiring upgrades and OS installation to fully meet requirements.",
        "If portability matters: System76 (4.2 lbs) > ThinkPad E16 (4.41 lbs) > Framework 16 (5.29 lbs).",
        "If future-proofing matters: Framework (modular everything) > System76 (RAM+storage) > ThinkPad E16 (limited slots).",
    ]

    return Comparison(
        id=comparison_id,
        request_id=request_id,
        products=products,
        requirement_matches=requirement_matches,
        tradeoffs=tradeoffs,
        requirement_analysis=requirement_analysis,
    )
