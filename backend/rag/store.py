"""
backend/rag/store.py
Durable PostgreSQL/pgvector or SQLite storage, plus an in-memory test helper.

Usage:
    store = get_vector_store()
    await store.upsert(chunks)
    results = await store.search(query_vector, product_id=..., source_type=..., top_k=8)

Implemented in Step 5.
"""

import logging
import os
from typing import Optional, Protocol
from dataclasses import dataclass, field, replace
import math
import re
import asyncio
import json
from dataclasses import asdict

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
    fetched_at: str           # Actual web observation time; empty for undated curated data
    origin: str = "web"       # web | curated | fixture
    kind: str = "specs"       # specs | reviews | policy | price | notes
    claims: list[dict] = field(default_factory=list)
    title: str = ""
    relevance: float = 0.0
    retrieval_mode: str = "vector"


class VectorStore(Protocol):
    """Protocol (interface) for vector stores."""

    async def upsert(self, chunks: list[Chunk]) -> None:
        """Store or update chunks and their embeddings."""
        ...

    async def for_product(self, product_id: str) -> list[Chunk]:
        ...

    async def search_lexical(self, query: str, *, product_id=None, source_type=None, top_k=8) -> list[Chunk]:
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
        dimensions = {len(c.embedding) for c in [*self._chunks, *chunks] if c.embedding}
        if len(dimensions) > 1:
            raise ValueError("Embedding dimensions differ; rebuild the vector store")
        if any(not math.isfinite(v) for c in chunks for v in c.embedding):
            raise ValueError("Embedding values must be finite")
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

        if not query_vector or not any(query_vector) or any(not math.isfinite(v) for v in query_vector):
            raise ValueError("Query embedding must be nonzero and finite")
        if any(c.embedding and len(c.embedding) != len(query_vector) for c in candidates):
            raise ValueError("Query/document embedding dimensions differ")
        # Cosine similarity
        def cosine(a: list[float], b: list[float]) -> float:
            mag_a, mag_b = math.hypot(*a), math.hypot(*b)
            if not math.isfinite(mag_a) or not math.isfinite(mag_b):
                raise ValueError("Embedding magnitude is not finite")
            if mag_a == 0 or mag_b == 0:
                return 0.0
            return sum((x / mag_a) * (y / mag_b) for x, y in zip(a, b))

        scored = [replace(c, relevance=cosine(query_vector, c.embedding)) for c in candidates if c.embedding and any(c.embedding)]
        return sorted(scored, key=lambda c: c.relevance, reverse=True)[:top_k]

    async def for_product(self, product_id: str) -> list[Chunk]:
        return [c for c in self._chunks if c.product_id == product_id]

    async def search_lexical(self, query: str, *, product_id=None, source_type=None, top_k=8) -> list[Chunk]:
        tokens = set(re.findall(r"\w+", query.lower()))
        candidates = [c for c in self._chunks if (not product_id or c.product_id == product_id) and (not source_type or c.source_type == source_type)]
        scored = [replace(c, relevance=len(tokens & set(re.findall(r"\w+", c.content.lower()))) / max(len(tokens), 1), retrieval_mode="lexical") for c in candidates]
        return sorted(scored, key=lambda c: c.relevance, reverse=True)[:top_k]


# Singleton store instance (per-process; reset on cold-start)
class DurableVectorStore:
    """Persist source metadata and vectors; PostgreSQL searches with pgvector."""
    def __init__(self, space):
        self.space = space

    def _read(self, product_id=None, source_type=None):
        from data import runtime
        runtime.ensure()
        sql, params = 'SELECT body FROM bw_chunks WHERE space=?', [self.space]
        if product_id:
            sql += ' AND product_id=?'; params.append(product_id)
        if source_type:
            sql += ' AND source_type=?'; params.append(source_type)
        with runtime.connect() as db:
            rows = db.execute(sql + ' ORDER BY id LIMIT 5000', params).fetchall()
        return [Chunk(**runtime.decode(r[0])) for r in rows]

    async def upsert(self, chunks):
        def save():
            from data import runtime
            runtime.ensure()
            # Validate the whole batch before changing any stored record.
            dimensions = {len(c.embedding) for c in chunks if c.embedding}
            if len(dimensions) > 1 or any(not math.isfinite(v) for c in chunks for v in c.embedding):
                raise ValueError('Embedding dimensions/values are invalid')
            with runtime.connect(write=True) as db:
                if any(c.embedding and len(c.embedding) != 768 for c in chunks):
                    raise ValueError('Durable embeddings must have 768 dimensions')
                for c in chunks:
                    params = (c.id, self.space, c.product_id, c.source_type, json.dumps(asdict(c)), __import__('time').time())
                    db.execute('INSERT INTO bw_chunks(id,space,product_id,source_type,body,saved_at) VALUES (?,?,?,?,?,?) ON CONFLICT(id,space) DO UPDATE SET body=excluded.body,source_type=excluded.source_type,saved_at=excluded.saved_at', params)
                    if db.pg:
                        vector = json.dumps(c.embedding) if c.embedding and any(c.embedding) else None
                        db.execute('UPDATE bw_chunks SET embedding=?::vector WHERE id=? AND space=?', (vector, c.id, self.space))
                # Bounded catalog store. Comparison snapshots keep their own evidence.
                db.execute('DELETE FROM bw_chunks WHERE (id,space) NOT IN (SELECT id,space FROM bw_chunks ORDER BY saved_at DESC,id DESC LIMIT 5000)')
        await asyncio.to_thread(save)

    async def for_product(self, product_id):
        return await asyncio.to_thread(self._read, product_id)

    async def search_lexical(self, query, *, product_id=None, source_type=None, top_k=8):
        store = InMemoryVectorStore()
        store._chunks = await asyncio.to_thread(self._read, product_id, source_type)
        return await store.search_lexical(query, top_k=top_k)

    async def search(self, query_vector, *, product_id=None, source_type=None, top_k=8):
        from data import runtime
        if not runtime.postgres():
            store = InMemoryVectorStore()
            store._chunks = await asyncio.to_thread(self._read, product_id, source_type)
            return await store.search(query_vector, top_k=top_k)
        if len(query_vector) != 768 or not any(query_vector) or any(not math.isfinite(v) for v in query_vector):
            raise ValueError('Query requires a finite nonzero 768-dimensional vector')
        def search():
            runtime.ensure()
            vector = json.dumps(query_vector)
            sql = 'SELECT body,1-(embedding <=> ?::vector) FROM bw_chunks WHERE space=? AND embedding IS NOT NULL'
            params = [vector, self.space]
            if product_id:
                sql += ' AND product_id=?'; params.append(product_id)
            if source_type:
                sql += ' AND source_type=?'; params.append(source_type)
            params += [vector, top_k]
            with runtime.connect() as db:
                rows = db.execute(sql + ' ORDER BY embedding <=> ?::vector LIMIT ?', params).fetchall()
            return [replace(Chunk(**runtime.decode(body)), relevance=float(score)) for body, score in rows]
        return await asyncio.to_thread(search)


_store_instance: Optional[VectorStore] = None
_store_config = None


def get_vector_store() -> VectorStore:
    """
    Return the appropriate vector store based on environment config.
    - If DATABASE_URL is set: use PostgreSQL/pgvector.
    - Otherwise: use durable SQLite (local development).
    """
    global _store_instance, _store_config
    space = 'fixture-lexical-v1' if os.getenv('BUYWISE_MODE', '').lower() == 'fixture' else os.getenv('GEMINI_EMBED_MODEL', 'gemini-embedding-001') + ':768'
    config = (os.getenv('DATABASE_URL'), os.getenv('BUYWISE_DB'), os.getenv('BUYWISE_FIXTURE_DB'), space)
    if _store_instance is not None and _store_config == config:
        return _store_instance
    _store_instance = DurableVectorStore(space)
    _store_config = config
    return _store_instance
