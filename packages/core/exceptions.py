"""Custom exception hierarchy for the application.

Every exception that leaves the core layer should be one of these.
They map 1-to-1 with the error types listed in spec §20.1.
"""

from __future__ import annotations


class Pixiv2KindleError(Exception):
    """Base for all domain errors."""

    user_message: str = "處理過程中發生錯誤"

    def __init__(self, message: str | None = None, *, user_message: str | None = None):
        super().__init__(message or self.user_message)
        if user_message is not None:
            self.user_message = user_message


class InvalidInputError(Pixiv2KindleError):
    """The novel input could not be parsed into a valid ID or URL."""

    user_message = "無法解析 pixiv 連結或 ID"


class UnauthorizedUserError(Pixiv2KindleError):
    """The Discord user is not in the allow-list."""

    user_message = "你沒有使用此指令的權限"


class PixivAuthError(Pixiv2KindleError):
    """Pixiv API authentication failed (e.g. expired refresh token)."""

    user_message = "pixiv 認證失效，需更新 refresh token"


class PixivFetchError(Pixiv2KindleError):
    """Failed to fetch novel data from Pixiv."""

    user_message = "無法從 pixiv 取得小說資料"


class TranslationError(Pixiv2KindleError):
    """Translation provider returned an error."""

    user_message = "翻譯服務發生錯誤"


class TimeBudgetExceededError(Pixiv2KindleError):
    """The task cannot complete within the Discord follow-up deadline."""

    user_message = "內容過長，處理時間可能超過可通知時限"


class EpubBuildError(Pixiv2KindleError):
    """EPUB generation failed."""

    user_message = "EPUB 生成失敗"


class AttachmentTooLargeError(Pixiv2KindleError):
    """Generated EPUB exceeds the Kindle email attachment limit."""

    user_message = "EPUB 檔案過大，無法寄送到 Kindle"


class KindleDeliveryError(Pixiv2KindleError):
    """SMTP delivery to Kindle email failed."""

    user_message = "Kindle 寄送失敗"


class DiscordNotifyError(Pixiv2KindleError):
    """Failed to send follow-up message to Discord."""

    user_message = "無法回覆 Discord 訊息"
