"""
backend/rag/sanitize.py
Content sanitization — prompt injection defense for retrieved web content.

Implements PRD §19 prompt injection defenses:
1. Strip scripts, HTML, hidden text.
2. Detect instruction-like patterns and drop the chunk.
3. Return clean text safe to include in LLM context.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Instruction-like pattern detection ──────────────────────────────────────

# Patterns that suggest prompt injection attempts in retrieved content.
# Add more as encountered. This is a blocklist — not exhaustive, but defensive.
INJECTION_PATTERNS = [
    r"ignore\s+(previous|all|above)\s+instructions?",
    r"disregard\s+(previous|all|above)\s+(instructions?|rules?|context)",
    r"forget\s+(everything|what\s+you\s+know|previous|all)",
    r"new\s+instructions?\s*:?",
    r"system\s*prompt\s*:",
    r"you\s+are\s+now\s+(a|an)",
    r"act\s+as\s+(a|an|if)",
    r"pretend\s+(you\s+are|to\s+be)",
    r"do\s+not\s+follow\s+your\s+(rules|guidelines|instructions)",
    r"override\s+(all|your|the)\s+(instructions?|rules?)",
    r"<\|.*?\|>",           # special tokens
    r"\[INST\]",             # Llama-style injection
    r"###\s*instruction",    # prompt header patterns
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in INJECTION_PATTERNS]


def is_injection_attempt(text: str) -> bool:
    """Return True if the text contains instruction-like patterns."""
    for pattern in _COMPILED_PATTERNS:
        if pattern.search(text):
            return True
    return False


def strip_html(html: str) -> str:
    """
    Remove HTML tags, scripts, styles, and hidden elements.
    Returns plain text.
    """
    try:
        from bs4 import BeautifulSoup  # type: ignore
        soup = BeautifulSoup(html, "html.parser")
        # Remove script and style elements
        for element in soup(["script", "style", "noscript", "head"]):
            element.decompose()
        # Also remove hidden elements
        for element in soup.find_all(style=re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.IGNORECASE)):
            element.decompose()
        for element in soup.select("[hidden], [aria-hidden='true']"):
            element.decompose()
        text = soup.get_text(separator="\n", strip=True)
    except ImportError:
        # Fallback: simple regex tag stripping
        text = re.sub(r"<[^>]+>", " ", html)

    # Collapse whitespace
    text = re.sub(r"[^\S\n]+", " ", text).strip()
    return text


def sanitize_chunk(text: str, source_url: str = "") -> Optional[str]:
    """
    Sanitize a retrieved chunk for safe inclusion in LLM context.

    Returns:
        Cleaned text string, or None if the chunk should be dropped
        (injection attempt detected or content too short to be useful).
    """
    # Strip HTML if present
    if re.search(r"<[a-z][^>]*>", text, re.IGNORECASE):
        text = strip_html(text)

    # Drop empty or trivial content
    if len(text.strip()) < 20:
        return None

    # Check for injection attempts
    if is_injection_attempt(text):
        logger.warning(
            "Prompt injection pattern detected in chunk from %s — dropping chunk",
            source_url,
        )
        return None

    # Normalize whitespace
    text = re.sub(r"[^\S\n]+", " ", text).strip()

    return text
