"""
backend/llm/base.py
LLMProvider interface — all LLM interactions go through this abstraction.
Adding a new LLM provider means implementing this interface, not touching agents.

Usage:
    from llm.base import LLMProvider
    from llm.gemini import GeminiProvider

    llm: LLMProvider = GeminiProvider()
    result = await llm.generate_json(prompt, schema=MyPydanticModel)
"""

from abc import ABC, abstractmethod
from typing import Any, Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    """
    Abstract base class for all LLM backends.
    Agents depend on this interface, not on Gemini directly.
    """

    @abstractmethod
    async def generate_json(
        self,
        prompt: str,
        schema: Type[T],
        *,
        system_prompt: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> T:
        """
        Generate a structured JSON response validated against `schema`.
        - Must retry once on transient failure (see PRD §13).
        - Honor upstream rate-limit waits; retry short waits once and surface long/exhausted quota waits.
        - Must raise LLMError on unrecoverable failure.
        """
        ...

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> str:
        """
        Generate a free-text response.
        Same retry/backoff rules as generate_json.
        """
        ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """
        Generate an embedding vector for the given text.
        Used by the RAG service for chunk embedding and retrieval.
        """
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Query embedding; override when a provider supports task-specific vectors."""
        return await self.embed(text)

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts efficiently.
        Default implementation calls embed() in a loop; providers may override.
        """
        ...


class LLMError(Exception):
    """Raised when the LLM provider fails after retries."""
    def __init__(self, message: str, retryable: bool = False, retry_after: int = 0):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after  # seconds


class LLMRateLimitError(LLMError):
    """Raised specifically on 429 / quota-exceeded responses."""
    def __init__(self, retry_after: int = 60):
        super().__init__(
            f"LLM rate limit exceeded. Retry after {retry_after}s.",
            retryable=True,
            retry_after=retry_after,
        )


class LLMSchemaError(LLMError):
    """Raised when the LLM output cannot be parsed as the expected schema."""
    def __init__(self, message: str):
        super().__init__(message, retryable=False)
