"""Gemini translation provider.

Uses Google's Gemini API for paragraph-level translation.
Spec references: §12.4, §12.5.
"""

from __future__ import annotations

import asyncio
import json

import httpx
from loguru import logger

from packages.core.exceptions import TranslationError

# ── System prompt ──────────────────────────────────────

_SYSTEM_PROMPT = """\
你是精通日文小說翻譯的專業翻譯師。

翻譯原則：
- 保留專有名詞原文（人名、地名、作品名等）
- 保留人物稱謂（さん、くん、ちゃん 等，可用原文或對應中文）
- 不摘要、不省略、不改寫
- 一段對一段，保持原文段落結構
- 翻譯目標語言為：{target_lang}
- 輸出僅包含譯文，不要加任何說明或前後綴

你會收到一個 JSON 陣列，每個元素是一個日文段落。
請回傳一個 JSON 陣列，每個元素是對應的翻譯。
陣列長度必須與輸入完全一致。
"""

_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiTranslationProvider:
    """Translate blocks using Google Gemini API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gemini-2.0-flash",
        max_blocks_per_request: int = 30,
        timeout_seconds: float = 120,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._max_blocks = max_blocks_per_request
        self._timeout = timeout_seconds

    async def translate_blocks(
        self,
        blocks: list[str],
        target_lang: str,
    ) -> list[str]:
        """Translate *blocks* in batches and return the concatenated results."""
        if not blocks:
            return []

        results: list[str] = []

        # Split into batches to stay within context limits.
        for i in range(0, len(blocks), self._max_blocks):
            batch = blocks[i : i + self._max_blocks]
            batch_num = i // self._max_blocks + 1
            total_batches = (len(blocks) - 1) // self._max_blocks + 1

            logger.info(
                "[gemini] Translating batch {}/{} ({} blocks)",
                batch_num,
                total_batches,
                len(batch),
            )

            translated = await self._translate_batch(batch, target_lang)
            results.extend(translated)

        if len(results) != len(blocks):
            raise TranslationError(
                f"Translation count mismatch: expected {len(blocks)}, got {len(results)}",
                user_message="翻譯結果數量不一致",
            )

        return results

    async def _translate_batch(
        self,
        batch: list[str],
        target_lang: str,
    ) -> list[str]:
        """Send one batch to the Gemini API."""
        url = f"{_GEMINI_API_BASE}/{self._model}:generateContent?key={self._api_key}"

        system_prompt = _SYSTEM_PROMPT.format(target_lang=target_lang)
        user_prompt = json.dumps(batch, ensure_ascii=False)

        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                },
            ],
            "generationConfig": {
                "temperature": 0.3,
                "responseMimeType": "application/json",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()

            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]

            translated = json.loads(text)

            if not isinstance(translated, list):
                raise TranslationError(
                    f"Gemini returned non-list: {type(translated)}",
                    user_message="翻譯服務回傳格式錯誤",
                )

            if len(translated) != len(batch):
                raise TranslationError(
                    f"Gemini returned {len(translated)} blocks, expected {len(batch)}",
                    user_message="翻譯結果數量不一致",
                )

            return [str(t) for t in translated]

        except TranslationError:
            raise
        except httpx.HTTPStatusError as exc:
            raise TranslationError(
                f"Gemini API error: {exc.response.status_code} – {exc.response.text[:200]}",
                user_message="翻譯服務 API 錯誤",
            ) from exc
        except json.JSONDecodeError as exc:
            raise TranslationError(
                f"Failed to parse Gemini response as JSON: {exc}",
                user_message="翻譯服務回傳格式錯誤",
            ) from exc
        except Exception as exc:
            raise TranslationError(
                f"Gemini translation failed: {exc}",
                user_message="翻譯服務發生錯誤",
            ) from exc
