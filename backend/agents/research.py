"""
backend/agents/research.py
Agent 2 — Product Research Agent.

Responsibilities:
- Find 3–5 candidate products matching the requirements.
- Use seed dataset first; optionally augment with search API results.
- Return candidates with source URLs and metadata.
- Fallback: if no results, broaden query once; if still none, return seed defaults.

PRD §10, §8 (F4)
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

from models.request import Requirement
from models.product import Product
from agents.base import AgentBase, RunState

logger = logging.getLogger(__name__)

SEED_FILE = Path(__file__).parent.parent / "data" / "seed" / "laptops.json"


class ProductCandidate(BaseModel):
    """A candidate product from research (pre-verification)."""
    id: str
    name: str
    brand: str
    category: str
    model_number: Optional[str] = None
    canonical_url: Optional[str] = None
    image: str = ""
    source_urls: list[dict] = Field(default_factory=list)
    raw_specs: dict = Field(default_factory=dict)
    notes: Optional[str] = None


def _load_seed() -> list[dict]:
    """Load the curated seed dataset."""
    if not SEED_FILE.exists():
        logger.error("Seed file not found: %s", SEED_FILE)
        return []
    with open(SEED_FILE, encoding="utf-8") as f:
        return json.load(f)


def _score_product(product: dict, requirements: list[Requirement]) -> float:
    """
    Simple rule-based relevance score for seed selection.
    Higher = better match. Used to select top 3-5 candidates.
    """
    score = 0.0
    specs = product.get("specs", {})

    for req in requirements:
        key = req.key.lower()
        value = req.value.lower()
        operator = req.operator

        if key == "budget":
            # Budget matching: prefer products with no price (unknown) over definitely too expensive
            price = product.get("price_usd")
            if price is None:
                score += 0.5  # unknown price — might fit
            else:
                try:
                    budget_val = float(value.replace("usd", "").replace("$", "").strip())
                    if operator in ("<=", "<") and price <= budget_val:
                        score += 2.0 if req.priority == "must" else 1.0
                    elif operator in (">", ">=") and price >= budget_val:
                        score += 1.0
                except ValueError:
                    pass

        elif key == "ram":
            ram = specs.get("ram_gb")
            if ram is None:
                # Has configurable RAM — might meet requirement
                if specs.get("ram_note") or specs.get("ram_upgradeable"):
                    score += 0.5
            else:
                try:
                    req_val = float("".join(c for c in value if c.isdigit() or c == "."))
                    if operator in (">=", ">") and ram >= req_val:
                        score += 2.0 if req.priority == "must" else 1.0
                except ValueError:
                    pass

        elif key in ("os_compatibility", "linux", "linux_compatibility", "linux support"):
            linux_support = specs.get("linux_support", "")
            if "native" in linux_support or "certified" in linux_support:
                score += 2.0
            elif "strong" in linux_support:
                score += 1.5
            elif "partial" in linux_support:
                score += 0.5

        elif key == "virtualization":
            virt = specs.get("virtualization", "")
            if virt and "not supported" not in virt.lower():
                score += 1.0

        elif key == "upgradeability":
            if specs.get("ram_upgradeable"):
                score += 1.0

    # Prefer lighter products for portability
    weight = specs.get("weight_lbs")
    if weight and weight < 3.5:
        score += 0.3

    return score


def select_candidates(products: list[dict], requirements: list[Requirement],
                      max_candidates: int = 5) -> list[dict]:
    """Score and return the top N seed products for the given requirements."""
    scored = [(p, _score_product(p, requirements)) for p in products]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [p for p, _ in scored[:max_candidates]]


def seed_product_to_product(p: dict) -> Product:
    """Convert a seed record dict into a Product model."""
    # Generate initials for the card image
    words = p["name"].split()
    initials = "".join(w[0].upper() for w in words if w)[:2]

    # Flatten specs for the product
    specs = []
    raw_specs = p.get("specs", {})
    for k, v in raw_specs.items():
        if v is not None:
            specs.append({
                "key": k.replace("_", " ").title(),
                "value": str(v),
                "status": "supported",  # seed data = supported (not yet verified)
                "evidence_ids": [],
            })

    return Product(
        id=p["id"],
        name=p["name"],
        brand=p.get("brand", ""),
        category=p.get("category", "laptop"),
        model_number=p.get("model_number"),
        canonical_url=p.get("canonical_url"),
        image=initials,
        specs=[],  # Specs filled in by Agent 3 (Spec Verification)
        pros=[],
        limitations=[],
    )


class ProductResearchAgent(AgentBase):
    """
    Agent 2: Product Research.
    Returns 3–5 candidate products for the given requirements.
    """

    name = "research"

    async def run(self, state: RunState) -> RunState:
        """
        Find candidate products. Uses seed data filtered by requirements.
        Future: augment with search API results.
        """
        run = self._start_run(state)
        start = time.perf_counter()

        try:
            await state.emit_progress("Finding products", step="research")

            seed_products = _load_seed()
            if not seed_products:
                logger.warning("Seed dataset empty — no candidates found")
                self._finish_run(run, start)
                return state

            # Select top 3–5 candidates based on requirements
            candidates = select_candidates(
                seed_products,
                state.requirements,
                max_candidates=5,
            )

            if not candidates:
                logger.warning("No seed candidates matched requirements")
                # Fallback: return top 3 from seed regardless
                candidates = seed_products[:3]

            logger.info(
                "ProductResearchAgent: selected %d candidates from seed dataset",
                len(candidates),
            )

            state.candidate_products = [seed_product_to_product(c) for c in candidates]
            # Store raw seed data for Agents 3–6 to use
            state._seed_candidates = candidates  # type: ignore[attr-defined]

            self._finish_run(run, start)
        except Exception as e:
            self._fail_run(run, str(e), start)
            logger.exception("ProductResearchAgent failed")
            raise

        return state
