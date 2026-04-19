"""Translation service – orchestrates translation of text blocks.

Handles provider selection, time budget estimation, batch translation,
and fallback/degradation strategy.

Spec references: §12.1 – §12.7.
"""

from __future__ import annotations

from loguru import logger

from packages.core.domain.models import BilingualBlock
from packages.core.exceptions import TimeBudgetExceededError, TranslationError
from packages.core.providers.translation.base import TranslationProvider
from packages.core.utils.time_budget import is_within_deadline, remaining_seconds


# Rough estimate: ~2 seconds per block for LLM translation.
_ESTIMATED_SECONDS_PER_BLOCK = 2.0
# Minimum remaining seconds to even attempt translation.
_MIN_REMAINING_FOR_TRANSLATION = 60.0


class TranslationService:
    """Translate source blocks using the configured provider.

    Features:
    - Pre-flight time budget estimation (spec §12.6)
    - Configurable degradation on failure (spec §12.7)
    """

    def __init__(
        self,
        *,
        provider: TranslationProvider,
        fail_on_error: bool = False,
    ) -> None:
        self._provider = provider
        self._fail_on_error = fail_on_error

    async def translate(
        self,
        source_blocks: list[str],
        target_lang: str,
        deadline_epoch_ms: int = 0,
    ) -> list[BilingualBlock]:
        """Translate *source_blocks* and return bilingual blocks.

        Parameters
        ----------
        source_blocks
            The raw paragraphs to translate.
        target_lang
            Target language code (e.g. ``"zh-TW"``).
        deadline_epoch_ms
            The Discord follow-up deadline (epoch ms).
            If ``0``, no deadline enforcement.

        Returns
        -------
        list[BilingualBlock]
            Each block contains source + translated text.
            On degradation (``fail_on_error=False``), translated may be
            ``None`` for blocks that failed.

        Raises
        ------
        TimeBudgetExceededError
            If the estimated translation time exceeds the remaining budget.
        TranslationError
            If ``fail_on_error=True`` and translation fails.
        """
        n = len(source_blocks)

        # ── 1. Time budget pre-check (spec §12.6) ─────
        if deadline_epoch_ms > 0:
            self._check_time_budget(n, deadline_epoch_ms)

        # ── 2. Translate ──────────────────────────────
        try:
            translated = await self._provider.translate_blocks(
                source_blocks, target_lang
            )

            logger.info(
                "[translation] Successfully translated {} blocks to {}",
                n,
                target_lang,
            )

            return [
                BilingualBlock(source=s, translated=t)
                for s, t in zip(source_blocks, translated)
            ]

        except TranslationError as exc:
            if self._fail_on_error:
                raise
            logger.warning(
                "[translation] Translation failed, degrading to source-only",
                exc_info=exc
            )
            return [
                BilingualBlock(source=s, translated=None)
                for s in source_blocks
            ]

        except Exception as exc:
            if self._fail_on_error:
                raise TranslationError(
                    f"Unexpected translation error: {exc}",
                    user_message="翻譯服務發生錯誤",
                ) from exc
            logger.warning(
                "[translation] Unexpected error, degrading to source-only: {}",
                exc,
            )
            return [
                BilingualBlock(source=s, translated=None)
                for s in source_blocks
            ]

    def _check_time_budget(
        self,
        block_count: int,
        deadline_epoch_ms: int,
    ) -> None:
        """Reject translation if estimated time exceeds remaining budget.

        Spec §12.6: if estimated translation time exceeds the remaining
        time, reject immediately rather than risk a timeout.
        """
        remaining = remaining_seconds(deadline_epoch_ms)

        if remaining < _MIN_REMAINING_FOR_TRANSLATION:
            raise TimeBudgetExceededError(
                f"Only {remaining:.0f}s remaining, need at least "
                f"{_MIN_REMAINING_FOR_TRANSLATION:.0f}s for translation",
                user_message="剩餘時間不足，無法進行翻譯",
            )

        estimated = block_count * _ESTIMATED_SECONDS_PER_BLOCK
        if estimated > remaining:
            raise TimeBudgetExceededError(
                f"Estimated {estimated:.0f}s for {block_count} blocks, "
                f"but only {remaining:.0f}s remaining",
                user_message="內容過長，翻譯可能超過可通知時限。請關閉翻譯或改用較短作品",
            )

        logger.info(
            "[translation] Budget OK: ~{:.0f}s estimated, {:.0f}s remaining",
            estimated,
            remaining,
        )
