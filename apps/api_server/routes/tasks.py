"""Task execution endpoint – called by Cloud Tasks or directly.

This endpoint is for explicit task execution (e.g. from Cloud Tasks
in M2, or for manual testing).

Spec reference: §17.1.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger

from apps.api_server.dependencies import (
    get_pixiv_to_kindle_service,
    get_settings,
    get_task_deduper,
)
from packages.core.config import Settings
from packages.core.domain.value_objects import TaskPayload
from packages.core.services.pixiv_to_kindle_service import PixivToKindleService
from packages.core.utils.task_dedupe import TaskDeduper

router = APIRouter()


@router.post("/internal/tasks/execute")
async def execute_task(
    payload: TaskPayload,
    settings: Settings = Depends(get_settings),
    service: PixivToKindleService = Depends(get_pixiv_to_kindle_service),
    deduper: TaskDeduper = Depends(get_task_deduper),
    x_internal_token: str = Header(default=""),
    x_cloudtasks_taskretrycount: str = Header(default=""),
) -> dict:
    """Execute a pixiv-to-kindle task synchronously (within this request)."""
    # Verify internal token.
    if settings.internal_api_token and x_internal_token != settings.internal_api_token:
        raise HTTPException(403, "Invalid internal token")

    # Cloud Tasks may re-deliver a task that is still running (or already
    # done). Answer 2xx so it stops retrying, instead of translating again.
    if not deduper.try_start(payload.request_id):
        logger.warning(
            "[task:{}] Duplicate delivery ignored (retry_count={})",
            payload.request_id,
            x_cloudtasks_taskretrycount or "?",
        )
        return {"success": True, "duplicate": True, "message": "already accepted"}

    result = await service.execute(payload)
    return {
        "success": result.success,
        "message": result.message,
        "title": result.title,
        "novel_id": result.novel_id,
    }
