"""No-op translation provider – returns input unchanged.

Used when ``translate=false`` or as a test double.
"""

from __future__ import annotations

from loguru import logger


class NoopTranslationProvider:
    """Pass-through: returns the source blocks as-is."""

    async def translate_blocks(
        self,
        blocks: list[str],
        target_lang: str,
    ) -> list[str]:
        logger.debug("[noop] Skipping translation for {} blocks", len(blocks))
        return blocks
