"""Turn pixiv novel text into a layout: text, blank-line gaps, page breaks,
chapters — and handle pixiv ruby markup.

pixiv markup handled here:
  - ``[newpage]``                 → page break
  - ``[chapter:タイトル]``          → chapter heading (also a page break)
  - ``[[rb:漢字 > かんじ]]``        → ruby (furigana)
Runs of blank lines are kept as ``gap`` items so the author's pacing
survives, capped at :data:`MAX_GAP_LINES`.
"""

from __future__ import annotations

import re

from markupsafe import Markup, escape

from packages.core.domain.models import BilingualBlock
from packages.core.utils.text_splitter import (
    DEFAULT_MAX_BLOCK_CHARS,
    split_text_into_blocks,
)

# More blank lines than this would leave a whole Kindle screen empty.
MAX_GAP_LINES = 5

_NEWPAGE = "[newpage]"
_CHAPTER_RE = re.compile(r"\[chapter:\s*(.*?)\s*\]")
_RUBY_RE = re.compile(r"\[\[rb:\s*(.+?)\s*>\s*(.+?)\s*\]\]")

# Items after which a gap would just be stray whitespace.
_BREAKS = ("page", "chapter")


def strip_ruby(text: str) -> str:
    """Drop ruby readings, keeping the base text (for translation)."""
    return _RUBY_RE.sub(r"\1", text)


def render_ruby(text: str | None) -> Markup:
    """HTML-escape *text*, render ruby as ``<ruby>``, and ``\\n`` as ``<br/>``."""
    if not text:
        return Markup("")
    out: list[str] = []
    pos = 0
    for m in _RUBY_RE.finditer(text):
        out.append(escape(text[pos : m.start()]))
        out.append(Markup("<ruby>{}<rt>{}</rt></ruby>").format(m[1], m[2]))
        pos = m.end()
    out.append(escape(text[pos:]))
    html = Markup("").join(out)
    return Markup("<br/>").join(html.split("\n"))


def parse_layout(
    text: str,
    *,
    per_line: bool = False,
    max_block_chars: int = DEFAULT_MAX_BLOCK_CHARS,
) -> list[BilingualBlock]:
    """Split pixiv novel text into layout items (see :class:`BilingualBlock`).

    In ``per_line`` mode every line is its own block and each blank line
    counts toward a gap. In paragraph mode a single blank line is the
    normal paragraph separator, and only the extra ones become a gap.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    items: list[BilingualBlock] = []
    para: list[str] = []

    def flush() -> None:
        if para:
            for block in split_text_into_blocks(
                "\n".join(para), max_block_chars=max_block_chars, per_line=per_line
            ):
                items.append(BilingualBlock(source=block))
            para.clear()

    def add_gap(lines: int) -> None:
        if lines > 0 and items and items[-1].kind not in (*_BREAKS, "gap"):
            items.append(
                BilingualBlock(source="", kind="gap", gap_lines=min(lines, MAX_GAP_LINES))
            )

    def add_break(item: BilingualBlock) -> None:
        flush()
        while items and items[-1].kind == "gap":
            items.pop()
        if item.kind == "page" and (not items or items[-1].kind in _BREAKS):
            return  # nothing to break away from
        items.append(item)

    # Alternates: line, newline-run, line, newline-run, ...
    for i, piece in enumerate(re.split(r"(\n+)", text)):
        if i % 2 == 1:
            newlines = len(piece)
            if per_line:
                flush()
                add_gap(newlines - 1)
            elif newlines >= 2:
                flush()
                add_gap(newlines - 2)
            continue

        line = piece.strip()
        if not line:
            continue
        if line == _NEWPAGE:
            add_break(BilingualBlock(source="", kind="page"))
            continue
        chapter = _CHAPTER_RE.fullmatch(line)
        if chapter:
            add_break(BilingualBlock(source=chapter[1], kind="chapter"))
            continue
        para.append(line)

    flush()
    while items and items[-1].kind in ("gap", "page"):
        items.pop()
    return items
