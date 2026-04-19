# Pixiv2Kindle — 實作任務清單

> 依據 [spec.md](file:///Users/elin/Desktop/discord-pixiv-send/spec.md) v1.1 制定  
> 里程碑順序：M1 → M2 → M3 → M4

---

## M1：最小可行版本（本機 / VM 可執行）

> 目標：在本機或 VM 上用 FastAPI + LocalBackgroundQueue 完成單篇小說原文 EPUB → 寄送 Kindle → Discord 通知 的完整閉環。  
> VM 模式直接接收 Discord Interactions，包含驗簽與指令解析。

### 1. 專案骨架與基礎設施

- [ ] 建立專案目錄結構（`apps/`, `packages/`, `deploy/`, `tests/`）
- [ ] 建立 `requirements.txt`，安裝核心依賴（fastapi, uvicorn, pixivpy3, ebooklib, httpx, pydantic, jinja2, pytest）
- [ ] 建立 `.env.example`，包含 spec §22 所列所有環境變數
- [ ] 建立 `packages/core/config.py`，使用 Pydantic `BaseSettings` 載入環境變數
- [ ] 建立 `packages/core/exceptions.py`，定義 spec §20.1 所有錯誤類型

### 2. Domain Models

- [ ] 建立 `packages/core/domain/models.py`
  - [ ] `PixivNovel` dataclass
  - [ ] `BilingualBlock` dataclass
  - [ ] `SendNovelResult` dataclass
- [ ] 建立 `packages/core/domain/value_objects.py`
  - [ ] `ParsedNovelInput`（input_type, novel_id, series_id）
- [ ] 建立 API schema（Pydantic models）
  - [ ] `DiscordContext`
  - [ ] `UserContext`
  - [ ] `CommandPayload`
  - [ ] `EnqueueRequest`
  - [ ] `TaskPayload`（含 deadline 欄位）
  - [ ] `EnqueueResponse`

### 3. 輸入解析（Resolver）

- [ ] 建立 `packages/core/providers/pixiv/resolver.py`
  - [ ] 解析純 ID（如 `12345678`）
  - [ ] 解析小說 URL（`https://www.pixiv.net/novel/show.php?id=...`）
  - [ ] 解析系列 URL（先回傳 parsed result，M1 不支援系列但需辨識並拒絕）
  - [ ] 無效輸入拋出 `InvalidInputError`
- [ ] 對應單元測試

### 4. Pixiv 抓取

- [ ] 建立 `packages/core/providers/pixiv/pixivpy_client.py`
  - [ ] 初始化 `AppPixivAPI`，以 refresh token 認證
  - [ ] `fetch_novel_detail(novel_id) -> dict`（同步，取 metadata）
  - [ ] `fetch_novel_text(novel_id) -> str`（同步，取本文）
  - [ ] 認證失敗拋出 `PixivAuthError`
  - [ ] 抓取失敗拋出 `PixivFetchError`
- [ ] 建立 `packages/core/services/pixiv_service.py`
  - [ ] 實作 `PixivService` Protocol
  - [ ] `async fetch_novel(novel_input: str) -> PixivNovel`
  - [ ] 內部使用 `asyncio.to_thread()` 呼叫 pixivpy3 同步方法
  - [ ] 組裝 `PixivNovel` 物件
- [ ] 對應單元測試（mock pixivpy3）

### 5. 文字處理工具

- [ ] 建立 `packages/core/utils/text_splitter.py`
  - [ ] `split_text_into_blocks(text: str) -> list[str]`
  - [ ] 先以雙換行分段
  - [ ] 過長段落依句號、問號、驚嘆號再拆分
- [ ] 建立 `packages/core/utils/sanitizer.py`
  - [ ] 檔名清理（`safe_title`）
  - [ ] 內容正規化（去除多餘空白、不支援字元等）
- [ ] 對應單元測試

### 6. EPUB 生成

- [ ] 建立 `packages/core/templates/chapter.xhtml.j2`（原文模式模板）
- [ ] 建立 `packages/core/templates/styles.css`（spec §13.4 CSS）
- [ ] 建立 `packages/core/services/epub_service.py`
  - [ ] 實作 `EpubService` Protocol
  - [ ] `async build(novel: PixivNovel, blocks: list[BilingualBlock]) -> str`
  - [ ] 設定 metadata（title, creator, identifier）
  - [ ] 套用 Jinja2 模板
  - [ ] 使用 EbookLib 產生 `.epub`
  - [ ] 檔名依 spec §13.5 規則：`[pixiv][novel_{id}]_{safe_title}.epub`
  - [ ] 寫入 `TEMP_DIR`
- [ ] 對應單元測試

### 7. Kindle SMTP 寄送

- [ ] 建立 `packages/core/providers/kindle/smtp_sender.py`
  - [ ] 實作 `KindleSender` Protocol
  - [ ] `async send(file_path: str) -> None`
  - [ ] 建立 MIME message，附加 EPUB
  - [ ] 使用 `asyncio.to_thread()` 包裝 `smtplib` 同步呼叫
  - [ ] 寄送失敗拋出 `KindleDeliveryError`
- [ ] 對應單元測試（模擬 SMTP）

### 8. Discord 通知

- [ ] 建立 `packages/core/providers/discord/webhook_client.py`
  - [ ] 實作 `DiscordNotifier` Protocol
  - [ ] `async send_followup(application_id, interaction_token, content) -> None`
  - [ ] 使用 httpx POST Discord follow-up webhook
  - [ ] 失敗拋出 `DiscordNotifyError`
- [ ] 對應單元測試

### 9. 主用例服務

- [ ] 建立 `packages/core/services/pixiv_to_kindle_service.py`
  - [ ] `async execute_send_novel(payload: TaskPayload) -> SendNovelResult`
  - [ ] 組裝完整流程：解析 → 抓取 → 切分 → 建 EPUB → 寄送 → 通知
  - [ ] M1 先不含翻譯、time budget、檔案大小檢查（M2/M3 加入）
  - [ ] 任何步驟失敗皆 log + Discord follow-up 錯誤訊息
  - [ ] 清理暫存檔

### 10. 任務佇列抽象

- [ ] 建立 `packages/core/queue/base.py`
  - [ ] `TaskQueue` Protocol：`async enqueue_send_novel(payload: dict) -> None`
- [ ] 建立 `packages/core/queue/local_background.py`
  - [ ] `LocalBackgroundQueue` 實作
  - [ ] 使用 `asyncio.create_task()` 在背景執行 `PixivToKindleService`
  - [ ] 記錄任務啟動與完成 log

### 11. FastAPI 應用

- [ ] 建立 `apps/api_server/main.py`
  - [ ] FastAPI app factory
  - [ ] 載入 config
  - [ ] 初始化各 service / provider（DI）
- [ ] 建立 `apps/api_server/dependencies.py`
  - [ ] 各 service 的 FastAPI dependency
- [ ] 建立 `apps/api_server/routes/health.py`
  - [ ] `GET /healthz`
- [ ] 建立 `apps/api_server/routes/interactions.py`
  - [ ] `POST /interactions`（Discord Interaction endpoint）
  - [ ] 使用 PyNaCl 驗證 Discord Ed25519 signature
  - [ ] 處理 PING（type 1）→ 回 `{ type: 1 }`
  - [ ] 處理 APPLICATION_COMMAND（type 2）→ 回 deferred ack `{ type: 5 }`
  - [ ] 檢查 `discord_user_id` 是否為允許使用者
  - [ ] 解析 slash command 參數
  - [ ] 呼叫 `TaskQueue.enqueue_send_novel()` 啟動背景任務
- [ ] 建立 `apps/api_server/routes/enqueue.py`
  - [ ] `POST /internal/enqueue/pixiv-to-kindle`
  - [ ] 驗證 `X-Internal-Token`
  - [ ] 驗證 `discord_user_id` 是否為允許使用者
  - [ ] 呼叫 `TaskQueue.enqueue_send_novel()`
  - [ ] 回傳 `{ accepted: true, queued: true }`
- [ ] 建立 `apps/api_server/routes/tasks.py`
  - [ ] `POST /internal/tasks/execute`（task handler endpoint，供 Cloud Tasks 或本機測試直接呼叫）

### 12. 本機端到端驗證

- [ ] 本機啟動 FastAPI（`uvicorn`）
- [ ] 使用 curl / httpie 手動呼叫 enqueue API
- [ ] 確認完整流程：抓取 → EPUB → SMTP → Discord follow-up
- [ ] 確認 Kindle 可開啟收到的 EPUB

---

## M2：Cloudflare Workers + Cloud Run + Cloud Tasks

> 目標：正式部署到 Cloudflare Workers + GCP Cloud Run，使用 Cloud Tasks 做非同步任務排程，並加入 deadline 控制與檔案大小檢查。

### 13. Cloudflare Workers Gateway

- [ ] 建立 `apps/worker_gateway/` 結構
- [ ] 建立 `wrangler.toml`
- [ ] 建立 `src/index.ts`
  - [ ] Discord signature 驗簽
  - [ ] 檢查 `ALLOWED_DISCORD_USER_ID`
  - [ ] 解析 slash command 參數
  - [ ] 回傳 deferred ack（`type: 5`）
  - [ ] `ctx.waitUntil()` POST 呼叫 backend `/internal/enqueue/pixiv-to-kindle`
  - [ ] 附帶 `X-Internal-Token` header
- [ ] Discord 開發者後台註冊 slash command `/pixiv2kindle`（M1 參數：novel, translate, target_lang）
- [ ] 測試驗簽與 deferred ack 流程

### 14. Cloud Tasks 佇列實作

- [ ] 建立 `packages/core/queue/cloud_tasks.py`
  - [ ] `CloudTasksQueue` 實作
  - [ ] 使用 Google Cloud Tasks client 建立 HTTP task
  - [ ] 目標 URL 為 Cloud Run 的 `/internal/tasks/execute`
  - [ ] payload 為 `TaskPayload` JSON
  - [ ] 設定 task deadline / dispatch deadline

### 15. Follow-up Deadline 控制

- [ ] 建立 `packages/core/utils/time_budget.py`
  - [ ] `calculate_followup_deadline(interaction_created_at, soft_seconds, hard_seconds) -> epoch_ms`
  - [ ] `is_within_deadline(deadline_epoch_ms) -> bool`
  - [ ] `ensure_time_budget(deadline) -> None`（超時拋出 `TimeBudgetExceededError`）
- [ ] 在 enqueue 階段計算並寫入 `TaskPayload.deadline.followup_deadline_epoch_ms`
- [ ] 在 `pixiv_to_kindle_service.py` 中接入 deadline 檢查
  - [ ] 任務開始時檢查剩餘時間
  - [ ] 完成後判斷是否仍在 deadline 內（決定是否發 follow-up）
  - [ ] 超時標記 `NOTIFY_TIMEOUT`
- [ ] 對應單元測試

### 16. 檔案大小檢查

- [ ] 建立 `packages/core/utils/file_utils.py`
  - [ ] `ensure_file_size(file_path: str, max_bytes: int) -> None`
  - [ ] 超過拋出 `AttachmentTooLargeError`
- [ ] 在 `pixiv_to_kindle_service.py` 中，EPUB 產出後 & 寄送前檢查
- [ ] 對應單元測試

### 17. Cloud Run 部署

- [ ] 建立 `deploy/cloudrun/Dockerfile`
- [ ] 建立 `deploy/cloudrun/service.yaml`（含 `--cpu-throttling=false` 或適當 timeout 設定）
- [ ] 確認 Cloud Run 可正常啟動 FastAPI
- [ ] 確認 Cloud Tasks → Cloud Run task handler 可正常觸發

### 18. M2 端到端驗證

- [ ] Discord 手機端執行 `/pixiv2kindle novel:...`
- [ ] Workers 成功 deferred ack
- [ ] Cloud Tasks 成功觸發 task handler
- [ ] Kindle 成功收到 EPUB
- [ ] Discord 成功收到 follow-up 訊息
- [ ] 測試超大檔案被正確拒絕

---

## M3：翻譯功能

> 目標：加入翻譯 provider、雙語 EPUB 輸出、時間預算控制與降級策略。

### 19. 翻譯 Provider

- [ ] 建立 `packages/core/providers/translation/base.py`
  - [ ] `TranslationProvider` Protocol
- [ ] 建立 `packages/core/providers/translation/noop.py`
  - [ ] 回傳原文（用於不翻譯場景與測試）
- [ ] 建立 `packages/core/providers/translation/gemini.py`
  - [ ] 呼叫 Gemini API
  - [ ] 實作 `translate_blocks()`
  - [ ] 失敗拋出 `TranslationError`
- [ ] 建立 `packages/core/providers/translation/openai.py`
  - [ ] 呼叫 OpenAI API
  - [ ] 實作 `translate_blocks()`
  - [ ] 失敗拋出 `TranslationError`
- [ ] Config 中依 `TRANSLATION_PROVIDER` 環境變數選擇 provider

### 20. 翻譯服務

- [ ] 建立 `packages/core/services/translation_service.py`
  - [ ] 封裝 provider 呼叫
  - [ ] 處理 block-by-block 翻譯
  - [ ] 確保 source block 與 translated block 數量一致

### 21. 雙語 EPUB

- [ ] 更新 `chapter.xhtml.j2` 支援雙語結構（`div.block > p.src + p.dst`）
- [ ] 更新 `epub_service.py`
  - [ ] 根據 blocks 中 `translated` 是否有值決定 mono / bilingual 模板

### 22. 時間預算估算

- [ ] 更新 `time_budget.py`
  - [ ] `ensure_translation_budget(blocks, deadline) -> None`
  - [ ] 根據 block 數量 / 字數估算翻譯所需時間
  - [ ] 若預估超過 deadline，直接拒絕並回 Discord 訊息
- [ ] 在 `pixiv_to_kindle_service.py` 的翻譯步驟前呼叫

### 23. 翻譯降級策略

- [ ] 在 `pixiv_to_kindle_service.py` 中
  - [ ] 若 `FAIL_ON_TRANSLATION_ERROR=true`：翻譯失敗即任務失敗
  - [ ] 若 `FAIL_ON_TRANSLATION_ERROR=false`：翻譯失敗降級為原文 EPUB
- [ ] Discord 通知訊息說明是否有降級

### 24. M3 整合流程更新

- [ ] `pixiv_to_kindle_service.py` 加入完整翻譯分支
  - [ ] `translate=true` → 切分 → 估時 → 翻譯 → 雙語 blocks
  - [ ] `translate=false` → 原文 blocks

### 25. M3 端到端驗證

- [ ] Discord 指令 `translate:true` 成功產出雙語 EPUB
- [ ] Kindle 可正常閱讀雙語格式
- [ ] 翻譯失敗降級為原文（`FAIL_ON_TRANSLATION_ERROR=false`）
- [ ] 超長作品被拒絕並收到合理訊息

---

## M4：系列小說與穩定性

> 目標：支援系列小說、分冊、bot fallback 通知、fallback parser。

### 26. 系列小說支援

- [ ] 更新 `resolver.py` 支援系列 URL 解析
- [ ] 更新 `pixivpy_client.py`
  - [ ] `fetch_series_detail(series_id) -> dict`
  - [ ] `fetch_series_novels(series_id) -> list[dict]`
- [ ] 更新 `pixiv_service.py`
  - [ ] 支援系列模式：取得所有章節並按順序排列
- [ ] 更新 `epub_service.py`
  - [ ] 系列模式：多章節 EPUB，每篇作為一章
  - [ ] 檔名：`[pixiv][series_{series_id}]_{safe_title}.epub`
- [ ] Discord slash command 新增 `series_mode` 參數

### 27. 分冊策略

- [ ] 系列 EPUB 超過 `MAX_EPUB_BYTES` 時自動分冊
- [ ] 每冊分別寄送 Kindle
- [ ] Discord 通知顯示分冊數與各冊資訊

### 28. Bot Token Fallback 通知

- [ ] 建立 `packages/core/providers/discord/bot_rest_client.py`
  - [ ] 使用 `DISCORD_BOT_TOKEN` 發送一般 channel message
- [ ] 更新 `discord_notifier.py`
  - [ ] 當 follow-up deadline 過期時，嘗試 bot REST fallback
  - [ ] 需要 `channel_id`（在 `DiscordContext` 中已有）

### 29. Fallback Parser

- [ ] 建立 `packages/core/providers/pixiv/fallback_parser.py`
  - [ ] 當 pixivpy3 抓取特定小說失敗時的備援方案
  - [ ] 直接 HTTP 抓取 + HTML parsing（有能力限制）
- [ ] 更新 `pixiv_service.py` 加入 fallback 邏輯

### 30. Discord `layout` 參數

- [ ] Discord slash command 新增 `layout` 參數
- [ ] 允許使用者在 `translate=true` 時手動選擇 `mono`（僅看原文）

### 31. M4 端到端驗證

- [ ] 系列小說成功產出多章 EPUB
- [ ] 超大系列成功分冊寄送
- [ ] 超時任務透過 bot fallback 成功通知
- [ ] fallback parser 在主路徑失敗時可成功抓取

---

## 跨里程碑：持續品質

- [ ] 所有 service protocol 有對應 mock
- [ ] CI 可跑 `pytest tests/unit/`
- [ ] `.env.example` 隨功能新增同步更新
- [ ] `README.md` 隨里程碑更新（安裝、設定、使用方式）
- [ ] 日誌格式符合 spec §23（request_id, elapsed_ms 等欄位）
