"""Tests for packages.core.config translation backend settings."""

from __future__ import annotations

from packages.core.config import Settings


def test_translation_backend_defaults():
    # _env_file=None 隔離本機 .env，確保測的是程式碼預設值
    s = Settings(_env_file=None)
    assert s.gemini_backend == "api_key"
    assert s.vertex_project_id == ""
    assert s.vertex_location == "global"
