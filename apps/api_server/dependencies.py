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
from packages.core.providers.translation.base import TranslationProvider
from packages.core.queue.base import TaskQueue
from packages.core.services.epub_service import EpubService
from packages.core.services.pixiv_service import PixivService
from packages.core.services.pixiv_to_kindle_service import PixivToKindleService
from packages.core.services.translation_service import TranslationService


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
def get_translation_provider() -> TranslationProvider:
    """Return the configured translation provider.

    Controlled by ``TRANSLATION_PROVIDER``:
      - ``noop``   → pass-through (default)
      - ``gemini`` → Google Gemini API
      - ``openai`` → OpenAI Chat Completions
    """
    settings = get_settings()
    name = settings.translation_provider.lower()

    if name == "gemini":
        from packages.core.providers.translation.gemini import GeminiTranslationProvider
        return GeminiTranslationProvider(api_key=settings.gemini_api_key)

    if name == "openai":
        from packages.core.providers.translation.openai import OpenAITranslationProvider
        return OpenAITranslationProvider(api_key=settings.openai_api_key)

    # Default: noop.
    from packages.core.providers.translation.noop import NoopTranslationProvider
    return NoopTranslationProvider()


@lru_cache(maxsize=1)
def get_translation_service() -> TranslationService:
    settings = get_settings()
    return TranslationService(
        provider=get_translation_provider(),
        fail_on_error=settings.fail_on_translation_error,
    )


@lru_cache(maxsize=1)
def get_pixiv_to_kindle_service() -> PixivToKindleService:
    settings = get_settings()
    return PixivToKindleService(
        pixiv_service=get_pixiv_service(),
        epub_service=get_epub_service(),
        kindle_sender=get_kindle_sender(),
        discord_notifier=get_discord_notifier(),
        translation_service=get_translation_service(),
        max_epub_bytes=settings.max_epub_bytes,
    )


@lru_cache(maxsize=1)
def get_task_queue() -> TaskQueue:
    """Return the task queue for the current deployment mode.

    Controlled by the ``QUEUE_BACKEND`` env var:
      - ``local``       → in-process asyncio task  (VM / dev)
      - ``cloud_tasks`` → GCP Cloud Tasks           (Cloud Run)
    """
    settings = get_settings()

    if settings.queue_backend == "cloud_tasks":
        from packages.core.queue.cloud_tasks import CloudTasksQueue

        return CloudTasksQueue(
            project_id=settings.cloud_tasks_project_id,
            location=settings.cloud_tasks_location,
            queue_name=settings.cloud_tasks_queue_name,
            task_handler_url=settings.cloud_tasks_task_handler_url,
            internal_api_token=settings.internal_api_token,
        )

    # Default: local background queue.
    from packages.core.queue.local_background import LocalBackgroundQueue

    return LocalBackgroundQueue(service=get_pixiv_to_kindle_service())
