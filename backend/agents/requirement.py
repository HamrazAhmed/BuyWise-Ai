"""
backend/agents/requirement.py
Agent 1 — Requirement Analysis Agent.

Responsibilities:
- Extract structured, prioritized requirements from natural-language text.
- Separate user-stated requirements from inferred ones.
- Return missing_info questions for clarification (0–3 questions).
- NEVER invent requirements the user didn't state or strongly imply.

PRD §10, §8 (F2), §18 (POST /api/analyze-requirements)
"""

import logging
import time
from typing import Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from models.request import (
    Requirement,
    RequirementSource,
    Priority,
    AnalyzeRequirementsResponse,
)
from llm.base import LLMProvider, LLMError
from agents.base import AgentBase, RunState

logger = logging.getLogger(__name__)

# ─── Supported categories ─────────────────────────────────────────────────────

SUPPORTED_CATEGORIES = ["laptop", "desktop", "tablet", "monitor", "keyboard", "headphones", "electronics"]

# ─── Gemini prompt ────────────────────────────────────────────────────────────

REQUIREMENT_EXTRACTION_PROMPT = """
You are analyzing a user's shopping request. Extract structured requirements.

RULES:
1. Only extract requirements the user explicitly stated or strongly implied.
2. Mark explicitly stated requirements as source="user".
3. Mark requirements you infer from context as source="inferred" — use sparingly.
4. Assign priority: must (deal-breaker), high (very important), preferred (nice to have), optional.
5. Do NOT invent requirements not in the text.
6. Budget: if a number is mentioned, extract it. If no budget mentioned, skip it.
7. For missing critical info, add 1–3 clarifying questions to missing_info.
8. Identify the product category (e.g. "laptop", "desktop", "headphones").
9. If the request is not about a purchasable product, set category="unsupported".

User request:
{text}

Respond with valid JSON matching the schema exactly.
"""


class RequirementExtractionOutput(BaseModel):
    """Intermediate schema for Gemini's structured output from Agent 1."""
    request_id: str = Field(default_factory=lambda: f"req_{uuid4().hex[:8]}")
    category: str
    requirements: list[Requirement]
    missing_info: list[str] = Field(default_factory=list, max_length=3)


# ─── Mock fallback data ───────────────────────────────────────────────────────

def _mock_requirements(text: str) -> AnalyzeRequirementsResponse:
    """
    Fallback used when Gemini is unavailable.
    Returns demo requirements so the UI keeps working.
    Shows a notice that AI extraction is unavailable.
    """
    return AnalyzeRequirementsResponse(
        request_id=f"req_{uuid4().hex[:8]}",
        category="laptop",
        requirements=[
            Requirement(key="budget", operator="<=", value="1000 USD", priority=Priority.must, source=RequirementSource.user),
            Requirement(key="ram", operator=">=", value="32 GB", priority=Priority.must, source=RequirementSource.user),
            Requirement(key="os_compatibility", operator="=", value="Linux", priority=Priority.high, source=RequirementSource.user),
            Requirement(key="virtualization", operator="=", value="high", priority=Priority.high, source=RequirementSource.user),
            Requirement(key="upgradeability", operator="=", value="preferred", priority=Priority.preferred, source=RequirementSource.inferred),
        ],
        missing_info=[
            "AI extraction is unavailable — showing example requirements. Preferred screen size?",
            "Portability importance?",
        ],
    )


# ─── Agent ────────────────────────────────────────────────────────────────────

class RequirementAgent(AgentBase):
    """
    Agent 1: Requirement Analysis.
    Converts natural-language text into structured Requirement objects.
    """

    name = "requirement"

    def __init__(self, llm: Optional[LLMProvider] = None) -> None:
        super().__init__(llm=llm)

    async def run(self, text: str) -> AnalyzeRequirementsResponse:
        """
        Main entry point called by the /api/analyze-requirements route.
        Also callable from the orchestrator as part of the full pipeline.

        :param text: Raw user input (10–1000 chars, already validated by Pydantic).
        :returns: AnalyzeRequirementsResponse with requirements and missing_info.
        :raises LLMError: If Gemini fails after retry (caller decides fallback).
        """
        if self.llm is None:
            logger.warning("RequirementAgent: no LLM provider — using mock fallback")
            return _mock_requirements(text)

        start = time.perf_counter()

        # Check for unsupported categories (quick rule-based pre-filter)
        text_lower = text.lower()
        if any(kw in text_lower for kw in ["car", "vehicle", "house", "apartment", "job", "recipe"]):
            return AnalyzeRequirementsResponse(
                request_id=f"req_{uuid4().hex[:8]}",
                category="unsupported",
                requirements=[],
                missing_info=[
                    "BuyWise AI currently supports consumer electronics and laptops. "
                    "Try describing a laptop, headphones, monitor, or similar product."
                ],
            )

        prompt = REQUIREMENT_EXTRACTION_PROMPT.format(text=text)

        try:
            output = await self.llm.generate_json(
                prompt=prompt,
                schema=RequirementExtractionOutput,
                system_prompt=(
                    "You extract purchase requirements. Be conservative — never invent requirements. "
                    "Respond only with valid JSON."
                ),
                temperature=0.0,  # deterministic extraction
            )
        except LLMError:
            raise  # caller (api/analyze.py) handles fallback

        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "RequirementAgent: extracted %d requirements (%d inferred) in %dms",
            len(output.requirements),
            sum(1 for r in output.requirements if r.source == RequirementSource.inferred),
            duration_ms,
        )

        return AnalyzeRequirementsResponse(
            request_id=output.request_id,
            category=output.category,
            requirements=output.requirements,
            missing_info=output.missing_info[:3],  # cap at 3 questions
        )

    async def run_mock(self, text: str) -> AnalyzeRequirementsResponse:
        """Public mock fallback — for use by callers that want a guaranteed result."""
        return _mock_requirements(text)

    async def run_on_state(self, state: RunState) -> RunState:
        """
        Pipeline variant: updates RunState in-place.
        Used by the orchestrator in the full research flow.
        """
        run = self._start_run(state)
        start = time.perf_counter()

        try:
            await state.emit_progress("Understanding requirements", step="requirement")
            result = await self.run(state.raw_text)
            state.requirements = result.requirements
            state.missing_info = result.missing_info
            state.category = result.category
            self._finish_run(run, start)
        except Exception as e:
            self._fail_run(run, str(e), start)
            raise

        return state
