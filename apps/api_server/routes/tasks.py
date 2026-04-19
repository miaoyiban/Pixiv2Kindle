"""Task execution endpoint – called by Cloud Tasks or directly.

This endpoint is for explicit task execution (e.g. from Cloud Tasks
in M2, or for manual testing).

Spec reference: §17.1.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from apps.api_server.dependencies import get_pixiv_to_kindle_service, get_settings
from packages.core.config import Settings
from packages.core.domain.value_objects import TaskPayload
from packages.core.services.pixiv_to_kindle_service import PixivToKindleService

router = APIRouter()


@router.post("/internal/tasks/execute")
async def execute_task(
    payload: TaskPayload,
    settings: Settings = Depends(get_settings),
    service: PixivToKindleService = Depends(get_pixiv_to_kindle_service),
    x_internal_token: str = Header(default=""),
) -> dict:
    """Execute a pixiv-to-kindle task synchronously (within this request)."""
    # Verify internal token.
    if settings.internal_api_token and x_internal_token != settings.internal_api_token:
        raise HTTPException(403, "Invalid internal token")

    result = await service.execute(payload)
    return {
        "success": result.success,
        "message": result.message,
        "title": result.title,
        "novel_id": result.novel_id,
    }
