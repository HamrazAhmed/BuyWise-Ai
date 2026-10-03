"""
backend/rag/store.py
Vector store abstraction — wraps either Supabase pgvector or Chroma in-memory.

Usage:
    store = get_vector_store()
    await store.upsert(chunks)
    results = await store.search(query_vector, product_id=..., source_type=..., top_k=8)

Implemented in Step 5.
"""

import logging
import os
from typing import Optional, Protocol
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """A text chunk with embedding and metadata."""
    id: str
    product_id: str
    source_id: str
    source_type: str          # 'primary' | 'secondary'
    url: str
    content: str
    embedding: list[float]
    fetched_at: str           # ISO datetime string


class VectorStore(Protocol):
    """Protocol (interface) for vector stores."""

    async def upsert(self, chunks: list[Chunk]) -> None:
        """Store or update chunks and their embeddings."""
        ...

    async def search(
        self,
        query_vector: list[float],
        *,
        product_id: Optional[str] = None,
        source_type: Optional[str] = None,
        top_k: int = 8,
    ) -> list[Chunk]:
        """
        Retrieve the top-k most similar chunks.
        Filter by product_id and/or source_type if provided.
        """
        ...


class InMemoryVectorStore:
    """
    Simple in-memory vector store using cosine similarity.
    Used for local development when Supabase is not configured.
    Falls back to this if DATABASE_URL is not set.
    """

    def __init__(self) -> None:
        self._chunks: list[Chunk] = []

    async def upsert(self, chunks: list[Chunk]) -> None:
        # Remove existing chunks with same ID, then add new ones
        existing_ids = {c.id for c in chunks}
        self._chunks = [c for c in self._chunks if c.id not in existing_ids]
        self._chunks.extend(chunks)

    async def search(
        self,
        query_vector: list[float],
        *,
        product_id: Optional[str] = None,
        source_type: Optional[str] = None,
        top_k: int = 8,
    ) -> list[Chunk]:
        candidates = self._chunks
        if product_id:
            candidates = [c for c in candidates if c.product_id == product_id]
        if source_type:
            candidates = [c for c in candidates if c.source_type == source_type]

        if not candidates:
            return []

        # Cosine similarity
        def cosine(a: list[float], b: list[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            mag_a = sum(x * x for x in a) ** 0.5
            mag_b = sum(x * x for x in b) ** 0.5
            if mag_a == 0 or mag_b == 0:
                return 0.0
            return dot / (mag_a * mag_b)

        scored = sorted(candidates, key=lambda c: cosine(query_vector, c.embedding), reverse=True)
        return scored[:top_k]


# Singleton store instance (per-process; reset on cold-start)
_store_instance: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """
    Return the appropriate vector store based on environment config.
    - If DATABASE_URL is set: use Supabase pgvector (Step 5 implementation).
    - Otherwise: use in-memory store (local dev fallback).
    """
    global _store_instance
    if _store_instance is not None:
        return _store_instance

    if os.getenv("DATABASE_URL"):
        # TODO (Step 5): implement SupabaseVectorStore
        logger.info("DATABASE_URL set — will use Supabase pgvector (not yet implemented, falling back to in-memory)")
    else:
        logger.info("DATABASE_URL not set — using in-memory vector store (local dev mode)")

    _store_instance = InMemoryVectorStore()
    return _store_instance
