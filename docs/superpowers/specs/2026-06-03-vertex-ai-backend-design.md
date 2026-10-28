# Vertex AI 雙後端設計

日期：2026-06-03
狀態：已核可，待實作

## 背景與動機

GCP 抵免額（credits）**不能抵 Gemini API（Generative Language API / Google AI Studio）**，但**可以抵 Vertex AI**。
為了讓翻譯成本由抵免額吸收，需把 `GeminiTranslationProvider` 從 Gemini API 端點搬到 Vertex AI 端點。

關鍵前提：Gemini API 與 Vertex AI 共用同一套 `generateContent` request schema
（`contents` / `system_instruction` / `generationConfig` / `safetySettings` 完全相同），
因此既有的 delimiter 協定、retry、per-segment fallback、`_extract_text` 解析邏輯**全部沿用，不需更動**。
真正要改的只有兩件事：**端點 URL** 與 **驗證方式（API key → OAuth Bearer）**。

## 決策摘要

| 項目 | 決定 |
|------|------|
| 後端策略 | 雙後端可切換（保留 API key 路徑當退路） |
| Region | `global` 端點（模型供應最齊全），但做成可設定 |
| Project ID | 自動偵測（`google.auth.default`），可被環境變數覆寫 |
| 依賴 | `google-auth`（已透過 `google-cloud-tasks` 間接存在，改為顯式列出） |

## 設計細節

### 1. 設定（`packages/core/config.py`）

新增三個欄位，**預設值維持現狀，不破壞既有部署**：

```python
gemini_backend: str = "api_key"   # "api_key" | "vertex"
vertex_project_id: str = ""        # 空字串 = 自動偵測
vertex_location: str = "global"
```

切換到 Vertex 只需在 Cloud Run 設 `GEMINI_BACKEND=vertex`，其餘自動。

### 2. Token 管理（新類別 `VertexTokenProvider`）

獨立、可單獨測試的小元件，負責 OAuth token 的快取與刷新。放在 `gemini.py`（或同模組）內。

職責：

- 第一次呼叫時以 `google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])`
  取得 credentials，並讀出自動偵測的 project ID。`google.auth.default` 為同步呼叫，
  以 `asyncio.to_thread` 包起避免阻塞 event loop。
- 每次取 token 前檢查 `creds.valid`；過期（或從未 refresh）才呼叫
  `creds.refresh(google.auth.transport.requests.Request())`（同樣用 `asyncio.to_thread`）。
  這解決 OAuth token 約 1 小時過期、翻譯長篇翻到一半被 401 的問題。
- 以 `asyncio.Lock` 保護，讓最多 3 條並行 batch 安全共用同一份 credentials，避免重複 refresh。
- 對外提供：`async def token() -> str` 與 `project_id` 屬性。
  若建構時帶入 `project_id`（來自 `VERTEX_PROJECT_ID`），優先使用該值，否則用自動偵測值。

### 3. Provider 改動（`packages/core/providers/translation/gemini.py`）

`__init__` 增加參數：`backend: str = "api_key"`、`vertex_project_id: str = ""`、`vertex_location: str = "global"`。
當 `backend == "vertex"` 時延遲建立一個 `VertexTokenProvider`。

核心翻譯邏輯（`translate_blocks` / `_pack_batches` / delimiter 解析 / `_per_segment_fallback` /
`_extract_text` / 安全過濾降級）**完全不動**。只在兩個點分流：

- **URL 組裝（新 `_build_url()`）**：
  - `api_key`：`https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}`（現狀）
  - `vertex`：`https://aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/publishers/google/models/{model}:generateContent`
    （`location` 預設 `global`，故 host 不帶 region 前綴；若改用 region，host 為 `{location}-aiplatform.googleapis.com`）
- **Headers**：
  - `vertex`：加 `Authorization: Bearer <token>`，token 在每個 batch 開始時跟 `VertexTokenProvider` 取得（確保不過期）。
  - `api_key`：維持空 header（`httpx` 由 `json=` 自動帶 `Content-Type`）。
- **`_fetch_with_retry` 簽名**：加一個 `headers: dict` 參數，傳給 `client.post(url, json=payload, headers=headers)`。

request payload 兩邊一模一樣，不需修改。

### 4. 接線（`apps/api_server/dependencies.py`）

`get_translation_provider()` 在建立 `GeminiTranslationProvider` 時多傳：

```python
backend=settings.gemini_backend,
vertex_project_id=settings.vertex_project_id,
vertex_location=settings.vertex_location,
```

### 5. 依賴（`requirements.txt`）

顯式新增 `google-auth>=2.0.0`（目前為 `google-cloud-tasks` 的間接依賴）。

### 6. 測試（新 `tests/unit/test_gemini_provider.py`）

mock 掉 `google.auth.default` 與 credentials 物件，不做真實網路呼叫：

- **`VertexTokenProvider`**：
  - 首次取 token 會呼叫 refresh。
  - token 未過期時不重複 refresh。
  - token 過期後再取會重新 refresh。
  - 建構時帶入的 `project_id` 優先於自動偵測值。
- **URL 組裝**：`api_key` 與 `vertex` 後端各組出預期 URL。
- **Headers**：`vertex` 後端帶 `Authorization: Bearer`；`api_key` 後端不帶。

## 範圍外（YAGNI）

- 不重寫成 `google-genai` SDK；保留手刻 httpx 邏輯。
- Vertex 配額 429（`RESOURCE_EXHAUSTED`）的 detail 解析照舊：status code 仍為 429，
  retry 主流程正常運作，`_is_daily_quota` 維持 best-effort，不特別為 Vertex 調整。

## 部署前置作業（GCP，程式之外，由使用者執行）

1. 啟用 Vertex AI API：
   `gcloud services enable aiplatform.googleapis.com --project=pixiv2kindle-bot`
2. 授權 Cloud Run service account（`371642369540-compute@developer.gserviceaccount.com`）
   `roles/aiplatform.user`。
3. 部署時設環境變數 `GEMINI_BACKEND=vertex`。
4. 本機測試需先 `gcloud auth application-default login`。
