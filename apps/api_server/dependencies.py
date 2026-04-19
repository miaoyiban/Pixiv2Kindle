"""Dependency injection for the FastAPI application.

All service singletons are created once at startup and shared via
FastAPI's dependency system.
"""

from __future__ import annotations

from functools import lru_cache

from packages.core.config import Settings
from packages.core.providers.discord.webhook_client import DiscordWebhookClient
from packages.core.providers.kindle.smtp_sender import SmtpKindleSender
from packages.core.providers.pixiv.pixivpy_client import PixivpyClient
from packages.core.queue.local_background import LocalBackgroundQueue
from packages.core.services.epub_service import EpubService
from packages.core.services.pixiv_service import PixivService
from packages.core.services.pixiv_to_kindle_service import PixivToKindleService


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton settings instance."""
    return Settings()


@lru_cache(maxsize=1)
def get_pixiv_service() -> PixivService:
    settings = get_settings()
    client = PixivpyClient(refresh_token=settings.pixiv_refresh_token)
    return PixivService(client)


@lru_cache(maxsize=1)
def get_epub_service() -> EpubService:
    settings = get_settings()
    return EpubService(temp_dir=settings.temp_dir)


@lru_cache(maxsize=1)
def get_kindle_sender() -> SmtpKindleSender:
    settings = get_settings()
    return SmtpKindleSender(
        kindle_email=settings.kindle_email,
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port,
        smtp_username=settings.smtp_username,
        smtp_password=settings.smtp_password,
        smtp_from=settings.smtp_from,
    )


@lru_cache(maxsize=1)
def get_discord_notifier() -> DiscordWebhookClient:
    return DiscordWebhookClient()


@lru_cache(maxsize=1)
def get_pixiv_to_kindle_service() -> PixivToKindleService:
    settings = get_settings()
    return PixivToKindleService(
        pixiv_service=get_pixiv_service(),
        epub_service=get_epub_service(),
        kindle_sender=get_kindle_sender(),
        discord_notifier=get_discord_notifier(),
        max_epub_bytes=settings.max_epub_bytes,
    )


@lru_cache(maxsize=1)
def get_task_queue() -> LocalBackgroundQueue:
    """Return the task queue appropriate for the current deployment.

    M1: always ``LocalBackgroundQueue``.
    M2: will add ``CloudTasksQueue`` branch based on settings.
    """
    return LocalBackgroundQueue(service=get_pixiv_to_kindle_service())
