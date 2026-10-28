"""Tests for packages.core.utils.sanitizer."""

from packages.core.utils.sanitizer import normalise_text, safe_title


class TestSafeTitle:
    """Spec §13.5 – filename safety."""

    def test_normal_title(self) -> None:
        assert safe_title("転生したらスライムだった件") == "転生したらスライムだった件"

    def test_removes_unsafe_chars(self) -> None:
        assert safe_title('test:file/name<>"|') == "test_file_name"

    def test_collapses_underscores(self) -> None:
        assert safe_title("a:::b") == "a_b"

    def test_truncation(self) -> None:
        long = "あ" * 100
        result = safe_title(long, max_len=80)
        assert len(result) <= 80

    def test_empty_title(self) -> None:
        assert safe_title("") == "untitled"

    def test_only_unsafe_chars(self) -> None:
        assert safe_title(":::") == "untitled"


class TestNormaliseText:
    def test_crlf(self) -> None:
        assert normalise_text("a\r\nb") == "a\nb"

    def test_keeps_japanese_punctuation_and_fullwidth_chars(self) -> None:
        # NFKC used to turn …… into ......, ？ into ?, 　 into a space, etc.
        text = "「……まだ？」\n　彼女は――ふっと笑った！（１２時）～♡"
        assert normalise_text(text) == text

    def test_composes_split_dakuten(self) -> None:
        # NFC still joins decomposed kana (か + ゛ combining) into が.
        assert normalise_text("が") == "が"

    def test_keeps_blank_lines_for_author_pacing(self) -> None:
        assert normalise_text("a\n\n\n\n\nb") == "a\n\n\n\n\nb"

    def test_strips_trailing_ws(self) -> None:
        assert normalise_text("hello   \nworld  ") == "hello\nworld"
