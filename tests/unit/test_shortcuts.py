"""Unit tests for the /api/shortcuts/pixiv-to-kindle endpoint.

Spec reference: §9.4 (M5).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.api_server.main import create_app
from packages.core.domain.value_objects import EnqueueResponse


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def valid_key() -> str:
    return "test-shortcut-api-key-abc123"


@pytest.fixture()
def app(valid_key: str):
    """Create a test app with a real settings override."""
    application = create_app()

    # Override settings to inject a known API key.
    from apps.api_server.dependencies import get_settings
    from packages.core.config import Settings

    mock_settings = MagicMock(spec=Settings)
    mock_settings.shortcut_api_key = valid_key
    mock_settings.app_name = "pixiv2kindle"
    mock_settings.app_env = "dev"
    mock_settings.log_level = "INFO"
    mock_settings.queue_backend = "local"

    application.dependency_overrides[get_settings] = lambda: mock_settings
    return application


@pytest.fixture()
def mock_queue():
    """A mock task queue that accepts enqueue calls."""
    q = AsyncMock()
    q.enqueue_send_novel = AsyncMock(return_value=None)
    return q


@pytest.fixture()
def client(app, mock_queue):
    from apps.api_server.dependencies import get_task_queue
    app.dependency_overrides[get_task_queue] = lambda: mock_queue
    return TestClient(app, raise_server_exceptions=True)


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestShortcutEndpointAuth:
    def test_valid_key_accepts_request(self, client, mock_queue, valid_key):
        resp = client.post(
            "/api/shortcuts/pixiv-to-kindle",
            headers={"X-API-Key": valid_key},
            json={"novel_input": "12345678"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"accepted": True, "queued": True}
        mock_queue.enqueue_send_novel.assert_awaited_once()

    def test_wrong_key_returns_403(self, client):
        resp = client.post(
            "/api/shortcuts/pixiv-to-kindle",
            headers={"X-API-Key": "wrong-key"},
            json={"novel_input": "12345678"},
        )
        assert resp.status_code == 403

    def test_missing_key_returns_403(self, client):
        resp = client.post(
            "/api/shortcuts/pixiv-to-kindle",
            json={"novel_input": "12345678"},
        )
        assert resp.status_code == 403

    def test_unconfigured_api_key_returns_500(self, app, mock_queue):
        from apps.api_server.dependencies import get_settings, get_task_queue
        from packages.core.config import Settings

        bad_settings = MagicMock(spec=Settings)
        bad_settings.shortcut_api_key = ""  # not configured
        app.dependency_overrides[get_settings] = lambda: bad_settings
        app.dependency_overrides[get_task_queue] = lambda: mock_queue

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/shortcuts/pixiv-to-kindle",
            headers={"X-API-Key": "any-key"},
            json={"novel_input": "12345678"},
        )
        assert resp.status_code == 500


class TestShortcutEndpointPayload:
    def test_missing_novel_input_returns_422(self, client, valid_key):
        resp = client.post(
            "/api/shortcuts/pixiv-to-kindle",
            headers={"X-API-Key": valid_key},
            json={},
        )
        assert resp.status_code == 422

    def test_default_translate_is_false(self, client, mock_queue, valid_key):
        client.post(
            "/api/shortcuts/pixiv-to-kindle",
            headers={"X-API-Key": valid_key},
            json={"novel_input": "12345678"},
        )
        call_args = mock_queue.enqueue_send_novel.call_args
        payload = call_args.args[0]
        assert payload.command.translate is False
        assert payload.command.target_lang == "zh-TW"

    def test_translate_flag_forwarded(self, client, mock_queue, valid_key):
        client.post(
            "/api/shortcuts/pixiv-to-kindle",
            headers={"X-API-Key": valid_key},
            json={"novel_input": "99999999", "translate": True, "target_lang": "en"},
        )
        call_args = mock_queue.enqueue_send_novel.call_args
        payload = call_args.args[0]
        assert payload.command.novel_input == "99999999"
        assert payload.command.translate is True
        assert payload.command.target_lang == "en"

    def test_task_payload_has_no_discord_context(self, client, mock_queue, valid_key):
        """Ensure the enqueued payload has no Discord context (M5 decoupling)."""
        client.post(
            "/api/shortcuts/pixiv-to-kindle",
            headers={"X-API-Key": valid_key},
            json={"novel_input": "12345678"},
        )
        call_args = mock_queue.enqueue_send_novel.call_args
        payload = call_args.args[0]
        assert payload.discord is None
        assert payload.user is None

    def test_task_payload_has_no_deadline(self, client, mock_queue, valid_key):
        """Deadline should be 0 (no Discord follow-up constraint)."""
        client.post(
            "/api/shortcuts/pixiv-to-kindle",
            headers={"X-API-Key": valid_key},
            json={"novel_input": "12345678"},
        )
        call_args = mock_queue.enqueue_send_novel.call_args
        payload = call_args.args[0]
        assert payload.deadline.followup_deadline_epoch_ms == 0

    def test_pixiv_url_accepted_as_novel_input(self, client, mock_queue, valid_key):
        url = "https://www.pixiv.net/novel/show.php?id=12345678"
        client.post(
            "/api/shortcuts/pixiv-to-kindle",
            headers={"X-API-Key": valid_key},
            json={"novel_input": url},
        )
        call_args = mock_queue.enqueue_send_novel.call_args
        payload = call_args.args[0]
        assert payload.command.novel_input == url
