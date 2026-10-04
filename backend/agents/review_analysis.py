"""
backend/agents/review_analysis.py
Agent 4 — Review Analysis Agent.

Responsibilities:
- Extract review themes from permitted review text.
- Label all review content as opinion (never fact).
- No fabricated quotes.
- If no data: return "Insufficient review data".

PRD §10, §8 (F6)
"""

import logging
import time
from pydantic import BaseModel, Field

from models.product import ReviewTheme
from agents.base import AgentBase, RunState
from llm.gemini import wrap_context
from rag.retrieve import retrieve, chunks_to_context

logger = logging.getLogger(__name__)

REVIEW_THEMES = [
    "Performance", "Battery life", "Thermals", "Build quality",
    "Display", "Keyboard", "Noise level", "Linux compatibility",
    "Value for money", "Common complaints", "Common positives",
]

REVIEW_PROMPT = """
You are analyzing user reviews and opinions for a laptop product.

PRODUCT: {product_name}

IMPORTANT:
- All output is labeled as user opinion, not verified fact.
- Do NOT fabricate quotes or invent themes.
- If no review data is present in the context, say so.

{context}

For each of these themes, provide a brief 1-2 sentence summary based ONLY on the context:
Themes: {themes}

If a theme has no data, set sentiment="neutral" and summary="Insufficient data".
Mark ALL summaries as opinion, not fact.
"""


class ReviewOutput(BaseModel):
    themes: list[ReviewTheme] = Field(default_factory=list)
    # Each: {theme, sentiment, summary}


class ReviewAnalysisAgent(AgentBase):
    """Agent 4: Review Analysis (opinion labeling, no fabricated content)."""

    name = "review_analysis"

    async def run(self, state: RunState) -> RunState:
        run = self._start_run(state)
        start = time.perf_counter()

        try:
            await state.emit_progress("Analyzing reviews", step="review_analysis")

            import asyncio
            tasks = [
                self._analyze_product(p, state)
                for p in state.candidate_products
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for product, result in zip(state.candidate_products, results):
                if isinstance(result, Exception):
                    logger.error("Review analysis failed for %s: %s", product.name, result)
                    state.review_themes[product.id] = []
                else:
                    state.review_themes[product.id] = result

            self._finish_run(run, start)
        except Exception as e:
            self._fail_run(run, str(e), start)
            raise

        return state

    async def _analyze_product(self, product, state: RunState) -> list[ReviewTheme]:
        if self.llm is None:
            return [ReviewTheme(
                theme=t,
                sentiment="neutral",
                summary="Review analysis unavailable in mock mode.",
            ) for t in REVIEW_THEMES[:5]]

        # Retrieve secondary (review) chunks specifically
        from rag.store import get_vector_store
        if not any(c.kind == 'reviews' for c in await get_vector_store().for_product(product.id)):
            return []
        chunks = await retrieve(
            query=f"{product.name} user review performance battery build quality",
            product_id=product.id,
            source_type="secondary",
            top_k=6,
            llm_provider=self.llm,
            notices=state.notices,
        )
        chunks = [c for c in chunks if c.kind == 'reviews']

        if not chunks:
            return [ReviewTheme(
                theme="Overall",
                sentiment="neutral",
                summary="Insufficient review data.",
            )]

        context = wrap_context(chunks_to_context(chunks))
        prompt = REVIEW_PROMPT.format(
            product_name=product.name,
            themes=", ".join(REVIEW_THEMES),
            context=context,
        )

        try:
            output = await self.llm.generate_json(
                prompt=prompt,
                schema=ReviewOutput,
                temperature=0.1,
            )
            return output.themes
        except Exception as e:
            logger.error("Review LLM call failed for %s: %s", product.name, e)
            return []
