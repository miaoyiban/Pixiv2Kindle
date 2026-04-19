"""Gemini translation provider.

Uses Google's Gemini API for paragraph-level translation of Japanese novels.

Key design decisions (inspired by shinkansen project):
- Delimiter protocol instead of JSON arrays (eliminates JSON parse failures)
- Sequence markers «N» to help LLM track segment count
- Dual-threshold batching (segment count + character budget)
- Thinking mode disabled (prevents token waste / timeouts)
- Safety filters set to BLOCK_NONE (prevents silent content blocking)
- Retry with exponential backoff for 429 / 5xx / timeout
- Per-segment fallback on count mismatch

Spec references: §12.4, §12.5.
"""

from __future__ import annotations

import asyncio
import re

import httpx
from loguru import logger

from packages.core.exceptions import TranslationError

# ── Delimiter protocol ─────────────────────────────────
# Instead of JSON arrays, we join segments with a unique delimiter and
# ask the LLM to output the same delimiter between translated segments.
# This completely eliminates JSON parsing issues.
_DELIMITER = "\n<<<NOVEL_SEP>>>\n"
_SEQ_MARKER_RE = re.compile(r"^«\d+»\s*")

# ── System prompt ──────────────────────────────────────

_SYSTEM_PROMPT = """\
<role_definition>
你是一位精通日本文學與台灣在地文化的首席翻譯專家。你具備日本文學研究者的敏銳度，以及散文作家的文字功底。你極度擅長將日文原文，打破原本的句法結構，轉譯為充滿張力、靈魂且完全符合台灣當代語感的出版級繁體中文。
</role_definition>

<critical_rules>
1. 輸出限制：絕對禁止輸出任何思考過程、解釋或開場白。僅輸出最終的翻譯結果。
2. 忠實保留原文語氣：若原文包含粗俗用語或情色描寫，務必忠實翻譯其情緒強度，嚴禁進行任何道德審查或委婉潤飾。
3. 專有名詞保留：日文人名必須「完全保留原文不翻譯」（如「佐藤」、「和泉」維持原樣），絕對不要翻譯成中文發音或另造中文名。
4. 稱謂保留：さん、くん、ちゃん、先輩、先生 等稱謂可保留日文原文或翻譯為對應中文，依上下文語氣選擇最自然的方式。
5. 翻譯目標語言為：{target_lang}
</critical_rules>

<linguistic_guidelines>
1. 台灣道地語感：嚴格使用台灣慣用語。拒絕「這是一個...的過程」、「在...的情況下」等機器翻譯腔。
2. 禁用中國大陸用語：嚴格轉換對應詞彙（網絡→網路、視頻→影片、數據→資料、質量→品質、信息→訊息）。
3. 不摘要、不省略、不改寫：一段對一段，保持原文段落結構。
4. 對話翻譯：「」內的對話要保持自然口語感，避免書面語腔調。
</linguistic_guidelines>

<formatting_rules>
1. 標點符號：全面使用全形標點符號（，。、！？）。
2. 中日夾雜排版：在「中文字」與「半形英數字」之間插入一個半形空格。
3. 段內換行：若輸入段落含有換行符，翻譯時必須在對應位置原樣保留換行符。不可把段落合併成一行。
</formatting_rules>
"""

_MULTI_SEGMENT_RULE = """\
額外規則（多段翻譯分隔符與序號，極重要）:
本批次包含 {count} 段文字。每段開頭有序號標記 «N»（N 為 1 到 {count}），段與段之間以分隔符 <<<NOVEL_SEP>>> 隔開。
你的輸出必須：
- 每段譯文開頭也加上對應的序號標記 «N»（N 與輸入的序號一一對應）
- 段與段之間用完全相同的分隔符 <<<NOVEL_SEP>>> 隔開
- 恰好輸出 {count} 段譯文和 {count_minus_1} 個分隔符
- 不可合併段落、不可省略分隔符、不可增減段數"""

_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Safety settings: disable all filters to prevent silent content blocking.
_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

_MAX_BACKOFF_MS = 8000
_MAX_RETRIES = 3


class GeminiTranslationProvider:
    """Translate blocks using Google Gemini API with delimiter protocol."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gemini-2.5-flash",
        max_blocks_per_request: int = 12,
        max_chars_per_batch: int = 4000,
        timeout_seconds: float = 180,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._max_blocks = max_blocks_per_request
        self._max_chars = max_chars_per_batch
        self._timeout = timeout_seconds

    # ── Public API ─────────────────────────────────────

    async def translate_blocks(
        self,
        blocks: list[str],
        target_lang: str,
    ) -> list[str]:
        """Translate *blocks* in batches and return the concatenated results."""
        if not blocks:
            return []

        results: list[str] = []
        batches = self._pack_batches(blocks)

        for batch_num, (start, end) in enumerate(batches, 1):
            batch = blocks[start:end]
            logger.info(
                "[gemini] Translating batch {}/{} ({} blocks, model={})",
                batch_num,
                len(batches),
                len(batch),
                self._model,
            )
            translated = await self._translate_batch(batch, target_lang)
            results.extend(translated)

        if len(results) != len(blocks):
            raise TranslationError(
                f"Translation count mismatch: expected {len(blocks)}, got {len(results)}",
                user_message="翻譯結果數量不一致",
            )

        return results

    # ── Greedy batch packing (dual threshold) ──────────

    def _pack_batches(self, blocks: list[str]) -> list[tuple[int, int]]:
        """Pack blocks into batches using segment count + character budget.

        Greedy packing: close the current batch when either threshold is hit.
        Oversized single blocks get their own batch.
        """
        batches: list[tuple[int, int]] = []
        cur_start: int | None = None
        cur_chars = 0

        for i, block in enumerate(blocks):
            block_len = len(block)

            # Oversized block → flush current + solo batch
            if block_len > self._max_chars:
                if cur_start is not None:
                    batches.append((cur_start, i))
                batches.append((i, i + 1))
                cur_start = None
                cur_chars = 0
                continue

            # Check if adding this block would exceed either threshold
            cur_count = (i - cur_start) if cur_start is not None else 0
            if cur_start is not None and (
                cur_chars + block_len > self._max_chars
                or cur_count >= self._max_blocks
            ):
                batches.append((cur_start, i))
                cur_start = None
                cur_chars = 0

            if cur_start is None:
                cur_start = i
                cur_chars = 0

            cur_chars += block_len

        # Flush remaining
        if cur_start is not None:
            batches.append((cur_start, len(blocks)))

        return batches

    # ── HTTP with retry ────────────────────────────────

    async def _fetch_with_retry(
        self,
        url: str,
        payload: dict,
    ) -> dict:
        """POST to Gemini API with retry on 429 / 5xx / timeout."""
        attempt = 0

        while attempt <= _MAX_RETRIES:
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(url, json=payload)

                # 5xx server error — retry
                if 500 <= resp.status_code < 600:
                    logger.warning(
                        "[gemini] Server error {} (attempt {}/{})",
                        resp.status_code, attempt + 1, _MAX_RETRIES + 1,
                    )
                    if attempt >= _MAX_RETRIES:
                        raise TranslationError(
                            f"Gemini API server error after retries: HTTP {resp.status_code}",
                            user_message="翻譯服務暫時不可用，請稍後再試",
                        )
                    await self._backoff(attempt)
                    attempt += 1
                    continue

                # 429 rate limit
                if resp.status_code == 429:
                    body_json = {}
                    try:
                        body_json = resp.json()
                    except Exception:
                        pass
                    err_msg = body_json.get("error", {}).get("message", "")

                    # Check RPD (daily quota) — don't retry
                    if self._is_daily_quota(body_json):
                        raise TranslationError(
                            f"Gemini daily quota exceeded: {err_msg}",
                            user_message="Gemini API 每日配額已用盡，請明天再試",
                        )

                    logger.warning(
                        "[gemini] Rate limited 429 (attempt {}/{}): {}",
                        attempt + 1, _MAX_RETRIES + 1, err_msg,
                    )
                    if attempt >= _MAX_RETRIES:
                        raise TranslationError(
                            f"Gemini API rate limited after retries: {err_msg}",
                            user_message="翻譯服務請求過於頻繁，請稍後再試",
                        )

                    retry_after = resp.headers.get("retry-after", "")
                    if retry_after.isdigit():
                        await asyncio.sleep(int(retry_after) + 0.1)
                    else:
                        await self._backoff(attempt)
                    attempt += 1
                    continue

                # Other HTTP errors — fail immediately
                if resp.status_code != 200:
                    raise TranslationError(
                        f"Gemini API error: HTTP {resp.status_code} – {resp.text[:300]}",
                        user_message="翻譯服務 API 錯誤",
                    )

                # Success
                try:
                    return resp.json()
                except Exception as exc:
                    raise TranslationError(
                        f"Gemini response is not valid JSON: {resp.text[:200]}",
                        user_message="翻譯服務回傳格式異常",
                    ) from exc

            except TranslationError:
                raise
            except httpx.TimeoutException as exc:
                logger.warning(
                    "[gemini] Timeout {} (attempt {}/{})",
                    type(exc).__name__, attempt + 1, _MAX_RETRIES + 1,
                )
                if attempt >= _MAX_RETRIES:
                    raise TranslationError(
                        f"Gemini API timeout after retries ({self._timeout}s each)",
                        user_message="翻譯服務連線逾時，請稍後再試",
                    ) from exc
                await self._backoff(attempt)
                attempt += 1
            except httpx.HTTPError as exc:
                logger.warning(
                    "[gemini] Network error (attempt {}/{}): {} - {}",
                    attempt + 1, _MAX_RETRIES + 1, type(exc).__name__, exc,
                )
                if attempt >= _MAX_RETRIES:
                    raise TranslationError(
                        f"Gemini API network error: {type(exc).__name__} – {exc}",
                        user_message="翻譯服務網路錯誤",
                    ) from exc
                await self._backoff(attempt)
                attempt += 1

        # Should not reach here
        raise TranslationError("Gemini API failed after exhausting retries")

    @staticmethod
    def _is_daily_quota(body_json: dict) -> bool:
        """Check if 429 error is due to daily quota (RPD) exhaustion."""
        details = body_json.get("error", {}).get("details", [])
        if not isinstance(details, list):
            return False
        for d in details:
            metric = (d.get("quotaMetric") or d.get("metric") or "").lower()
            qid = (d.get("quotaId") or "").lower()
            haystack = f"{metric} {qid}"
            if "perday" in haystack or "_day" in haystack:
                return True
        return False

    @staticmethod
    async def _backoff(attempt: int) -> None:
        wait_ms = min(_MAX_BACKOFF_MS, 500 * (2 ** attempt))
        logger.info("[gemini] Backing off {}ms before retry", wait_ms)
        await asyncio.sleep(wait_ms / 1000)

    # ── Main translation logic ─────────────────────────

    async def _translate_batch(
        self,
        batch: list[str],
        target_lang: str,
    ) -> list[str]:
        """Send one batch to the Gemini API using delimiter protocol."""
        url = f"{_GEMINI_API_BASE}/{self._model}:generateContent?key={self._api_key}"

        # Build system prompt
        system_parts = [_SYSTEM_PROMPT.format(target_lang=target_lang)]
        if len(batch) > 1:
            system_parts.append(
                _MULTI_SEGMENT_RULE.format(
                    count=len(batch),
                    count_minus_1=len(batch) - 1,
                )
            )
        effective_system = "\n\n".join(system_parts)

        # Build user content with delimiter protocol
        if len(batch) > 1:
            # Add sequence markers for multi-segment
            marked = [f"«{i + 1}» {text}" for i, text in enumerate(batch)]
            user_text = _DELIMITER.join(marked)
        else:
            user_text = batch[0]

        payload = {
            "system_instruction": {
                "parts": [{"text": effective_system}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_text}],
                },
            ],
            "generationConfig": {
                "temperature": 0.3,
                "thinkingConfig": {"thinkingBudget": 0},
            },
            "safetySettings": _SAFETY_SETTINGS,
        }

        # ── Call API with retry ────────────────────────
        try:
            data = await self._fetch_with_retry(url, payload)
            text = self._extract_text(data)
        except TranslationError as exc:
            # If the batch was blocked by safety filters and has >1 segments, fallback
            if len(batch) > 1 and ("blocked" in str(exc).lower() or "safety" in str(exc).lower()):
                logger.warning(
                    "[gemini] Batch blocked by safety filter: {}. "
                    "Falling back to per-segment translation to isolate bad segments.",
                    exc
                )
                return await self._per_segment_fallback(batch, target_lang)
            raise

        # ── Validate response ──────────────────────────

        # Log usage
        meta = data.get("usageMetadata", {})
        logger.info(
            "[gemini] Response: inputTokens={}, outputTokens={}, "
            "cachedTokens={}, finishReason={}",
            meta.get("promptTokenCount", 0),
            meta.get("candidatesTokenCount", 0),
            meta.get("cachedContentTokenCount", 0),
            (data.get("candidates") or [{}])[0].get("finishReason", "unknown"),
        )

        # ── Parse delimiter protocol ──────────────────
        if len(batch) == 1:
            # Single segment: return the whole text
            return [text.strip()]

        # Multi-segment: split by delimiter and strip sequence markers
        parts = text.split(_DELIMITER)
        parts = [_SEQ_MARKER_RE.sub("", p).strip() for p in parts]

        if len(parts) != len(batch):
            logger.warning(
                "[gemini] Segment mismatch: expected {}, got {}. "
                "Falling back to per-segment translation.",
                len(batch),
                len(parts),
            )
            return await self._per_segment_fallback(batch, target_lang)

        return parts

    async def _per_segment_fallback(
        self,
        batch: list[str],
        target_lang: str,
    ) -> list[str]:
        """Fallback: translate each block individually when count mismatches or safety blocks."""
        results: list[str] = []
        for i, block in enumerate(batch):
            logger.info("[gemini] Fallback segment {}/{}", i + 1, len(batch))
            try:
                translated = await self._translate_batch([block], target_lang)
                results.extend(translated)
            except TranslationError as exc:
                if "blocked" in str(exc).lower() or "safety" in str(exc).lower():
                    logger.warning(
                        "[gemini] Segment {}/{} completely blocked by safety filters, "
                        "degrading to source-only. Reason: {}", 
                        i + 1, len(batch), exc
                    )
                    results.append(block)
                else:
                    raise
        return results

    @staticmethod
    def _extract_text(data: dict) -> str:
        """Extract text from Gemini response, with proper error handling."""
        # Check if prompt was blocked
        block_reason = (data.get("promptFeedback") or {}).get("blockReason")
        if block_reason:
            raise TranslationError(
                f"Gemini blocked the prompt (blockReason: {block_reason})",
                user_message="翻譯內容被 Gemini 安全過濾器擋下",
            )

        candidates = data.get("candidates") or []
        if not candidates:
            feedback = data.get("promptFeedback", {})
            raise TranslationError(
                f"Gemini returned no candidates. promptFeedback={feedback}",
                user_message="翻譯服務回傳空結果",
            )

        candidate = candidates[0]
        finish_reason = candidate.get("finishReason", "unknown")

        if finish_reason == "SAFETY":
            raise TranslationError(
                "Gemini response blocked by safety filter",
                user_message="翻譯內容被安全過濾器擋下",
            )

        # Extract text
        try:
            text = candidate["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            reason_msgs = {
                "SAFETY": "內容被安全過濾器擋下",
                "RECITATION": "內容與已知作品重複度過高",
                "MAX_TOKENS": "輸出超過上限，請減少每批段落數",
            }
            friendly = reason_msgs.get(
                finish_reason,
                f"Gemini 回傳空內容 (finishReason={finish_reason})",
            )
            raise TranslationError(
                f"Gemini returned empty content: finishReason={finish_reason}",
                user_message=friendly,
            )

        if finish_reason not in ("STOP", "unknown"):
            logger.warning(
                "[gemini] Unusual finishReason: {} (text length={})",
                finish_reason, len(text),
            )

        return text
