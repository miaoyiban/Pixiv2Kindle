"""Tests for packages.core.services.translation_service."""

from __future__ import annotations

import time
import pytest

from packages.core.domain.models import BilingualBlock
from packages.core.exceptions import TimeBudgetExceededError, TranslationError
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
    async def test_time_budget_exceeded(self) -> None:
        svc = TranslationService(provider=MockProvider(), fail_on_error=False)
        # Deadline already passed.
        past_deadline = int(time.time() * 1000) - 10_000
        with pytest.raises(TimeBudgetExceededError):
            await svc.translate(["test"], "zh-TW", deadline_epoch_ms=past_deadline)

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
