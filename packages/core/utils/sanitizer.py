"""Filename and content sanitisation helpers.

Used when building EPUB filenames and cleaning raw novel text.
"""

from __future__ import annotations

import re
import unicodedata


# Characters that are unsafe in filenames on common OSes.
_UNSAFE_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Collapse multiple whitespace / underscores into one.
_MULTI_UNDERSCORE_RE = re.compile(r"_+")

# Maximum filename length (without extension) – conservative for all OSes.
MAX_SAFE_TITLE_LEN = 80


def safe_title(title: str, *, max_len: int = MAX_SAFE_TITLE_LEN) -> str:
    """Convert a novel title into a filesystem-safe string.

    - NFKC-normalise
    - Replace unsafe chars with underscore
    - Collapse runs of underscores
    - Truncate
    - Strip leading/trailing underscores
    """
    title = unicodedata.normalize("NFKC", title)
    title = _UNSAFE_FILENAME_RE.sub("_", title)
    title = _MULTI_UNDERSCORE_RE.sub("_", title)
    title = title.strip("_ ")
    if len(title) > max_len:
        title = title[:max_len].rstrip("_")
    return title or "untitled"


def normalise_text(text: str) -> str:
    """Light normalisation of raw novel text.

    - Normalise Unicode to NFKC
    - Unify line endings to ``\\n``
    - Strip trailing whitespace per line
    - Collapse 3+ consecutive blank lines into 2
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)

    # Collapse excessive blank lines.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
