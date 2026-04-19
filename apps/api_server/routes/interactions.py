"""Discord Interaction endpoint – direct VM mode.

Handles Discord's Interaction lifecycle:
  1. Ed25519 signature verification
  2. PING (type 1) → pong
  3. APPLICATION_COMMAND (type 2) → deferred ack + enqueue background task

Spec references: §8, §16.1, §19.1.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from loguru import logger
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from apps.api_server.dependencies import get_settings, get_task_queue
from packages.core.config import Settings
from packages.core.domain.value_objects import (
    CommandPayload,
    DeadlineInfo,
    DiscordContext,
    TaskPayload,
    UserContext,
)
from packages.core.exceptions import UnauthorizedUserError
from packages.core.queue.base import TaskQueue

router = APIRouter()

# Discord interaction types.
_PING = 1
_APPLICATION_COMMAND = 2

# Discord response types.
_PONG = 1
_DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE = 5


def _verify_signature(
    body: bytes,
    signature: str,
    timestamp: str,
    public_key: str,
) -> None:
    """Verify Discord Ed25519 request signature.

    Raises ``BadSignatureError`` on failure.
    """
    vk = VerifyKey(bytes.fromhex(public_key))
    vk.verify(timestamp.encode() + body, bytes.fromhex(signature))


def _extract_option(
    options: list[dict[str, Any]] | None,
    name: str,
    *,
    default: Any = None,
) -> Any:
    """Pull a named option from the interaction data options list."""
    if not options:
        return default
    for opt in options:
        if opt.get("name") == name:
            return opt.get("value", default)
    return default


@router.post("/interactions")
async def discord_interactions(
    request: Request,
    settings: Settings = Depends(get_settings),
    queue: TaskQueue = Depends(get_task_queue),
) -> Response:
    """Handle incoming Discord Interactions."""
    # ── Read raw body for signature verification ───────
    body = await request.body()
    signature = request.headers.get("X-Signature-Ed25519", "")
    timestamp = request.headers.get("X-Signature-Timestamp", "")

    try:
        _verify_signature(body, signature, timestamp, settings.discord_public_key)
    except (BadSignatureError, Exception) as exc:
        logger.warning("Discord signature verification failed: {}", exc)
        return JSONResponse({"error": "invalid signature"}, status_code=401)

    # ── Parse interaction ──────────────────────────────
    payload: dict[str, Any] = await request.json()
    interaction_type = payload.get("type")

    # PING – Discord health check.
    if interaction_type == _PING:
        return JSONResponse({"type": _PONG})

    # APPLICATION_COMMAND – process command.
    if interaction_type == _APPLICATION_COMMAND:
        # Authorise user.
        user = payload.get("member", {}).get("user", {}) or payload.get("user", {})
        user_id = user.get("id", "")

        if user_id != settings.allowed_discord_user_id:
            logger.warning("Unauthorised Discord user: {}", user_id)
            return JSONResponse(
                {
                    "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
                    "data": {"content": "❌ 你沒有使用此指令的權限", "flags": 64},
                },
            )

        # Parse command options.
        data = payload.get("data", {})
        options = data.get("options")

        novel_input = _extract_option(options, "novel", default="")
        translate = _extract_option(options, "translate", default=False)
        target_lang = _extract_option(options, "target_lang", default="zh-TW")

        if not novel_input:
            return JSONResponse(
                {
                    "type": 4,
                    "data": {"content": "❌ 請提供 pixiv 小說 URL 或 ID", "flags": 64},
                },
            )

        # Build task payload.
        request_id = str(uuid.uuid4())
        interaction_epoch_ms = int(time.time() * 1000)
        soft_deadline_ms = interaction_epoch_ms + settings.followup_soft_deadline_seconds * 1000

        task_payload = TaskPayload(
            request_id=request_id,
            discord=DiscordContext(
                application_id=settings.discord_application_id,
                interaction_token=payload.get("token", ""),
                channel_id=payload.get("channel_id"),
                guild_id=payload.get("guild_id"),
            ),
            user=UserContext(discord_user_id=user_id),
            command=CommandPayload(
                novel_input=str(novel_input),
                translate=bool(translate),
                target_lang=str(target_lang),
            ),
            deadline=DeadlineInfo(followup_deadline_epoch_ms=soft_deadline_ms),
        )

        logger.info(
            "[interaction] request_id={} novel_input={} user={}",
            request_id,
            novel_input,
            user_id,
        )

        # Enqueue background task.
        await queue.enqueue_send_novel(task_payload)

        # Return deferred ack immediately.
        return JSONResponse({"type": _DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE})

    # Unrecognised interaction type.
    logger.warning("Unknown interaction type: {}", interaction_type)
    return JSONResponse({"error": "unknown interaction type"}, status_code=400)
