"""Domain models – internal data structures used across the core layer.

These are plain dataclasses (not Pydantic) because they do not cross
API boundaries.  Pydantic models for API I/O live in value_objects.py.
Spec references: §10.1, §10.2.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PixivNovel:
    """Resolved pixiv novel with metadata and full text."""

    novel_id: int
    title: str
    author_name: str
    text: str
    caption: str | None = None
    tags: list[str] = field(default_factory=list)
    series_id: int | None = None
    series_title: str | None = None


@dataclass(frozen=True)
class BilingualBlock:
    """One item of the novel layout, with an optional translation.

    ``kind`` is one of:
      - ``"text"``    – a paragraph/line (may contain pixiv ruby markup)
      - ``"chapter"`` – a ``[chapter:]`` heading; ``source`` is the title
      - ``"gap"``     – author's blank lines; ``gap_lines`` says how many
      - ``"page"``    – a ``[newpage]`` page break
    Only ``text`` and ``chapter`` are translated.
    """

    source: str
    translated: str | None = None
    kind: str = "text"
    gap_lines: int = 0


@dataclass(frozen=True)
class SendNovelResult:
    """Outcome of a single pixiv-to-kindle task."""

    success: bool
    message: str
    title: str | None = None
    novel_id: int | None = None
    file_path: str | None = None
