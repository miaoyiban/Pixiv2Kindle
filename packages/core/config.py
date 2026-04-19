"""Application settings loaded from environment variables.

Uses pydantic-settings to validate and provide typed access
to every configuration knob defined in the project spec (§22).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration – all values come from env vars or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Application ────────────────────────────────────
    app_name: str = "pixiv2kindle"
    app_env: str = "dev"
    log_level: str = "INFO"

    # ── Discord ────────────────────────────────────────
    discord_public_key: str = ""
    discord_application_id: str = ""
    discord_bot_token: str = ""
    allowed_discord_user_id: str = ""

    # ── Pixiv ──────────────────────────────────────────
    pixiv_refresh_token: str = ""

    # ── Kindle / SMTP ──────────────────────────────────
    kindle_email: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # ── Translation ────────────────────────────────────
    translation_provider: str = "noop"
    gemini_api_key: str = ""
    openai_api_key: str = ""
    fail_on_translation_error: bool = False

    # ── File handling ──────────────────────────────────
    temp_dir: str = "./tmp"
    keep_recent_epub_count: int = 0
    max_epub_bytes: int = 50_000_000  # 50 MB

    # ── Internal API ───────────────────────────────────
    internal_api_token: str = ""
    backend_base_url: str = ""

    # ── Queue ──────────────────────────────────────────
    queue_backend: str = "local"  # "local" | "cloud_tasks"
    cloud_tasks_project_id: str = ""
    cloud_tasks_location: str = ""
    cloud_tasks_queue_name: str = ""
    cloud_tasks_task_handler_url: str = ""

    # ── Deadline ───────────────────────────────────────
    followup_soft_deadline_seconds: int = 720   # 12 min
    followup_hard_deadline_seconds: int = 900   # 15 min
