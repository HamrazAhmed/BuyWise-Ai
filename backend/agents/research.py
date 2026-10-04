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


def _score_product(product: dict, requirements: list[Requirement]) -> tuple[int, float]:
    """Rank known must-have failures behind uncertain and satisfied candidates."""
    from agents.matching import match_requirement
    from models.product import Spec
    specs = [Spec(key=k, value=str(v), status="supported", evidence_ids=[f"seed_{product['id']}"])
             for k, v in product.get("specs", {}).items() if v is not None]
    if product.get("price_usd") is not None:
        specs.append(Spec(key="budget", value=f"{product['price_usd']} USD", status="supported", evidence_ids=[f"seed_{product['id']}"]))
    if product.get('market') == 'PK' and product.get('amount') is not None:
        from datetime import datetime, timezone, timedelta
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(product['observed_at'].replace('Z', '+00:00'))
            fresh = timedelta(0) <= age <= timedelta(hours=24)
        except (ValueError, TypeError):
            fresh = False
        specs.append(Spec(key='budget', value=f"{product['amount']} {product['currency']}", status='supported' if fresh else 'insufficient', evidence_ids=[product['source_id']]))
    if product.get("documents"):
        from datetime import datetime, timezone, timedelta
        documents = {d["payload"]["kind"]: d for d in product["documents"]}
        specs = [Spec.model_validate(s) for s in documents["specs"]["payload"]["specs"]]
        price = documents["price"]["payload"]
        stale = datetime.now(timezone.utc) - datetime.fromisoformat(price["fetched_at"].replace("Z", "+00:00")) > timedelta(hours=24)
        if price["amount"] is not None:
            specs.append(Spec(key="budget", value=f"{price['amount']} USD",
                              status="insufficient" if stale else "supported",
                              evidence_ids=[documents["price"]["source_id"]]))
    weights = {"must": 4, "high": 3, "preferred": 2, "optional": 1}
    matches = [(r, match_requirement(r, specs)[0]) for r in requirements]
    failures = sum(1 for r, m in matches if r.priority == "must" and m == "✕")
    score = sum(weights[r.priority] for r, m in matches if m == "✓")
    return -failures, score


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

            if getattr(self.llm, "data_mode", None) == "fixture":
                from llm.fixture import load_fixtures
                seed_products = load_fixtures()
            else:
                import os
                if os.getenv('BUYWISE_MARKET', 'PK') == 'PK':
                    from data.pakistan import prepare
                    seed_products = await prepare(self.llm, state.notices)
                else:
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
