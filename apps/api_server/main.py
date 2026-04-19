"""FastAPI application entry-point.

Run with:
    uvicorn apps.api_server.main:app --host 0.0.0.0 --port 8000

Spec references: §16, §17.
"""

from __future__ import annotations

import sys
from loguru import logger

from fastapi import FastAPI

from apps.api_server.dependencies import get_settings
from apps.api_server.routes import enqueue, health, interactions, tasks

# ── Logging ────────────────────────────────────────────


def _configure_logging() -> None:
    settings = get_settings()
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "{message}"
        ),
    )


# ── App ────────────────────────────────────────────────


def create_app() -> FastAPI:
    _configure_logging()
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs" if settings.app_env == "dev" else None,
        redoc_url=None,
    )

    # Register routers.
    application.include_router(health.router)
    application.include_router(interactions.router)
    application.include_router(enqueue.router)
    application.include_router(tasks.router)

    @application.on_event("startup")
    async def _startup() -> None:
        logger.info(
            "Starting {} (env={}, queue={})",
            settings.app_name,
            settings.app_env,
            settings.queue_backend,
        )

    return application


app = create_app()
