"""
backend/rag/ingest.py
RAG ingestion pipeline: fetch → clean → chunk → embed → store.

This module handles ingesting content from:
1. The curated seed dataset (backend/data/seed/laptops.json) — loaded on startup.
2. On-demand fetching of URLs from the seed records.

Chunking strategy (PRD §11):
- Spec tables: kept intact as a single chunk.
- Policy text: split by section (paragraph-aware).
- General text: fixed-size chunks of 500–800 tokens with ~10% overlap.
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from uuid import uuid4

import httpx

from .sanitize import sanitize_chunk
from .store import Chunk, get_vector_store

logger = logging.getLogger(__name__)

# ─── Chunking config ──────────────────────────────────────────────────────────

CHUNK_TARGET_CHARS = 2000   # ~500 tokens at ~4 chars/token
CHUNK_MAX_CHARS = 3200      # ~800 tokens
CHUNK_OVERLAP_CHARS = 200   # ~10% overlap

# ─── Domain allowlist (PRD §12, §19) ──────────────────────────────────────────
# Only fetch from these domains to prevent SSRF and unlicensed scraping.
# Add new trusted domains here as needed.

ALLOWED_DOMAINS = {
    "lenovo.com", "psref.lenovo.com",
    "frame.work", "guides.frame.work",
    "system76.com",
    "dell.com",
    "hpdevone.com",
    "rog.asus.com", "asus.com",
    "apple.com",
    "acer.com",
    "msi.com",
    "gigabyte.com",
    "puri.sm",
    "starlabs.systems",
    "tuxedocomputers.com",
    "notebookcheck.net",
    "rtings.com",
    "anandtech.com",
    "theverge.com",
    "arstechnica.com",
}


def _domain_allowed(url: str) -> bool:
    """Return True if the URL's domain is in the allowlist."""
    from urllib.parse import urlparse
    try:
        host = urlparse(url).netloc.lstrip("www.")
        # Check if host matches or is a subdomain of an allowed domain
        return any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS)
    except Exception:
        return False


# ─── Chunking ────────────────────────────────────────────────────────────────

def chunk_text(text: str, product_id: str, source_id: str,
               source_type: str, url: str, fetched_at: str) -> list[dict]:
    """
    Split text into overlapping chunks with metadata.
    Returns list of dicts (not yet embedded).
    """
    text = text.strip()
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_MAX_CHARS, len(text))

        # Try to break at a paragraph boundary
        if end < len(text):
            # Look for last paragraph break before end
            para_break = text.rfind("\n\n", start, end)
            if para_break > start + CHUNK_TARGET_CHARS:
                end = para_break
            else:
                # Fall back to sentence boundary
                sentence_break = text.rfind(". ", start + CHUNK_TARGET_CHARS, end)
                if sentence_break > start:
                    end = sentence_break + 1

        chunk_text_str = text[start:end].strip()
        if chunk_text_str:
            chunks.append({
                "id": str(uuid4()),
                "product_id": product_id,
                "source_id": source_id,
                "source_type": source_type,
                "url": url,
                "content": chunk_text_str,
                "fetched_at": fetched_at,
            })

        # Move forward with overlap
        start = end - CHUNK_OVERLAP_CHARS if end < len(text) else len(text)

    return chunks


def spec_dict_to_text(specs: dict, product_name: str) -> str:
    """
    Convert a spec dictionary into a structured text block for embedding.
    Spec tables are kept as a single chunk (PRD §11).
    """
    lines = [f"Technical specifications for {product_name}:"]
    for key, value in specs.items():
        if value is None:
            continue
        # Convert snake_case keys to readable labels
        label = key.replace("_", " ").title()
        lines.append(f"  {label}: {value}")
    return "\n".join(lines)


# ─── Fetching ─────────────────────────────────────────────────────────────────

async def fetch_url(url: str, timeout_s: int = 15) -> Optional[str]:
    """
    Fetch URL content and return cleaned text.
    Only fetches from allowed domains. Returns None on failure.
    """
    if not _domain_allowed(url):
        logger.warning("Domain not in allowlist, skipping: %s", url)
        return None

    try:
        async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "BuyWiseAI/0.1 (research bot; contact@buywise.ai)"},
            )
            if response.status_code != 200:
                logger.warning("Non-200 from %s: %d", url, response.status_code)
                return None

            content_type = response.headers.get("content-type", "")
            if "text/html" in content_type or "text/plain" in content_type:
                return response.text
            else:
                logger.warning("Unsupported content-type %s from %s", content_type, url)
                return None
    except Exception as e:
        logger.error("Failed to fetch %s: %s", url, e)
        return None


# ─── Seed ingestion ───────────────────────────────────────────────────────────

SEED_FILE = Path(__file__).parent.parent / "data" / "seed" / "laptops.json"


async def ingest_seed_data(llm_provider=None) -> int:
    """
    Load the curated seed dataset and ingest it into the vector store.
    Embeds spec text for each product.

    Returns the number of chunks ingested.
    """
    if not SEED_FILE.exists():
        logger.error("Seed file not found: %s", SEED_FILE)
        return 0

    with open(SEED_FILE, encoding="utf-8") as f:
        products = json.load(f)

    store = get_vector_store()
    total_chunks = 0
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")

    for product in products:
        product_id = product["id"]
        product_name = product["name"]

        # Convert spec dict to text and create a primary-source chunk
        if "specs" in product and product["specs"]:
            spec_text = spec_dict_to_text(product["specs"], product_name)
            spec_text = sanitize_chunk(spec_text, source_url="seed")
            if spec_text:
                chunk_data = {
                    "id": f"{product_id}__specs",
                    "product_id": product_id,
                    "source_id": f"seed_{product_id}",
                    "source_type": "primary",
                    "url": product.get("canonical_url", ""),
                    "content": spec_text,
                    "fetched_at": fetched_at,
                }

                # Embed the chunk
                embedding = await _embed_chunk(spec_text, llm_provider)
                chunk = Chunk(embedding=embedding, **chunk_data)
                await store.upsert([chunk])
                total_chunks += 1

        # Add notes as a secondary chunk
        if product.get("notes"):
            notes_text = f"Notes about {product_name}: {product['notes']}"
            notes_text = sanitize_chunk(notes_text, source_url="seed")
            if notes_text:
                chunk_data = {
                    "id": f"{product_id}__notes",
                    "product_id": product_id,
                    "source_id": f"seed_{product_id}_notes",
                    "source_type": "secondary",
                    "url": product.get("canonical_url", ""),
                    "content": notes_text,
                    "fetched_at": fetched_at,
                }
                embedding = await _embed_chunk(notes_text, llm_provider)
                chunk = Chunk(embedding=embedding, **chunk_data)
                await store.upsert([chunk])
                total_chunks += 1

    logger.info("Seed ingestion complete: %d chunks for %d products", total_chunks, len(products))
    return total_chunks


async def ingest_url(url: str, product_id: str, source_type: str,
                     title: str, llm_provider=None) -> int:
    """
    Fetch and ingest a single URL for a product.
    Returns the number of chunks created.
    """
    raw = await fetch_url(url)
    if not raw:
        return 0

    clean = sanitize_chunk(raw, source_url=url)
    if not clean:
        logger.warning("Content sanitization dropped everything from %s", url)
        return 0

    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    source_id = str(uuid4())

    raw_chunks = chunk_text(
        text=clean,
        product_id=product_id,
        source_id=source_id,
        source_type=source_type,
        url=url,
        fetched_at=fetched_at,
    )

    store = get_vector_store()
    embedded_chunks = []
    for c in raw_chunks:
        emb = await _embed_chunk(c["content"], llm_provider)
        embedded_chunks.append(Chunk(embedding=emb, **c))

    await store.upsert(embedded_chunks)
    logger.info("Ingested %d chunks from %s", len(embedded_chunks), url)
    return len(embedded_chunks)


async def _embed_chunk(text: str, llm_provider=None) -> list[float]:
    """Get embedding for a text chunk. Falls back to zero vector if no LLM."""
    if llm_provider is None:
        return [0.0] * 768  # dummy embedding for mock mode
    try:
        return await llm_provider.embed(text)
    except Exception as e:
        logger.error("Embedding failed: %s", e)
        return [0.0] * 768
