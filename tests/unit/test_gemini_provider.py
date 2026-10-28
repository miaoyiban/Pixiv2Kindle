"""Tests for the Gemini/Vertex translation provider."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from packages.core.exceptions import TranslationError
from packages.core.providers.translation.gemini import (
    GeminiTranslationProvider,
    VertexTokenProvider,
)


class FakeCreds:
    """Fake google.auth credentials: tracks refresh calls, toggles validity."""

    def __init__(self) -> None:
        self.token = "tok-0"
        self.valid = False
        self.refresh_calls = 0

    def refresh(self, request) -> None:  # noqa: ANN001 - matches google API
        self.refresh_calls += 1
        self.valid = True
        self.token = f"tok-{self.refresh_calls}"


@pytest.mark.asyncio
async def test_token_refreshes_on_first_call():
    creds = FakeCreds()
    with patch("google.auth.default", return_value=(creds, "auto-proj")):
        provider = VertexTokenProvider()
        token = await provider.token()
    assert token == "tok-1"
    assert creds.refresh_calls == 1
    assert provider.project_id == "auto-proj"


@pytest.mark.asyncio
async def test_token_not_refreshed_when_valid():
    creds = FakeCreds()
    with patch("google.auth.default", return_value=(creds, "auto-proj")):
        provider = VertexTokenProvider()
        await provider.token()   # refresh -> valid
        await provider.token()   # still valid, must NOT refresh again
    assert creds.refresh_calls == 1


@pytest.mark.asyncio
async def test_token_refreshed_when_expired():
    creds = FakeCreds()
    with patch("google.auth.default", return_value=(creds, "auto-proj")):
        provider = VertexTokenProvider()
        await provider.token()   # refresh 1
        creds.valid = False      # simulate 1h expiry
        token = await provider.token()  # refresh 2
    assert creds.refresh_calls == 2
    assert token == "tok-2"


@pytest.mark.asyncio
async def test_explicit_project_overrides_detected():
    creds = FakeCreds()
    with patch("google.auth.default", return_value=(creds, "auto-proj")):
        provider = VertexTokenProvider(project_id="explicit-proj")
        await provider.token()
    assert provider.project_id == "explicit-proj"


@pytest.mark.asyncio
async def test_project_id_raises_when_not_detected():
    creds = FakeCreds()
    with patch("google.auth.default", return_value=(creds, None)):
        provider = VertexTokenProvider()
        await provider.token()
    with pytest.raises(TranslationError):
        _ = provider.project_id


def test_build_url_api_key():
    provider = GeminiTranslationProvider(
        api_key="KEY", model="gemini-x", backend="api_key"
    )
    assert provider._build_url() == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-x:generateContent?key=KEY"
    )


def test_build_url_vertex_global():
    provider = GeminiTranslationProvider(
        api_key="", model="gemini-x", backend="vertex",
        vertex_project_id="proj-1", vertex_location="global",
    )
    assert provider._build_url() == (
        "https://aiplatform.googleapis.com/v1/projects/proj-1/locations/global"
        "/publishers/google/models/gemini-x:generateContent"
    )


def test_build_url_vertex_region():
    provider = GeminiTranslationProvider(
        api_key="", model="gemini-x", backend="vertex",
        vertex_project_id="proj-1", vertex_location="us-central1",
    )
    assert provider._build_url() == (
        "https://us-central1-aiplatform.googleapis.com/v1/projects/proj-1"
        "/locations/us-central1/publishers/google/models/"
        "gemini-x:generateContent"
    )


def test_api_key_backend_has_no_token_provider():
    provider = GeminiTranslationProvider(api_key="KEY", backend="api_key")
    assert provider._token_provider is None


def test_unknown_backend_raises():
    with pytest.raises(ValueError):
        GeminiTranslationProvider(api_key="KEY", backend="bogus")


def _canned_response(text: str) -> dict:
    return {
        "candidates": [
            {"finishReason": "STOP", "content": {"parts": [{"text": text}]}}
        ],
        "usageMetadata": {},
    }


@pytest.mark.asyncio
async def test_vertex_batch_sends_bearer_header():
    creds = FakeCreds()
    captured: dict = {}

    async def fake_fetch(url, payload, headers):
        captured["url"] = url
        captured["headers"] = headers
        return _canned_response("譯文")

    with patch("google.auth.default", return_value=(creds, "auto-proj")):
        provider = GeminiTranslationProvider(
            api_key="", model="gemini-x", backend="vertex",
            vertex_project_id="proj-1",
        )
        provider._fetch_with_retry = fake_fetch  # type: ignore[assignment]
        result = await provider._translate_batch(["こんにちは"], "繁體中文")

    assert result == ["譯文"]
    assert captured["headers"]["Authorization"] == "Bearer tok-1"
    assert "aiplatform.googleapis.com" in captured["url"]


@pytest.mark.asyncio
async def test_api_key_batch_has_no_auth_header():
    captured: dict = {}

    async def fake_fetch(url, payload, headers):
        captured["url"] = url
        captured["headers"] = headers
        return _canned_response("out")

    provider = GeminiTranslationProvider(
        api_key="KEY", model="gemini-x", backend="api_key"
    )
    provider._fetch_with_retry = fake_fetch  # type: ignore[assignment]
    result = await provider._translate_batch(["hi"], "繁體中文")

    assert result == ["out"]
    assert "Authorization" not in captured["headers"]
    assert "key=KEY" in captured["url"]


@pytest.mark.asyncio
async def test_token_force_refresh_refreshes_valid_token():
    creds = FakeCreds()
    with patch("google.auth.default", return_value=(creds, "auto-proj")):
        provider = VertexTokenProvider()
        await provider.token()                       # refresh 1, now valid
        token = await provider.token(force_refresh=True)  # forced refresh 2
    assert creds.refresh_calls == 2
    assert token == "tok-2"


@pytest.mark.asyncio
async def test_vertex_401_refreshes_token_and_retries(monkeypatch):
    import httpx
    from packages.core.providers.translation import gemini as gemini_mod

    creds = FakeCreds()
    calls = {"n": 0}
    seen_auth: list[str] = []

    class FakeResp:
        def __init__(self, status_code, json_body):
            self.status_code = status_code
            self._json = json_body
            self.text = ""
            self.headers = {}

        def json(self):
            return self._json

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            calls["n"] += 1
            seen_auth.append(headers.get("Authorization", ""))
            if calls["n"] == 1:
                return FakeResp(401, {"error": {"message": "token expired"}})
            return FakeResp(200, _canned_response("譯文"))

    monkeypatch.setattr(gemini_mod.httpx, "AsyncClient", FakeClient)
    # make backoff instant
    async def _no_backoff(attempt):
        return None
    monkeypatch.setattr(GeminiTranslationProvider, "_backoff", staticmethod(_no_backoff))

    with patch("google.auth.default", return_value=(creds, "auto-proj")):
        provider = GeminiTranslationProvider(
            api_key="", model="gemini-x", backend="vertex",
            vertex_project_id="proj-1",
        )
        result = await provider._translate_batch(["こんにちは"], "繁體中文")

    assert result == ["譯文"]
    assert calls["n"] == 2                      # retried once after 401
    assert seen_auth[0] == "Bearer tok-1"       # first attempt used initial token
    assert seen_auth[1] == "Bearer tok-2"       # retry used force-refreshed token


@pytest.mark.asyncio
async def test_concurrent_token_calls_refresh_once():
    import asyncio

    creds = FakeCreds()
    default_calls = {"n": 0}

    def fake_default(scopes=None):
        default_calls["n"] += 1
        return (creds, "auto-proj")

    with patch("google.auth.default", side_effect=fake_default):
        provider = VertexTokenProvider()
        tokens = await asyncio.gather(*[provider.token() for _ in range(10)])

    assert default_calls["n"] == 1          # creds loaded once
    assert creds.refresh_calls == 1         # refreshed once despite 10 callers
    assert all(t == "tok-1" for t in tokens)
