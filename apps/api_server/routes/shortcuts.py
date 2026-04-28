"""Direct API endpoint for iOS Shortcuts.

Bypasses Discord entirely – authenticates via a pre-shared X-API-Key header.
The pipeline runs as normal but skips the Discord follow-up step, since there
is no interaction token.  Results are delivered exclusively via Kindle email.

Spec reference: §9.4 (M5).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger
from pydantic import BaseModel

from apps.api_server.dependencies import get_settings, get_task_queue
from packages.core.config import Settings
from packages.core.domain.value_objects import (
    CommandPayload,
    DeadlineInfo,
    EnqueueResponse,
    TaskPayload,
)
from packages.core.queue.base import TaskQueue

router = APIRouter()


class ShortcutRequest(BaseModel):
    """Minimal request body – no Discord context needed."""

    novel_input: str
    translate: bool = False
    target_lang: str = "zh-TW"


@router.post(
    "/api/shortcuts/pixiv-to-kindle",
    response_model=EnqueueResponse,
    summary="iOS Shortcut direct trigger",
    description=(
        "Enqueue a pixiv-to-kindle task from an iOS Shortcut. "
        "Requires a valid X-API-Key header. "
        "Results are delivered to Kindle via email; no Discord notification is sent."
    ),
)
async def shortcut_pixiv_to_kindle(
    req: ShortcutRequest,
    settings: Settings = Depends(get_settings),
    queue: TaskQueue = Depends(get_task_queue),
    x_api_key: str = Header(default=""),
) -> EnqueueResponse:
    """Accept a task from an iOS Shortcut and enqueue it."""
    # 1. Verify API key.
    if not settings.shortcut_api_key:
        raise HTTPException(500, "SHORTCUT_API_KEY not configured")
    if x_api_key != settings.shortcut_api_key:
        raise HTTPException(403, "Invalid API key")

    # 2. Build task payload with no Discord context and no deadline.
    request_id = str(uuid.uuid4())
    payload = TaskPayload(
        request_id=request_id,
        discord=None,
        user=None,
        command=CommandPayload(
            novel_input=req.novel_input,
            translate=req.translate,
            target_lang=req.target_lang,
        ),
        deadline=DeadlineInfo(followup_deadline_epoch_ms=0),  # no Discord deadline
    )

    logger.info(
        "[shortcut] request_id={} novel_input={} translate={}",
        request_id,
        req.novel_input,
        req.translate,
    )

    # 3. Enqueue – pipeline will skip Discord follow-up automatically.
    await queue.enqueue_send_novel(payload)
    return EnqueueResponse(accepted=True, queued=True)
