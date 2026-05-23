"""Tests for packages.core.utils.text_splitter."""

from packages.core.utils.text_splitter import split_text_into_blocks


class TestSplitTextIntoBlocks:
    """Spec §12.3 – text splitting strategy."""

    def test_simple_paragraphs(self) -> None:
        text = "段落一。\n\n段落二。\n\n段落三。"
        result = split_text_into_blocks(text)
        assert result == ["段落一。", "段落二。", "段落三。"]

    def test_empty_text(self) -> None:
        assert split_text_into_blocks("") == []

    def test_single_paragraph(self) -> None:
        assert split_text_into_blocks("只有一段") == ["只有一段"]

    def test_multiple_blank_lines(self) -> None:
        text = "段落一。\n\n\n\n\n段落二。"
        result = split_text_into_blocks(text)
        assert result == ["段落一。", "段落二。"]

    def test_crlf_normalisation(self) -> None:
        text = "段落一。\r\n\r\n段落二。"
        result = split_text_into_blocks(text)
        assert result == ["段落一。", "段落二。"]

    def test_long_paragraph_split_on_sentence(self) -> None:
        # Create a paragraph that exceeds the limit.
        sentence = "這是一句很長的話。"
        para = sentence * 30  # ~270 chars
        result = split_text_into_blocks(para, max_block_chars=100)
        assert len(result) > 1
        for block in result:
            assert len(block) <= 100 or "。" not in block

    def test_strips_whitespace(self) -> None:
        text = "  前面有空白  \n\n  後面也有  "
        result = split_text_into_blocks(text)
        assert result == ["前面有空白", "後面也有"]

    def test_per_line_splits_single_newlines(self) -> None:
        text = "第一行\n第二行\n第三行"
        # Default: kept as one block (no \n\n)
        assert split_text_into_blocks(text) == ["第一行\n第二行\n第三行"]
        # per_line: each line becomes its own block
        assert split_text_into_blocks(text, per_line=True) == [
            "第一行", "第二行", "第三行",
        ]

    def test_per_line_collapses_consecutive_newlines(self) -> None:
        # Mixed \n and \n\n should all be treated as separators in per_line mode.
        text = "甲\n\n乙\n丙"
        assert split_text_into_blocks(text, per_line=True) == ["甲", "乙", "丙"]
