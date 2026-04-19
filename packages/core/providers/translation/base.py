"""Translation provider protocol.

All translation providers must implement this interface.
Spec reference: §12.5.
"""

from __future__ import annotations

from typing import Protocol


class TranslationProvider(Protocol):
    """Translate a list of text blocks into *target_lang*."""

    async def translate_blocks(
        self,
        blocks: list[str],
        target_lang: str,
    ) -> list[str]:
        """Return translated texts, one per input block.

        The output list **must** be the same length as *blocks*.
        """
        ...
