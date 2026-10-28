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

    - Normalise Unicode to NFC (not NFKC: NFKC rewrites Japanese
      typography — …… → ..., ？ → ?, 　 → space, ～ → ~, （１） → (1))
    - Unify line endings to ``\\n``
    - Strip trailing whitespace per line

    Blank-line runs are kept on purpose: authors use them for pacing,
    and :func:`packages.core.utils.pixiv_layout.parse_layout` turns them
    into (capped) gaps.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    return text.strip()
