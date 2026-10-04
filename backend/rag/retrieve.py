"""Product-filtered retrieval. Relevance first; explicit lexical degradation."""
from .store import Chunk, get_vector_store

DEGRADED_NOTICE = 'Semantic embeddings unavailable or incompatible; using lexical retrieval, which does not prove semantic relevance.'


async def retrieve(query, *, product_id=None, source_type=None, top_k=8, llm_provider=None, notices=None):
    store = get_vector_store()
    try:
        if llm_provider is None:
            raise ValueError('No embedding provider')
        vector = await getattr(llm_provider, "embed_query", llm_provider.embed)(query)
        raw = await store.search(vector, product_id=product_id, source_type=source_type, top_k=top_k*2)
        # Empty embeddings on ingested documents require lexical fallback too.
        if not raw and await store.search_lexical(query, product_id=product_id, source_type=source_type, top_k=1):
            raise ValueError('Document embeddings unavailable')
    except Exception:
        if notices is not None and DEGRADED_NOTICE not in notices:
            notices.append(DEGRADED_NOTICE)
        raw = await store.search_lexical(query, product_id=product_id, source_type=source_type, top_k=top_k*2)
    return rerank(raw)[:top_k]


def rerank(chunks: list[Chunk]) -> list[Chunk]:
    # Source trust/recency break relevance ties, never replace cosine relevance.
    return sorted(chunks, key=lambda c: (c.relevance, c.origin == 'web' and c.source_type == 'primary', c.fetched_at), reverse=True)


def chunks_to_context(chunks):
    return [{'content':c.content, 'source_type':c.source_type, 'url':c.url,
             'source_id':c.source_id, 'chunk_id':c.id, 'origin':c.origin} for c in chunks]
