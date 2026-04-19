"""Pixiv API client wrapping *pixivpy3*.

All methods are **synchronous** because pixivpy3 is built on
``requests``.  The service layer wraps calls with
``asyncio.to_thread()`` (spec §11.2).

Authentication uses a refresh token (spec §11.4).
"""

from __future__ import annotations

from typing import Any

from pixivpy3 import AppPixivAPI

from packages.core.domain.models import PixivNovel
from packages.core.exceptions import PixivAuthError, PixivFetchError


class PixivpyClient:
    """Thin wrapper around :class:`AppPixivAPI` for novel access."""

    def __init__(self, refresh_token: str) -> None:
        self._refresh_token = refresh_token
        self._api = AppPixivAPI()
        self._authenticated = False

    # ── Authentication ─────────────────────────────────

    def _ensure_auth(self) -> None:
        """Authenticate lazily on first use."""
        if self._authenticated:
            return
        try:
            self._api.auth(refresh_token=self._refresh_token)
            self._authenticated = True
        except Exception as exc:
            raise PixivAuthError(
                f"pixivpy3 auth failed: {exc}",
                user_message="pixiv 認證失效，需更新 refresh token",
            ) from exc

    # ── Public helpers ─────────────────────────────────

    def fetch_novel_detail(self, novel_id: int) -> dict[str, Any]:
        """Return the raw detail dict for *novel_id*."""
        self._ensure_auth()
        result = self._api.novel_detail(novel_id)

        if "error" in result:
            msg = result["error"].get("user_message", str(result["error"]))
            raise PixivFetchError(
                f"novel_detail error: {msg}",
                user_message=f"無法取得小說 {novel_id} 的詳細資料",
            )

        novel = result.get("novel")
        if novel is None:
            raise PixivFetchError(
                f"novel_detail returned no 'novel' key for {novel_id}",
                user_message=f"找不到小說 {novel_id}",
            )
        return novel

    def fetch_novel_text(self, novel_id: int) -> str:
        """Return the full text body of *novel_id*."""
        self._ensure_auth()
        result = self._api.novel_text(novel_id)

        if "error" in result:
            msg = result["error"].get("user_message", str(result["error"]))
            raise PixivFetchError(
                f"novel_text error: {msg}",
                user_message=f"無法取得小說 {novel_id} 的內容",
            )

        text = result.get("novel_text")
        if not text:
            raise PixivFetchError(
                f"novel_text returned empty body for {novel_id}",
                user_message=f"小說 {novel_id} 的內容為空",
            )
        return text

    def build_novel(self, novel_id: int) -> PixivNovel:
        """Fetch detail + text and assemble a :class:`PixivNovel`.

        This is the main convenience method called (via thread) from
        the async service layer.
        """
        detail = self.fetch_novel_detail(novel_id)
        text = self.fetch_novel_text(novel_id)

        series = detail.get("series") or {}

        return PixivNovel(
            novel_id=novel_id,
            title=detail.get("title", ""),
            author_name=detail.get("user", {}).get("name", ""),
            caption=detail.get("caption"),
            text=text,
            tags=[t.get("name", "") for t in detail.get("tags", [])],
            series_id=series.get("id"),
            series_title=series.get("title"),
        )
