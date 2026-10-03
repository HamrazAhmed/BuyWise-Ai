"""
backend/rag/retrieve.py
Retrieval and reranking for the RAG pipeline.

PRD §11: top-k = 6–8 per product, metadata-filtered.
Rerank: primary > secondary, newer > older (no extra LLM call).
"""

import logging
from typing import Optional

from .store import Chunk, get_vector_store

logger = logging.getLogger(__name__)


async def retrieve(
    query: str,
    *,
    product_id: Optional[str] = None,
    source_type: Optional[str] = None,
    top_k: int = 8,
    llm_provider=None,
) -> list[Chunk]:
    """
    Retrieve top-k chunks relevant to `query`, optionally filtered by
    product_id and/or source_type.

    If llm_provider is available, uses it to embed the query.
    Falls back to zero-vector (returns random chunks) when no LLM.

    Returns reranked chunks (primary sources first, then by recency).
    """
    # Embed the query
    query_vector = await _embed_query(query, llm_provider)

    store = get_vector_store()
    # Fetch more than top_k so reranking has candidates to work with
    raw_results = await store.search(
        query_vector,
        product_id=product_id,
        source_type=source_type,
        top_k=top_k * 2,  # over-fetch for reranking
    )

    # Rerank
    reranked = rerank(raw_results)

    return reranked[:top_k]


def rerank(chunks: list[Chunk]) -> list[Chunk]:
    """
    Rule-based reranking (PRD §11):
    1. Primary sources before secondary.
    2. Within same tier, newer fetched_at first.
    No extra LLM call needed.
    """
    def sort_key(chunk: Chunk):
        primary_first = 0 if chunk.source_type == "primary" else 1
        # Descending date: negate timestamp string comparison (ISO format sorts lexicographically)
        recency = chunk.fetched_at if chunk.fetched_at else ""
        return (primary_first, tuple(-ord(c) for c in recency))

    return sorted(chunks, key=sort_key)


def chunks_to_context(chunks: list[Chunk]) -> list[dict]:
    """
    Convert Chunk objects to the dict format expected by llm.gemini.wrap_context().
    """
    return [
        {
            "content": chunk.content,
            "source_type": chunk.source_type,
            "url": chunk.url,
            "source_id": chunk.source_id,
        }
        for chunk in chunks
    ]


async def _embed_query(query: str, llm_provider) -> list[float]:
    """Embed a query string. Returns zero vector if no LLM."""
    if llm_provider is None:
        return [0.0] * 768
    try:
        return await llm_provider.embed(query)
    except Exception as e:
        logger.error("Query embedding failed: %s", e)
        return [0.0] * 768
