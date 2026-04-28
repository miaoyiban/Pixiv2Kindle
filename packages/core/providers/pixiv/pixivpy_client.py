"""Pixiv API client wrapping *pixivpy3*.

All methods are **synchronous** because pixivpy3 is built on
``requests``.  The service layer wraps calls with
``asyncio.to_thread()`` (spec §11.2).

Authentication uses a refresh token (spec §11.4).
"""

from __future__ import annotations

from typing import Any

from loguru import logger
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
        self._do_auth()

    def _do_auth(self) -> None:
        """Perform the actual auth call."""
        try:
            self._api.auth(refresh_token=self._refresh_token)
            self._authenticated = True
            logger.info("[pixiv] Auth succeeded")
        except Exception as exc:
            self._authenticated = False
            raise PixivAuthError(
                f"pixivpy3 auth failed: {exc}",
                user_message="pixiv 認證失效，需更新 refresh token",
            ) from exc

    def _force_reauth(self) -> None:
        """Reset auth state and re-authenticate.

        Called when an API call fails — the access token may have
        expired while the Cloud Run instance stayed warm.
        """
        logger.info("[pixiv] Forcing re-auth (access token may have expired)")
        self._authenticated = False
        self._do_auth()

    # ── Public helpers ─────────────────────────────────

    def fetch_novel_detail(self, novel_id: int) -> dict[str, Any]:
        """Return the raw detail dict for *novel_id*.

        On first failure, re-authenticates and retries once (handles
        expired access tokens on long-lived Cloud Run instances).
        """
        self._ensure_auth()
        result = self._api.novel_detail(novel_id)

        if "error" in result:
            # Log the full raw error for debugging.
            logger.warning(
                "[pixiv] novel_detail({}) returned error on first try: {}",
                novel_id,
                result["error"],
            )
            # Retry once after re-auth.
            self._force_reauth()
            result = self._api.novel_detail(novel_id)

            if "error" in result:
                logger.error(
                    "[pixiv] novel_detail({}) still failed after re-auth: {}",
                    novel_id,
                    result["error"],
                )
                raw_error = result["error"]
                msg = (
                    raw_error.get("user_message")
                    or raw_error.get("message")
                    or str(raw_error)
                )
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
        """Return the full text body of *novel_id*.

        On first failure, re-authenticates and retries once.
        """
        self._ensure_auth()
        result = self._api.novel_text(novel_id)

        if "error" in result:
            logger.warning(
                "[pixiv] novel_text({}) returned error on first try: {}",
                novel_id,
                result["error"],
            )
            self._force_reauth()
            result = self._api.novel_text(novel_id)

            if "error" in result:
                logger.error(
                    "[pixiv] novel_text({}) still failed after re-auth: {}",
                    novel_id,
                    result["error"],
                )
                raw_error = result["error"]
                msg = (
                    raw_error.get("user_message")
                    or raw_error.get("message")
                    or str(raw_error)
                )
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
