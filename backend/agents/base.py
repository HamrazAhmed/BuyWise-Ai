"""
backend/agents/base.py
Base classes and shared state for the BuyWise AI agent pipeline.
"""

import time
from abc import ABC, abstractmethod
from typing import Any, Optional
from dataclasses import dataclass, field
from uuid import uuid4

from models.request import Requirement, ShoppingRequestStatus
from models.product import Product
from models.comparison import Comparison, AgentRun


@dataclass
class RunState:
    """
    Shared state passed through the agent pipeline.
    Agents read from and write to this object.
    Progressive filling: Agents 3–6 add their results for each product.
    """
    # Identifiers
    request_id: str = field(default_factory=lambda: str(uuid4()))
    comparison_id: str = field(default_factory=lambda: str(uuid4()))

    # Input
    raw_text: str = ""
    category: str = "laptop"

    # Agent 1 output
    requirements: list[Requirement] = field(default_factory=list)
    missing_info: list[str] = field(default_factory=list)

    # Agent 2 output
    candidate_products: list[Product] = field(default_factory=list)

    # Agents 3–6 output (by product id)
    verified_specs: dict[str, list] = field(default_factory=dict)
    review_themes: dict[str, list] = field(default_factory=dict)
    warranties: dict[str, Any] = field(default_factory=dict)
    prices: dict[str, Any] = field(default_factory=dict)

    # Agent 7 output
    evidence_by_claim: dict[str, list] = field(default_factory=dict)

    # Agent 8 output
    comparison: Optional[Comparison] = None

    # Telemetry
    agent_runs: list[AgentRun] = field(default_factory=list)
    status: str = ShoppingRequestStatus.pending
    error: Optional[str] = None
    notices: list[str] = field(default_factory=list)

    # SSE progress callback (set by orchestrator)
    _progress_callback: Optional[Any] = field(default=None, repr=False)

    async def emit_progress(self, message: str, step: str = "") -> None:
        """Emit a safe status message to the SSE stream (no chain-of-thought)."""
        if self._progress_callback:
            await self._progress_callback({"type": "status", "message": message, "step": step})


class AgentBase(ABC):
    """
    Abstract base class for all BuyWise AI agents.
    Each agent is a single-responsibility async callable.
    """

    name: str = "base"

    def __init__(self, llm=None) -> None:
        self.llm = llm  # LLMProvider or None (mock mode)

    @abstractmethod
    async def run(self, state: RunState) -> RunState:
        """Execute this agent and return the updated state."""
        ...

    def _start_run(self, state: RunState) -> AgentRun:
        run = AgentRun(request_id=state.request_id, agent=self.name, status="running")
        state.agent_runs.append(run)
        return run

    def _finish_run(self, run: AgentRun, start_time: float, tokens: int = 0) -> None:
        run.status = "done"
        run.duration_ms = int((time.perf_counter() - start_time) * 1000)
        run.tokens = tokens

    def _fail_run(self, run: AgentRun, error: str, start_time: float) -> None:
        run.status = "error"
        run.error = error
        run.duration_ms = int((time.perf_counter() - start_time) * 1000)
