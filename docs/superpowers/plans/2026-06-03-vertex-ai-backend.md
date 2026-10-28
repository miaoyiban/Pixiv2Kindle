# Vertex AI 雙後端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 `GeminiTranslationProvider` 支援 Vertex AI 後端（OAuth 認證、抵免額可抵），並保留現有 Gemini API key 後端當退路，透過 `GEMINI_BACKEND` 環境變數切換。

**Architecture:** Gemini API 與 Vertex AI 共用同一套 `generateContent` request schema，因此只在「端點 URL」與「認證 header」兩處分流；核心翻譯邏輯不動。新增 `VertexTokenProvider` 管理 OAuth token 的快取與過期刷新。

**Tech Stack:** Python 3.9、httpx、google-auth（ADC）、pydantic-settings、pytest / pytest-asyncio。

---

## File Structure

- `requirements.txt` — 顯式新增 `google-auth`。
- `packages/core/config.py` — 新增 3 個設定欄位。
- `apps/api_server/dependencies.py` — 把新設定傳給 provider。
- `packages/core/providers/translation/gemini.py` — 新增 `VertexTokenProvider` 類別、`_build_url()`、`__init__` 參數、`_translate_batch` 與 `_fetch_with_retry` 的 header 分流。
- `tests/unit/test_gemini_provider.py` — 新測試檔（token 管理、URL 組裝、header 分流）。
- `tests/unit/test_config.py` — 新增（或沿用）設定預設值測試。

備註：本專案 `pyproject.toml` 設定 `asyncio_mode = "auto"`，但既有測試仍標 `@pytest.mark.asyncio`，本計畫沿用同風格。

---

### Task 1: 設定欄位、依賴接線與套件宣告

**Files:**
- Modify: `requirements.txt`
- Modify: `packages/core/config.py:52`（`fail_on_translation_error` 之後）
- Modify: `apps/api_server/dependencies.py:74-78`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: 寫失敗測試（設定預設值）**

建立 `tests/unit/test_config.py`：

```python
"""Tests for packages.core.config translation backend settings."""

from __future__ import annotations

from packages.core.config import Settings


def test_translation_backend_defaults():
    # _env_file=None 隔離本機 .env，確保測的是程式碼預設值
    s = Settings(_env_file=None)
    assert s.gemini_backend == "api_key"
    assert s.vertex_project_id == ""
    assert s.vertex_location == "global"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/unit/test_config.py -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'gemini_backend'`

- [ ] **Step 3: 新增設定欄位**

在 `packages/core/config.py` 第 52 行 `fail_on_translation_error: bool = False` 之後插入：

```python

    # ── Vertex AI backend ──────────────────────────────
    gemini_backend: str = "api_key"  # "api_key" | "vertex"
    vertex_project_id: str = ""        # 空字串 = 自動偵測
    vertex_location: str = "global"
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/unit/test_config.py -v`
Expected: PASS

- [ ] **Step 5: 接線到 provider**

在 `apps/api_server/dependencies.py`，把現有的：

```python
        return GeminiTranslationProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            max_chars_per_batch=settings.gemini_max_chars_per_batch,
        )
```

改為：

```python
        return GeminiTranslationProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            max_chars_per_batch=settings.gemini_max_chars_per_batch,
            backend=settings.gemini_backend,
            vertex_project_id=settings.vertex_project_id,
            vertex_location=settings.vertex_location,
        )
```

> 註：此時 `GeminiTranslationProvider` 尚未接受這些參數，要等 Task 3 才會實作；先接線好，Task 3 完成後即可用。本步驟不需單獨測試。

- [ ] **Step 6: 顯式宣告 google-auth**

在 `requirements.txt` 中 `google-cloud-tasks>=2.16.0` 那一行下方新增一行：

```
google-auth>=2.0.0
```

- [ ] **Step 7: Commit**

```bash
git add requirements.txt packages/core/config.py apps/api_server/dependencies.py tests/unit/test_config.py
git commit -m "feat(config): 新增 Vertex AI 後端設定欄位與依賴接線

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: VertexTokenProvider（OAuth token 快取與刷新）

**Files:**
- Modify: `packages/core/providers/translation/gemini.py`（新增 import 與類別）
- Test: `tests/unit/test_gemini_provider.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/unit/test_gemini_provider.py`：

```python
"""Tests for the Gemini/Vertex translation provider."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from packages.core.providers.translation.gemini import VertexTokenProvider


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
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/unit/test_gemini_provider.py -v`
Expected: FAIL — `ImportError: cannot import name 'VertexTokenProvider'`

- [ ] **Step 3: 實作 VertexTokenProvider**

在 `packages/core/providers/translation/gemini.py`，於檔案頂部 import 區（`import httpx` 附近）新增：

```python
import google.auth
import google.auth.transport.requests
```

並在 `_MAX_RETRIES = 3` 常數之後、`class GeminiTranslationProvider` 之前，新增類別：

```python
class VertexTokenProvider:
    """Manage Cloud OAuth credentials for Vertex AI calls.

    Caches Application Default Credentials and refreshes the access token
    only when it has expired (~1h). An asyncio lock makes it safe for the
    concurrent batches to share one credentials object without duplicate
    refreshes.
    """

    _SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]

    def __init__(self, *, project_id: str = "") -> None:
        self._explicit_project = project_id
        self._detected_project: str | None = None
        self._creds = None
        self._lock = asyncio.Lock()

    async def token(self) -> str:
        """Return a valid access token, refreshing on demand."""
        async with self._lock:
            if self._creds is None:
                self._creds, self._detected_project = await asyncio.to_thread(
                    google.auth.default, scopes=self._SCOPES
                )
            if not self._creds.valid:
                await asyncio.to_thread(
                    self._creds.refresh,
                    google.auth.transport.requests.Request(),
                )
            return self._creds.token

    @property
    def project_id(self) -> str:
        """Project ID: explicit override wins, else auto-detected.

        Auto-detection happens during the first ``token()`` call, so call
        ``token()`` before reading this when relying on detection.
        """
        if self._explicit_project:
            return self._explicit_project
        if self._detected_project:
            return self._detected_project
        raise TranslationError(
            "Vertex project ID not set and could not be auto-detected",
            user_message="Vertex AI 專案 ID 無法自動偵測，請設定 VERTEX_PROJECT_ID",
        )
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/unit/test_gemini_provider.py -v`
Expected: PASS（4 個 token 測試全綠）

- [ ] **Step 5: Commit**

```bash
git add packages/core/providers/translation/gemini.py tests/unit/test_gemini_provider.py
git commit -m "feat(gemini): 新增 VertexTokenProvider 管理 OAuth token 快取與刷新

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Provider 後端參數與 _build_url 分流

**Files:**
- Modify: `packages/core/providers/translation/gemini.py:101-116`（`__init__`）
- Modify: `packages/core/providers/translation/gemini.py`（新增 `_build_url` 方法與 Vertex host 常數）
- Test: `tests/unit/test_gemini_provider.py`

- [ ] **Step 1: 寫失敗測試（URL 組裝）**

在 `tests/unit/test_gemini_provider.py` 末尾追加：

```python
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
```

並把檔案頂部既有的 import 行補上 `GeminiTranslationProvider`：

```python
from packages.core.providers.translation.gemini import (
    GeminiTranslationProvider,
    VertexTokenProvider,
)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/unit/test_gemini_provider.py -k build_url -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'backend'`

- [ ] **Step 3: 擴充 __init__ 並新增 _build_url**

把 `gemini.py` 的 `__init__`（第 101-116 行）改為：

```python
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gemini-2.5-flash",
        max_blocks_per_request: int = 20,
        max_chars_per_batch: int = 3500,
        timeout_seconds: float = 180,
        max_concurrent_batches: int = 3,
        backend: str = "api_key",
        vertex_project_id: str = "",
        vertex_location: str = "global",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._max_blocks = max_blocks_per_request
        self._max_chars = max_chars_per_batch
        self._timeout = timeout_seconds
        self._max_concurrent = max_concurrent_batches
        self._backend = backend
        self._vertex_location = vertex_location
        self._token_provider = (
            VertexTokenProvider(project_id=vertex_project_id)
            if backend == "vertex"
            else None
        )
```

在 `_pack_batches` 方法之後（`# ── HTTP with retry ──` 區段之前）新增：

```python
    # ── Endpoint URL ───────────────────────────────────

    def _build_url(self) -> str:
        """Build the generateContent URL for the active backend."""
        if self._backend == "vertex":
            project = self._token_provider.project_id
            loc = self._vertex_location
            host = (
                "https://aiplatform.googleapis.com"
                if loc == "global"
                else f"https://{loc}-aiplatform.googleapis.com"
            )
            return (
                f"{host}/v1/projects/{project}/locations/{loc}"
                f"/publishers/google/models/{self._model}:generateContent"
            )
        return f"{_GEMINI_API_BASE}/{self._model}:generateContent?key={self._api_key}"
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/unit/test_gemini_provider.py -k build_url -v`
Expected: PASS（3 個 URL 測試全綠）

- [ ] **Step 5: Commit**

```bash
git add packages/core/providers/translation/gemini.py tests/unit/test_gemini_provider.py
git commit -m "feat(gemini): 後端參數與 _build_url 分流（api_key / vertex）

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: 請求 header 分流（注入 Bearer token）

**Files:**
- Modify: `packages/core/providers/translation/gemini.py:241-252`（`_fetch_with_retry` 簽名與 POST）
- Modify: `packages/core/providers/translation/gemini.py:377,421`（`_translate_batch` 內 URL/header）
- Test: `tests/unit/test_gemini_provider.py`

- [ ] **Step 1: 寫失敗測試（header 分流）**

在 `tests/unit/test_gemini_provider.py` 末尾追加：

```python
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/python -m pytest tests/unit/test_gemini_provider.py -k batch -v`
Expected: FAIL — `_translate_batch` 仍把舊 URL 寫死且 `_fetch_with_retry` 只收 2 個參數，會出現 `TypeError`（fake_fetch 收到非預期參數）或 AssertionError。

- [ ] **Step 3: 改 _fetch_with_retry 簽名接受 headers**

在 `gemini.py` 把 `_fetch_with_retry` 的定義（第 241-245 行）改為：

```python
    async def _fetch_with_retry(
        self,
        url: str,
        payload: dict,
        headers: dict,
    ) -> dict:
        """POST to the active backend with retry on 429 / 5xx / timeout."""
```

並把該方法內的 POST 呼叫（原第 252 行）：

```python
                    resp = await client.post(url, json=payload)
```

改為：

```python
                    resp = await client.post(url, json=payload, headers=headers)
```

- [ ] **Step 4: 改 _translate_batch 組 URL 與 header**

在 `_translate_batch` 中，把原第 377 行：

```python
        url = f"{_GEMINI_API_BASE}/{self._model}:generateContent?key={self._api_key}"
```

改為（先取 token，使 Vertex 的 project 自動偵測完成，再組 URL）：

```python
        headers: dict[str, str] = {}
        if self._backend == "vertex":
            token = await self._token_provider.token()
            headers["Authorization"] = f"Bearer {token}"
        url = self._build_url()
```

再把該方法稍後的呼叫（原第 421 行）：

```python
            data = await self._fetch_with_retry(url, payload)
```

改為：

```python
            data = await self._fetch_with_retry(url, payload, headers)
```

- [ ] **Step 5: 跑測試確認通過**

Run: `.venv/bin/python -m pytest tests/unit/test_gemini_provider.py -v`
Expected: PASS（全部 token / URL / header 測試皆綠）

- [ ] **Step 6: 跑全套測試確認沒打壞既有行為**

Run: `.venv/bin/python -m pytest tests/unit -v`
Expected: PASS（含既有 `test_translation_service` 等）

- [ ] **Step 7: Commit**

```bash
git add packages/core/providers/translation/gemini.py tests/unit/test_gemini_provider.py
git commit -m "feat(gemini): 請求 header 分流，Vertex 後端注入 Bearer token

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## 部署前置作業（GCP，程式之外，由使用者執行）

實作與測試完成後、要實際切換時：

1. 啟用 Vertex AI API：
   `gcloud services enable aiplatform.googleapis.com --project=<PROJECT_ID>`
2. 授權 Cloud Run service account `<PROJECT_NUMBER>-compute@developer.gserviceaccount.com` 取得 `roles/aiplatform.user`。
3. 部署時設環境變數 `GEMINI_BACKEND=vertex`。
4. 本機測試需先 `gcloud auth application-default login`。
