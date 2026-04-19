"""File-system helpers for temporary EPUB files."""

from __future__ import annotations

import os
from pathlib import Path

from packages.core.exceptions import AttachmentTooLargeError


def ensure_file_size(file_path: str, *, max_bytes: int) -> None:
    """Raise if *file_path* exceeds *max_bytes*.

    Parameters
    ----------
    file_path:
        Absolute or relative path to the generated EPUB.
    max_bytes:
        Upper bound in bytes (spec default: 50 MB for Kindle).

    Raises
    ------
    AttachmentTooLargeError
        When the file is too large for Kindle email delivery.
    """
    size = os.path.getsize(file_path)
    if size > max_bytes:
        mb = size / (1024 * 1024)
        raise AttachmentTooLargeError(
            f"EPUB is {mb:.1f} MB, exceeds {max_bytes / (1024 * 1024):.0f} MB limit",
            user_message=f"EPUB 檔案 {mb:.1f} MB 超過 Kindle 附件上限，無法寄送",
        )


def ensure_temp_dir(temp_dir: str) -> Path:
    """Create *temp_dir* if it does not exist and return it as a Path."""
    path = Path(temp_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path
