"""Parse user-supplied novel identifiers into structured results.

Supported formats (spec §10.1):
  - Pure ID:        ``12345678``
  - Novel URL:      ``https://www.pixiv.net/novel/show.php?id=12345678``
  - Series URL:     ``https://www.pixiv.net/novel/series/987654``  (M4)
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from packages.core.domain.value_objects import ParsedNovelInput
from packages.core.exceptions import InvalidInputError

# Novel URL pattern – query-param style.
_NOVEL_URL_RE = re.compile(
    r"^https?://(?:www\.)?pixiv\.net/novel/show\.php",
)

# Series URL pattern.
_SERIES_URL_RE = re.compile(
    r"^https?://(?:www\.)?pixiv\.net/novel/series/(\d+)",
)

# Pure numeric string.
_PURE_ID_RE = re.compile(r"^\d+$")


def parse_novel_input(raw: str) -> ParsedNovelInput:
    """Parse *raw* into a :class:`ParsedNovelInput`.

    Raises
    ------
    InvalidInputError
        When *raw* is not a recognisable pixiv novel identifier.
    """
    raw = raw.strip()
    if not raw:
        raise InvalidInputError("輸入不可為空")

    # ── Pure numeric ID ────────────────────────────────
    if _PURE_ID_RE.match(raw):
        return ParsedNovelInput(input_type="novel", novel_id=int(raw))

    # ── Series URL ─────────────────────────────────────
    m = _SERIES_URL_RE.match(raw)
    if m:
        return ParsedNovelInput(input_type="series", series_id=int(m.group(1)))

    # ── Novel URL ──────────────────────────────────────
    if _NOVEL_URL_RE.match(raw):
        parsed = urlparse(raw)
        qs = parse_qs(parsed.query)
        ids = qs.get("id")
        if ids and ids[0].isdigit():
            return ParsedNovelInput(input_type="novel", novel_id=int(ids[0]))
        raise InvalidInputError(f"URL 中找不到有效的小說 ID: {raw}")

    raise InvalidInputError(f"無法解析的 pixiv 輸入: {raw}")
