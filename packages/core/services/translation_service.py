"""Translation service – orchestrates translation of text blocks.

Handles provider selection, time budget estimation, batch translation,
and fallback/degradation strategy.

Spec references: §12.1 – §12.7.
"""

from __future__ import annotations

import math

from loguru import logger

from packages.core.domain.models import BilingualBlock
from packages.core.exceptions import TranslationError
from packages.core.providers.translation.base import TranslationProvider
from packages.core.utils.time_budget import remaining_seconds


# ── Estimation constants ──────────────────────────────
# Based on user data: ~20K chars ≈ 6 min serial.
# With the Gemini provider batching at 12 blocks/batch and
# ~4000 chars/batch, one batch takes ~60-90s including overhead.
# Parallel execution (concurrency=3) brings this down ~2-3x.
_ESTIMATED_SECONDS_PER_BATCH = 70.0
_BLOCKS_PER_BATCH = 12


class TranslationService:
    """Translate source blocks using the configured provider.

    Features:
    - Pre-flight time budget estimation with warning (spec §12.6)
    - Always attempts translation regardless of time budget
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
        TranslationError
            If ``fail_on_error=True`` and translation fails.
        """
        n = len(source_blocks)

        # ── 1. Time budget estimation (warning only) ──
        if deadline_epoch_ms > 0:
            self._log_time_estimate(n, deadline_epoch_ms)

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
                "[translation] Translation failed, degrading to source-only: {}",
                repr(exc),
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
                "[translation] Uncaught translation exception, degrading to source-only: {}",
                repr(exc),
                exc_info=exc
            )
            return [
                BilingualBlock(source=s, translated=None)
                for s in source_blocks
            ]

    def _log_time_estimate(
        self,
        block_count: int,
        deadline_epoch_ms: int,
    ) -> None:
        """Log estimated translation time vs remaining budget.

        Unlike the previous _check_time_budget, this method **never**
        raises an exception.  Translation always proceeds — the user
        prefers to receive the translated EPUB on Kindle even if the
        Discord follow-up notification deadline is missed.
        """
        remaining = remaining_seconds(deadline_epoch_ms)
        batch_count = max(1, math.ceil(block_count / _BLOCKS_PER_BATCH))
        estimated = batch_count * _ESTIMATED_SECONDS_PER_BATCH

        if estimated > remaining:
            logger.warning(
                "[translation] Estimated {:.0f}s for {} blocks ({} batches), "
                "but only {:.0f}s remaining — proceeding anyway "
                "(Discord notification may be missed)",
                estimated,
                block_count,
                batch_count,
                remaining,
            )
        else:
            logger.info(
                "[translation] Budget OK: ~{:.0f}s estimated ({} batches), "
                "{:.0f}s remaining",
                estimated,
                batch_count,
                remaining,
            )
