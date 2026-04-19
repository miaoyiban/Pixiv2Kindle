"""Internal enqueue endpoint – called by Cloudflare Workers.

Validates the internal API token and enqueues a task.
In VM-direct mode this endpoint is optional (interactions.py handles
everything), but it's needed for the Workers + Backend architecture.

Spec reference: §9.1.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Header, HTTPException

from apps.api_server.dependencies import get_settings, get_task_queue
from packages.core.config import Settings
from packages.core.domain.value_objects import (
    DeadlineInfo,
    EnqueueRequest,
    EnqueueResponse,
    TaskPayload,
)
from packages.core.queue.local_background import LocalBackgroundQueue

router = APIRouter()


@router.post(
    "/internal/enqueue/pixiv-to-kindle",
    response_model=EnqueueResponse,
)
async def enqueue_pixiv_to_kindle(
    req: EnqueueRequest,
    settings: Settings = Depends(get_settings),
    queue: LocalBackgroundQueue = Depends(get_task_queue),
    x_internal_token: str = Header(default=""),
) -> EnqueueResponse:
    """Accept a task from Cloudflare Workers and enqueue it."""
    # Verify internal token.
    if not settings.internal_api_token:
        raise HTTPException(500, "INTERNAL_API_TOKEN not configured")
    if x_internal_token != settings.internal_api_token:
        raise HTTPException(403, "Invalid internal token")

    # Verify user.
    if req.user.discord_user_id != settings.allowed_discord_user_id:
        raise HTTPException(403, "Unauthorised user")

    # Build task payload with deadline.
    interaction_epoch_ms = int(time.time() * 1000)
    soft_deadline_ms = (
        interaction_epoch_ms + settings.followup_soft_deadline_seconds * 1000
    )

    payload = TaskPayload(
        request_id=req.request_id,
        discord=req.discord,
        user=req.user,
        command=req.command,
        deadline=DeadlineInfo(followup_deadline_epoch_ms=soft_deadline_ms),
    )

    await queue.enqueue_send_novel(payload)
    return EnqueueResponse(accepted=True, queued=True)
