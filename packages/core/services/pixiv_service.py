"""Async pixiv service – the bridge between the core layer and pixivpy3.

pixivpy3 is synchronous, so every blocking call goes through
``asyncio.to_thread()`` (spec §11.2).
"""

from __future__ import annotations

import asyncio

from loguru import logger

from packages.core.domain.models import PixivNovel
from packages.core.providers.pixiv.pixivpy_client import PixivpyClient
from packages.core.providers.pixiv.resolver import parse_novel_input
from packages.core.exceptions import InvalidInputError


class PixivService:
    """Fetch pixiv novels asynchronously."""

    def __init__(self, client: PixivpyClient) -> None:
        self._client = client

    async def fetch_novel(self, novel_input: str) -> PixivNovel:
        """Parse *novel_input* and return a fully-populated :class:`PixivNovel`.

        Raises
        ------
        InvalidInputError
            If the input cannot be parsed or is a series (not yet supported).
        PixivAuthError
            If the pixiv refresh token is invalid.
        PixivFetchError
            If the novel cannot be fetched.
        """
        parsed = parse_novel_input(novel_input)

        if parsed.input_type == "series":
            raise InvalidInputError(
                user_message="系列小說尚未支援，請使用單篇小說 URL 或 ID",
            )

        assert parsed.novel_id is not None
        logger.info("Fetching pixiv novel {}", parsed.novel_id)

        novel = await asyncio.to_thread(self._client.build_novel, parsed.novel_id)
        logger.info(
            "Fetched novel: {} ({}chars)",
            novel.title,
            len(novel.text),
        )
        return novel
