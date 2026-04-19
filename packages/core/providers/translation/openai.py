"""OpenAI translation provider.

Uses OpenAI Chat Completions API for paragraph-level translation.
Spec references: §12.4, §12.5.
"""

from __future__ import annotations

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

_OPENAI_API_BASE = "https://api.openai.com/v1/chat/completions"


class OpenAITranslationProvider:
    """Translate blocks using OpenAI Chat Completions API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-4o-mini",
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

        for i in range(0, len(blocks), self._max_blocks):
            batch = blocks[i : i + self._max_blocks]
            batch_num = i // self._max_blocks + 1
            total_batches = (len(blocks) - 1) // self._max_blocks + 1

            logger.info(
                "[openai] Translating batch {}/{} ({} blocks)",
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
        """Send one batch to the OpenAI API."""
        system_prompt = _SYSTEM_PROMPT.format(target_lang=target_lang)
        user_prompt = json.dumps(batch, ensure_ascii=False)

        payload = {
            "model": self._model,
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    _OPENAI_API_BASE,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)

            # Handle both { "translations": [...] } and plain [...] formats.
            if isinstance(parsed, dict):
                # Look for the first list value.
                for v in parsed.values():
                    if isinstance(v, list):
                        translated = v
                        break
                else:
                    raise TranslationError(
                        f"OpenAI returned dict without list: {list(parsed.keys())}",
                        user_message="翻譯服務回傳格式錯誤",
                    )
            elif isinstance(parsed, list):
                translated = parsed
            else:
                raise TranslationError(
                    f"OpenAI returned unexpected type: {type(parsed)}",
                    user_message="翻譯服務回傳格式錯誤",
                )

            if len(translated) != len(batch):
                raise TranslationError(
                    f"OpenAI returned {len(translated)} blocks, expected {len(batch)}",
                    user_message="翻譯結果數量不一致",
                )

            return [str(t) for t in translated]

        except TranslationError:
            raise
        except httpx.HTTPStatusError as exc:
            raise TranslationError(
                f"OpenAI API error: {exc.response.status_code} – {exc.response.text[:200]}",
                user_message="翻譯服務 API 錯誤",
            ) from exc
        except json.JSONDecodeError as exc:
            raise TranslationError(
                f"Failed to parse OpenAI response as JSON: {exc}",
                user_message="翻譯服務回傳格式錯誤",
            ) from exc
        except Exception as exc:
            raise TranslationError(
                f"OpenAI translation failed: {exc}",
                user_message="翻譯服務發生錯誤",
            ) from exc
