"""Pydantic models for API request/response schemas and task payloads.

These cross API boundaries (HTTP JSON) and therefore use Pydantic for
validation and serialisation.  Spec references: §9.1, §9.2.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Discord Interaction context ────────────────────────


class DiscordContext(BaseModel):
    application_id: str
    interaction_token: str
    channel_id: str | None = None
    guild_id: str | None = None


class UserContext(BaseModel):
    discord_user_id: str


class CommandPayload(BaseModel):
    novel_input: str
    translate: bool = False
    target_lang: str = "zh-TW"


# ── Enqueue request / response ─────────────────────────


class EnqueueRequest(BaseModel):
    request_id: str
    discord: DiscordContext
    user: UserContext
    command: CommandPayload


class EnqueueResponse(BaseModel):
    accepted: bool = True
    queued: bool = True


# ── Task payload (sent to task handler) ────────────────


class DeadlineInfo(BaseModel):
    followup_deadline_epoch_ms: int = 0


class TaskPayload(BaseModel):
    request_id: str
    discord: DiscordContext
    user: UserContext
    command: CommandPayload
    deadline: DeadlineInfo = Field(default_factory=DeadlineInfo)


# ── Parsed novel input ─────────────────────────────────


class ParsedNovelInput(BaseModel):
    """Result of parsing a user-supplied novel identifier."""

    input_type: str  # "novel" | "series"
    novel_id: int | None = None
    series_id: int | None = None
