"""EPUB output keeps pixiv layout: page breaks, gaps, chapters, ruby."""

from __future__ import annotations

import asyncio
import re
import zipfile

from packages.core.domain.models import BilingualBlock as B
from packages.core.domain.models import PixivNovel
from packages.core.services.epub_service import EpubService


def _build(tmp_path, blocks):
    novel = PixivNovel(novel_id=1, title="題名", author_name="作者", text="")
    path = asyncio.run(EpubService(temp_dir=str(tmp_path)).build(novel, blocks))
    z = zipfile.ZipFile(path)
    pages = sorted(n for n in z.namelist() if re.search(r"page_\d+\.xhtml$", n))
    return z, [z.read(p).decode("utf-8") for p in pages]


def test_newpage_starts_a_new_file(tmp_path) -> None:
    _, pages = _build(tmp_path, [B("甲"), B("", kind="page"), B("乙")])
    assert len(pages) == 2
    assert "甲" in pages[0] and "乙" not in pages[0]
    assert "乙" in pages[1]


def test_title_only_on_first_page(tmp_path) -> None:
    _, pages = _build(tmp_path, [B("甲"), B("", kind="page"), B("乙")])
    assert "<h1>題名</h1>" in pages[0]
    assert "<h1>" not in pages[1]


def test_chapter_starts_new_file_and_appears_in_toc(tmp_path) -> None:
    z, pages = _build(
        tmp_path,
        [
            B("序"),
            B("", kind="page"),
            B("第一章", translated="第一章（譯）", kind="chapter"),
            B("甲"),
        ],
    )
    assert len(pages) == 2  # page + chapter right after it → one break, not two
    assert "第一章（譯）" in pages[1]
    nav = next(z.read(n).decode() for n in z.namelist() if n.endswith("nav.xhtml"))
    assert "第一章" in nav


def test_gap_is_rendered_with_line_count(tmp_path) -> None:
    _, pages = _build(tmp_path, [B("甲"), B("", kind="gap", gap_lines=3), B("乙")])
    assert 'class="gap gap-3"' in pages[0]


def test_ruby_is_rendered_in_source(tmp_path) -> None:
    _, pages = _build(tmp_path, [B("[[rb:漢字 > かんじ]]", translated="漢字")])
    assert "<ruby>漢字<rt>かんじ</rt></ruby>" in pages[0]
    assert "[[rb:" not in pages[0]
