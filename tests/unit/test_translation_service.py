"""Tests for packages.core.services.translation_service."""

from __future__ import annotations

import time
import pytest

from packages.core.domain.models import BilingualBlock
from packages.core.exceptions import TranslationError
from packages.core.services.translation_service import TranslationService


# ── Test doubles ───────────────────────────────────────


class MockProvider:
    """Returns reversed text as 'translation'."""

    async def translate_blocks(
        self, blocks: list[str], target_lang: str
    ) -> list[str]:
        return [b[::-1] for b in blocks]


class FailingProvider:
    """Always raises TranslationError."""

    async def translate_blocks(
        self, blocks: list[str], target_lang: str
    ) -> list[str]:
        raise TranslationError("mock failure")


class MismatchProvider:
    """Returns wrong number of blocks."""

    async def translate_blocks(
        self, blocks: list[str], target_lang: str
    ) -> list[str]:
        return ["only one"]


# ── Tests ──────────────────────────────────────────────


class TestTranslationService:
    @pytest.mark.asyncio
    async def test_successful_translation(self) -> None:
        svc = TranslationService(provider=MockProvider(), fail_on_error=False)
        blocks = await svc.translate(["hello", "world"], "zh-TW")
        assert len(blocks) == 2
        assert blocks[0] == BilingualBlock(source="hello", translated="olleh")
        assert blocks[1] == BilingualBlock(source="world", translated="dlrow")

    @pytest.mark.asyncio
    async def test_empty_input(self) -> None:
        svc = TranslationService(provider=MockProvider(), fail_on_error=False)
        blocks = await svc.translate([], "zh-TW")
        assert blocks == []

    @pytest.mark.asyncio
    async def test_fail_on_error_true_raises(self) -> None:
        svc = TranslationService(provider=FailingProvider(), fail_on_error=True)
        with pytest.raises(TranslationError):
            await svc.translate(["test"], "zh-TW")

    @pytest.mark.asyncio
    async def test_fail_on_error_false_degrades(self) -> None:
        svc = TranslationService(provider=FailingProvider(), fail_on_error=False)
        blocks = await svc.translate(["test"], "zh-TW")
        assert len(blocks) == 1
        assert blocks[0].source == "test"
        assert blocks[0].translated is None

    @pytest.mark.asyncio
    async def test_time_budget_exceeded_proceeds_anyway(self) -> None:
        """Translation no longer rejects on budget exceeded — it proceeds
        and lets the Kindle delivery happen even if Discord notification
        will be missed.
        """
        svc = TranslationService(provider=MockProvider(), fail_on_error=False)
        # Deadline already passed.
        past_deadline = int(time.time() * 1000) - 10_000
        # Should NOT raise — translation proceeds regardless.
        blocks = await svc.translate(["test"], "zh-TW", deadline_epoch_ms=past_deadline)
        assert len(blocks) == 1
        assert blocks[0].translated == "tset"

    @pytest.mark.asyncio
    async def test_time_budget_sufficient(self) -> None:
        svc = TranslationService(provider=MockProvider(), fail_on_error=False)
        # Deadline far in the future.
        future = int(time.time() * 1000) + 600_000  # +10 min
        blocks = await svc.translate(["test"], "zh-TW", deadline_epoch_ms=future)
        assert len(blocks) == 1
        assert blocks[0].translated == "tset"

    @pytest.mark.asyncio
    async def test_no_deadline_skips_budget_check(self) -> None:
        svc = TranslationService(provider=MockProvider(), fail_on_error=False)
        blocks = await svc.translate(["test"], "zh-TW", deadline_epoch_ms=0)
        assert len(blocks) == 1


# ── translate_layout ───────────────────────────────────


class RecordingProvider:
    def __init__(self) -> None:
        self.seen: list[str] = []

    async def translate_blocks(self, blocks: list[str], target_lang: str) -> list[str]:
        self.seen = list(blocks)
        return [f"<{b}>" for b in blocks]


@pytest.mark.asyncio
async def test_translate_layout_only_sends_text_and_chapters_without_ruby() -> None:
    provider = RecordingProvider()
    svc = TranslationService(provider=provider)
    layout = [
        BilingualBlock("第一章", kind="chapter"),
        BilingualBlock("[[rb:漢字 > かんじ]]だ"),
        BilingualBlock("", kind="gap", gap_lines=2),
        BilingualBlock("", kind="page"),
        BilingualBlock("乙"),
    ]

    out = await svc.translate_layout(layout, "zh-TW")

    assert provider.seen == ["第一章", "漢字だ", "乙"]
    assert out == [
        BilingualBlock("第一章", translated="<第一章>", kind="chapter"),
        BilingualBlock("[[rb:漢字 > かんじ]]だ", translated="<漢字だ>"),
        BilingualBlock("", kind="gap", gap_lines=2),
        BilingualBlock("", kind="page"),
        BilingualBlock("乙", translated="<乙>"),
    ]


@pytest.mark.asyncio
async def test_translate_layout_degrades_keeping_structure() -> None:
    svc = TranslationService(provider=FailingProvider(), fail_on_error=False)
    layout = [BilingualBlock("甲"), BilingualBlock("", kind="page"), BilingualBlock("乙")]
    out = await svc.translate_layout(layout, "zh-TW")
    assert out == layout


# ── punctuation / symbol-only lines are never sent ─────


@pytest.mark.asyncio
@pytest.mark.parametrize("line", ["……", "⚪︎⚫︎⚪︎⚫︎", "◇◇◇", "♡♡", "！？", "――", "* * *", "「……」"])
async def test_symbol_only_lines_are_not_sent(line: str) -> None:
    provider = RecordingProvider()
    svc = TranslationService(provider=provider)
    out = await svc.translate(["甲", line, "乙"], "zh-TW")
    assert provider.seen == ["甲", "乙"]
    assert out[1] == BilingualBlock(source=line, translated=None)
    assert out[0].translated == "<甲>" and out[2].translated == "<乙>"


@pytest.mark.asyncio
async def test_all_symbol_lines_skip_provider_entirely() -> None:
    provider = FailingProvider()  # would raise if called
    svc = TranslationService(provider=provider, fail_on_error=True)
    out = await svc.translate(["……", "♡"], "zh-TW")
    assert [b.translated for b in out] == [None, None]


@pytest.mark.asyncio
async def test_onomatopoeia_is_still_translated() -> None:
    provider = RecordingProvider()
    await TranslationService(provider=provider).translate(["ああぁっ♡"], "zh-TW")
    assert provider.seen == ["ああぁっ♡"]


@pytest.mark.asyncio
async def test_empty_translation_means_no_translation() -> None:
    class EmptyProvider:
        async def translate_blocks(self, blocks, target_lang):
            return [""]

    out = await TranslationService(provider=EmptyProvider()).translate(["甲"], "zh-TW")
    assert out[0].translated is None
