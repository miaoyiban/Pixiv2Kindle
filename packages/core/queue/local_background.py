"""In-process background queue for VM / local development.

Spawns an ``asyncio.Task`` for each job.  No persistence, no retry –
suitable for a single-user personal tool on a long-running server.

Spec reference: §17.3.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from loguru import logger

from packages.core.domain.value_objects import TaskPayload

if TYPE_CHECKING:
    from packages.core.services.pixiv_to_kindle_service import PixivToKindleService


class LocalBackgroundQueue:
    """Fire-and-forget asyncio task runner."""

    def __init__(self, service: PixivToKindleService) -> None:
        self._service = service

    async def enqueue_send_novel(self, payload: TaskPayload) -> None:
        """Schedule *payload* for immediate background execution."""
        logger.info(
            "[queue:local] Enqueuing task request_id={}",
            payload.request_id,
        )
        asyncio.create_task(self._run(payload))

    async def _run(self, payload: TaskPayload) -> None:
        try:
            result = await self._service.execute(payload)
            logger.info(
                "[queue:local] Task {} finished: {}",
                payload.request_id,
                result.message,
            )
        except Exception:
            logger.exception(
                "[queue:local] Task {} failed with unhandled error",
                payload.request_id,
            )
