"""Tests for pixiv layout parsing: blank lines, [newpage], [chapter:], ruby."""

from __future__ import annotations

from packages.core.domain.models import BilingualBlock as B
from packages.core.utils.pixiv_layout import (
    MAX_GAP_LINES,
    parse_layout,
    render_ruby,
    strip_ruby,
)


def T(s: str) -> B:
    return B(source=s)


def GAP(n: int) -> B:
    return B(source="", kind="gap", gap_lines=n)


PAGE = B(source="", kind="page")


def CH(title: str) -> B:
    return B(source=title, kind="chapter")


# ── per_line mode ─────────────────────────────────────


def test_per_line_single_newlines_have_no_gap() -> None:
    assert parse_layout("甲\n乙\n丙", per_line=True) == [T("甲"), T("乙"), T("丙")]


def test_per_line_keeps_blank_line_count() -> None:
    # 1 blank line, then 3 blank lines
    text = "甲\n\n乙\n\n\n\n丙"
    assert parse_layout(text, per_line=True) == [T("甲"), GAP(1), T("乙"), GAP(3), T("丙")]


def test_gap_is_capped() -> None:
    text = "甲" + "\n" * 40 + "乙"
    assert parse_layout(text, per_line=True) == [T("甲"), GAP(MAX_GAP_LINES), T("乙")]


# ── paragraph mode ────────────────────────────────────


def test_paragraph_mode_double_newline_is_plain_separator() -> None:
    assert parse_layout("甲\n乙\n\n丙") == [T("甲\n乙"), T("丙")]


def test_paragraph_mode_extra_blank_lines_become_gap() -> None:
    assert parse_layout("甲\n\n\n\n丙") == [T("甲"), GAP(2), T("丙")]


# ── [newpage] ─────────────────────────────────────────


def test_newpage_becomes_page_break_and_is_not_text() -> None:
    text = "甲\n\n[newpage]\n\n乙"
    assert parse_layout(text, per_line=True) == [T("甲"), PAGE, T("乙")]


def test_gaps_around_page_break_are_dropped() -> None:
    text = "甲\n\n\n\n[newpage]\n\n\n\n乙"
    assert parse_layout(text, per_line=True) == [T("甲"), PAGE, T("乙")]


def test_leading_and_repeated_newpage_are_ignored() -> None:
    text = "[newpage]\n甲\n[newpage]\n[newpage]\n乙\n[newpage]"
    assert parse_layout(text, per_line=True) == [T("甲"), PAGE, T("乙")]


# ── [chapter:] ────────────────────────────────────────


def test_chapter_marker() -> None:
    text = "[chapter:第一章 はじまり]\n甲\n[newpage]\n[chapter:第二章]\n乙"
    assert parse_layout(text, per_line=True) == [
        CH("第一章 はじまり"), T("甲"), PAGE, CH("第二章"), T("乙"),
    ]


def test_gap_right_after_chapter_is_dropped() -> None:
    text = "[chapter:一]\n\n\n甲"
    assert parse_layout(text, per_line=True) == [CH("一"), T("甲")]


# ── ruby ──────────────────────────────────────────────


def test_strip_ruby_keeps_base_text() -> None:
    assert strip_ruby("[[rb:漢字 > かんじ]]を読む") == "漢字を読む"


def test_render_ruby_escapes_and_marks_up() -> None:
    html = str(render_ruby("<[[rb:漢字 > かんじ]]>"))
    assert html == "&lt;<ruby>漢字<rt>かんじ</rt></ruby>&gt;"


def test_render_ruby_turns_newlines_into_br() -> None:
    assert str(render_ruby("甲\n乙")) == "甲<br/>乙"


def test_ruby_markup_is_kept_in_source() -> None:
    assert parse_layout("[[rb:漢字 > かんじ]]", per_line=True) == [T("[[rb:漢字 > かんじ]]")]


# ── long lines still get split ────────────────────────


def test_long_line_is_split_on_sentences() -> None:
    line = "這是一句很長的話。" * 30
    items = parse_layout(line, per_line=True, max_block_chars=100)
    assert len(items) > 1
    assert all(i.kind == "text" for i in items)
