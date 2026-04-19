"""Send EPUB files to a Kindle email address via SMTP.

Uses stdlib ``smtplib`` wrapped with ``asyncio.to_thread()`` so the
caller can ``await`` it without blocking the event loop.

Spec references: §14.1 – §14.4.
"""

from __future__ import annotations

import asyncio
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from loguru import logger

from packages.core.exceptions import KindleDeliveryError


class SmtpKindleSender:
    """Deliver EPUB attachments to a Kindle email via SMTP."""

    def __init__(
        self,
        *,
        kindle_email: str,
        smtp_host: str,
        smtp_port: int,
        smtp_username: str,
        smtp_password: str,
        smtp_from: str,
    ) -> None:
        self._kindle_email = kindle_email
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._smtp_username = smtp_username
        self._smtp_password = smtp_password
        self._smtp_from = smtp_from

    # ── Public API ─────────────────────────────────────

    async def send(self, file_path: str) -> None:
        """Send the EPUB at *file_path* to the configured Kindle email.

        Runs the blocking SMTP transaction in a thread.
        """
        await asyncio.to_thread(self._send_sync, file_path)

    # ── Internal ───────────────────────────────────────

    def _send_sync(self, file_path: str) -> None:
        path = Path(file_path)
        if not path.is_file():
            raise KindleDeliveryError(f"EPUB file not found: {file_path}")

        msg = self._build_message(path)

        try:
            logger.info("Connecting to SMTP {}:{}", self._smtp_host, self._smtp_port)
            with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(self._smtp_username, self._smtp_password)
                server.send_message(msg)
            logger.info("EPUB sent to {}", self._kindle_email)
        except smtplib.SMTPException as exc:
            raise KindleDeliveryError(
                f"SMTP error: {exc}",
                user_message="Kindle 寄送失敗，SMTP 連線或認證錯誤",
            ) from exc
        except Exception as exc:
            raise KindleDeliveryError(
                f"Unexpected send error: {exc}",
            ) from exc

    def _build_message(self, path: Path) -> MIMEMultipart:
        msg = MIMEMultipart()
        msg["From"] = self._smtp_from
        msg["To"] = self._kindle_email
        msg["Subject"] = "convert"  # Kindle ignores subject but needs one

        msg.attach(MIMEText("", "plain", "utf-8"))

        part = MIMEBase("application", "epub+zip")
        part.set_payload(path.read_bytes())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{path.name}"',
        )
        msg.attach(part)
        return msg
