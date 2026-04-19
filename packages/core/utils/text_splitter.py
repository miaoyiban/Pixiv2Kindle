"""Split novel text into translatable / displayable blocks.

Strategy (spec §12.3):
  1. Split on double newlines (paragraph boundaries).
  2. If a paragraph exceeds *max_block_chars*, split further on
     sentence-ending punctuation (。！？!? and fullwidth variants).
  3. Guarantee every block ≤ *max_block_chars* by hard-cutting as
     a last resort (should be extremely rare in natural text).
"""

from __future__ import annotations

import re

# Sentence-ending punctuation used for secondary splitting.
_SENTENCE_END_RE = re.compile(r"(?<=[。！？!?])")

# Default ceiling per block – generous enough for LLM context windows
# while short enough for readable bilingual chunks.
DEFAULT_MAX_BLOCK_CHARS = 2000


def split_text_into_blocks(
    text: str,
    *,
    max_block_chars: int = DEFAULT_MAX_BLOCK_CHARS,
) -> list[str]:
    """Return a list of text blocks ready for display or translation.

    Parameters
    ----------
    text:
        Raw novel text (may contain ``\\n``, ``\\r\\n``, etc.).
    max_block_chars:
        Soft maximum characters per block.

    Returns
    -------
    list[str]
        Non-empty, stripped blocks.
    """
    # Normalise line endings.
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Step 1 – paragraph split on double newline.
    raw_paragraphs = re.split(r"\n{2,}", text)

    blocks: list[str] = []
    for para in raw_paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(para) <= max_block_chars:
            blocks.append(para)
            continue

        # Step 2 – sentence-level split for over-long paragraphs.
        sentences = _SENTENCE_END_RE.split(para)
        buffer = ""
        for sentence in sentences:
            if not sentence:
                continue
            if buffer and len(buffer) + len(sentence) > max_block_chars:
                blocks.append(buffer.strip())
                buffer = ""
            buffer += sentence

        if buffer.strip():
            # Step 3 – hard cut if still over limit.
            _hard_split(buffer.strip(), max_block_chars, blocks)

    return blocks


def _hard_split(text: str, limit: int, out: list[str]) -> None:
    """Last-resort character-level split (should almost never fire)."""
    while text:
        out.append(text[:limit].strip())
        text = text[limit:]
