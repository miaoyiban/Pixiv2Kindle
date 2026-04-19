"""Main orchestration service – the heart of the application.

Coordinates: input parsing → pixiv fetch → text split →
(optional translation) → EPUB build → file-size check →
Kindle delivery → Discord follow-up.

Spec references: §18, §19, §26.
"""

from __future__ import annotations

import os
import time

from loguru import logger

from packages.core.domain.models import BilingualBlock, SendNovelResult
from packages.core.domain.value_objects import TaskPayload
from packages.core.exceptions import (
    DiscordNotifyError,
    Pixiv2KindleError,
)
from packages.core.providers.discord.webhook_client import DiscordWebhookClient
from packages.core.providers.kindle.smtp_sender import SmtpKindleSender
from packages.core.services.epub_service import EpubService
from packages.core.services.pixiv_service import PixivService
from packages.core.utils.file_utils import ensure_file_size
from packages.core.utils.sanitizer import normalise_text
from packages.core.utils.text_splitter import split_text_into_blocks
from packages.core.utils.time_budget import ensure_time_budget, is_within_deadline


class PixivToKindleService:
    """Execute the full pixiv-to-kindle pipeline for one task."""

    def __init__(
        self,
        *,
        pixiv_service: PixivService,
        epub_service: EpubService,
        kindle_sender: SmtpKindleSender,
        discord_notifier: DiscordWebhookClient,
        max_epub_bytes: int = 50_000_000,
    ) -> None:
        self._pixiv = pixiv_service
        self._epub = epub_service
        self._kindle = kindle_sender
        self._discord = discord_notifier
        self._max_epub_bytes = max_epub_bytes

    async def execute(self, payload: TaskPayload) -> SendNovelResult:
        """Run the complete pipeline described in spec §19.2."""
        start = time.monotonic()
        request_id = payload.request_id
        deadline_ms = payload.deadline.followup_deadline_epoch_ms
        file_path: str | None = None

        logger.info(
            "[task:{}] Starting – novel_input={} translate={}",
            request_id,
            payload.command.novel_input,
            payload.command.translate,
        )

        try:
            # 1. Check time budget.
            if deadline_ms > 0:
                ensure_time_budget(deadline_ms)

            # 2. Fetch novel.
            novel = await self._pixiv.fetch_novel(payload.command.novel_input)

            # 3. Normalise & split.
            clean_text = normalise_text(novel.text)
            # Replace text in the novel (frozen dataclass → rebuild).
            from dataclasses import replace
            novel = replace(novel, text=clean_text)

            source_blocks = split_text_into_blocks(novel.text)
            logger.info("[task:{}] Split into {} blocks", request_id, len(source_blocks))

            # 4. Build bilingual blocks (M1: translate=false only).
            blocks = [
                BilingualBlock(source=s, translated=None)
                for s in source_blocks
            ]

            # 5. Build EPUB.
            file_path = await self._epub.build(novel, blocks)

            # 6. Check file size.
            ensure_file_size(file_path, max_bytes=self._max_epub_bytes)

            # 7. Send to Kindle.
            await self._kindle.send(file_path)

            # 8. Discord follow-up.
            elapsed = time.monotonic() - start
            message = f"✅ 已寄送《{novel.title}》到 Kindle（耗時 {elapsed:.1f}s）"

            if deadline_ms == 0 or is_within_deadline(deadline_ms):
                await self._discord.send_followup(
                    application_id=payload.discord.application_id,
                    interaction_token=payload.discord.interaction_token,
                    content=message,
                )
            else:
                logger.warning("[task:{}] Follow-up deadline exceeded, skipping notification", request_id)

            result = SendNovelResult(
                success=True,
                title=novel.title,
                novel_id=novel.novel_id,
                file_path=file_path,
                message=message,
            )

        except Pixiv2KindleError as exc:
            elapsed = time.monotonic() - start
            logger.error("[task:{}] Failed ({:.1f}s): {}", request_id, elapsed, exc)
            await self._notify_error(payload, exc.user_message, deadline_ms)
            result = SendNovelResult(
                success=False,
                message=exc.user_message,
            )

        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.exception("[task:{}] Unexpected error ({:.1f}s)", request_id, elapsed)
            await self._notify_error(payload, "處理過程中發生未預期的錯誤", deadline_ms)
            result = SendNovelResult(
                success=False,
                message="處理過程中發生未預期的錯誤",
            )

        finally:
            # Clean up temp file.
            if file_path:
                try:
                    os.remove(file_path)
                    logger.debug("[task:{}] Cleaned up {}", request_id, file_path)
                except OSError:
                    pass

            elapsed = time.monotonic() - start
            logger.info(
                "[task:{}] Completed in {:.1f}s – success={}",
                request_id,
                elapsed,
                result.success,
            )

        return result

    async def _notify_error(
        self,
        payload: TaskPayload,
        user_message: str,
        deadline_ms: int,
    ) -> None:
        """Best-effort error notification to Discord."""
        if deadline_ms > 0 and not is_within_deadline(deadline_ms):
            logger.warning("Cannot send error follow-up: deadline exceeded")
            return
        try:
            await self._discord.send_followup(
                application_id=payload.discord.application_id,
                interaction_token=payload.discord.interaction_token,
                content=f"❌ {user_message}",
            )
        except DiscordNotifyError:
            logger.exception("Failed to send error follow-up to Discord")
