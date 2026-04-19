"""Tests for packages.core.providers.pixiv.resolver."""

import pytest

from packages.core.domain.value_objects import ParsedNovelInput
from packages.core.exceptions import InvalidInputError
from packages.core.providers.pixiv.resolver import parse_novel_input


class TestParseNovelInput:
    """Spec §10.1 – supported input formats."""

    # ── Pure numeric ID ────────────────────────────────

    def test_pure_id(self) -> None:
        result = parse_novel_input("12345678")
        assert result == ParsedNovelInput(input_type="novel", novel_id=12345678)

    def test_pure_id_with_whitespace(self) -> None:
        result = parse_novel_input("  12345678  ")
        assert result == ParsedNovelInput(input_type="novel", novel_id=12345678)

    # ── Novel URL ──────────────────────────────────────

    def test_novel_url(self) -> None:
        url = "https://www.pixiv.net/novel/show.php?id=12345678"
        result = parse_novel_input(url)
        assert result == ParsedNovelInput(input_type="novel", novel_id=12345678)

    def test_novel_url_without_www(self) -> None:
        url = "https://pixiv.net/novel/show.php?id=99999"
        result = parse_novel_input(url)
        assert result == ParsedNovelInput(input_type="novel", novel_id=99999)

    def test_novel_url_http(self) -> None:
        url = "http://www.pixiv.net/novel/show.php?id=11111"
        result = parse_novel_input(url)
        assert result == ParsedNovelInput(input_type="novel", novel_id=11111)

    # ── Series URL ─────────────────────────────────────

    def test_series_url(self) -> None:
        url = "https://www.pixiv.net/novel/series/987654"
        result = parse_novel_input(url)
        assert result == ParsedNovelInput(input_type="series", series_id=987654)

    # ── Invalid inputs ─────────────────────────────────

    def test_empty_string(self) -> None:
        with pytest.raises(InvalidInputError):
            parse_novel_input("")

    def test_whitespace_only(self) -> None:
        with pytest.raises(InvalidInputError):
            parse_novel_input("   ")

    def test_random_text(self) -> None:
        with pytest.raises(InvalidInputError):
            parse_novel_input("hello world")

    def test_url_without_id(self) -> None:
        with pytest.raises(InvalidInputError):
            parse_novel_input("https://www.pixiv.net/novel/show.php")

    def test_non_pixiv_url(self) -> None:
        with pytest.raises(InvalidInputError):
            parse_novel_input("https://example.com/12345")
