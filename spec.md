以下是依照你提供的回饋重新整理後的 **修正版 spec**。
這版有幾個關鍵調整：

* 明確把 **Discord interaction token 只有 15 分鐘有效** 寫進規格，並把系統的目標處理時間訂成 **12 分鐘內完成 follow-up**，超過則走失敗/降級策略。([Discord 開發者平台文檔][1])
* 不採用 `pixivpy-async`，改為 **固定使用 `pixivpy3`**，並在 Python 端用 `asyncio.to_thread()` 包裝同步呼叫。`pixivpy` README 也明確列出 refresh token 認證與小說 API 能力。([GitHub][2])
* 不再使用「Cloud Run 回 202 後在同一 request 背景慢慢跑」作為主策略，因為 Cloud Run 在 **request-based billing** 下，請求結束後 CPU 會停用或大幅受限；改成 **Cloud Tasks 觸發真正的任務 handler**。Cloud Run 也支援最長 60 分鐘 request timeout。([Google Cloud Documentation][3])
* Workers 端明確要求用 `ctx.waitUntil()` 送出後端 enqueue 呼叫，避免回應後請求被取消。([Cloudflare Docs][4])
* Kindle 端補上 **單一附件 50 MB** 限制，系列小說若超過要分冊或直接報錯。([亞馬遜][5])

下面是可直接存成 `SPEC.md` 的版本：

````md
# Pixiv Novel to Kindle via Discord
## Product / System Specification
Version: 1.1  
Status: Draft for Implementation  
Owner: Personal Use  
Primary Language: Python  
Gateway Layer: Cloudflare Workers  
Primary Runtime: GCP Cloud Run  
Async Execution on Cloud Run: Cloud Tasks  
Compatible Runtime: VM / VPS / On-prem Host

---

## 1. 專案目標

建立一個自用系統，讓使用者可以在手機 Discord 中輸入 pixiv 小說 URL 或小說 ID，系統自動完成：

1. 解析 pixiv 小說
2. 抓取小說內容
3. 視需求進行翻譯
4. 生成適合 Kindle 閱讀的 EPUB
5. 寄送到使用者 Kindle
6. 在 Discord 回報結果

本專案目前僅供單一使用者自用，不考慮多租戶、公開服務化與複雜帳號系統。

---

## 2. 核心約束與設計決策

### 2.1 Discord interaction 時效
Discord interaction token 僅能在有限時效內做 follow-up，因此本系統必須以「快速 ack、任務非同步處理、盡量在 12 分鐘內完成 follow-up」為原則。

### 2.2 Pixiv API 客戶端決策
本專案固定使用 `pixivpy3`，不使用 `pixivpy-async`。

原因：
- `pixivpy3` 仍是主整合基礎
- 既有能力足夠涵蓋小說 detail / text / series 類需求
- 非同步需求由應用層包裝處理，不依賴未維護的 async 分支

### 2.3 Cloud Run 背景任務策略
本專案在 Cloud Run 上**不採用**「HTTP request 回應後，仍在同一 request context 中繼續跑長任務」作為主策略。

正式策略：
- Cloudflare Workers 只做驗簽、授權與 defer
- 後端接到請求後，只做驗證與 enqueue
- 真正的抓 pixiv / 翻譯 / EPUB / 寄 Kindle 由 Cloud Tasks 呼叫專用 task handler 執行

### 2.4 兼容部署策略
為兼容一般主機（VM / VPS / 地端）：
- 核心業務邏輯固定不變
- Cloud Run 版使用 Cloud Tasks
- 一般主機版可使用「本機背景工作器」或「同步任務端點」
- API contract 儘量一致

---

## 3. 使用情境

### 3.1 主要使用情境
使用者在 Discord 手機端輸入 slash command：

- `/pixiv2kindle novel:https://www.pixiv.net/novel/show.php?id=12345678`
- `/pixiv2kindle novel:12345678`
- `/pixiv2kindle novel:12345678 translate:true`
- `/pixiv2kindle novel:12345678 translate:true target_lang:zh-TW`

系統流程：
1. Discord 將 interaction 傳給 Cloudflare Workers
2. Workers 驗簽並驗證使用者
3. Workers 立刻回 deferred response
4. Workers 呼叫後端 enqueue API
5. 後端建立任務
6. 任務執行完成後，以 Discord follow-up webhook 回報結果

---

## 4. 範圍

### 4.1 第一版（M1-M2）要做
- 支援 pixiv 小說 URL / ID
- 支援單篇小說
- 支援可選翻譯
- 支援雙語 EPUB（原文在上、譯文在下）
- 支援寄送 Kindle
- 支援 Discord 回報結果
- 僅允許指定 Discord User ID 使用
- Cloudflare Workers + Cloud Run + Cloud Tasks 部署模式
- 兼容一般主機部署模式

### 4.2 第一版不做
- Web 管理後台
- 公開多使用者使用
- OAuth 帳號系統
- pixiv 收藏夾同步
- App
- 批量排程平台

### 4.3 第二階段（M4+）
- pixiv 系列小說
- glossary / 專有名詞表
- 失敗重試 UI
- 備份下載
- 更多翻譯 provider

---

## 5. 系統架構總覽

### 5.1 Cloudflare Workers + Cloud Run 正式架構

```text
Discord
  -> Cloudflare Workers
      - 驗簽 Discord Interactions
      - 驗證使用者
      - 回 deferred ack
      - waitUntil() 呼叫 backend enqueue API
  -> Cloud Run API
      - 驗證內部請求
      - 建立 Cloud Tasks HTTP task
      - 立即回 accepted
  -> Cloud Tasks
      - 呼叫 Cloud Run task handler
  -> Cloud Run Task Handler
      - 抓 pixiv 小說
      - 視需要翻譯
      - 生成 EPUB
      - 寄送 Kindle
      - 發 Discord follow-up
````

### 5.2 一般主機兼容架構

```text
Discord
  -> FastAPI Server (VM / VPS / On-prem)
      - 驗簽 Discord Interactions
      - 驗證使用者
      - 回 deferred ack
      - 將任務丟給本機背景工作器
  -> Local Worker
      - 抓 pixiv 小說
      - 視需要翻譯
      - 生成 EPUB
      - 寄送 Kindle
      - 發 Discord follow-up
```

### 5.3 架構原則

* Workers 不做核心業務邏輯
* 核心 Python 邏輯不得依賴特定部署平台
* Cloud Run 與 VM 共用同一套核心 service
* 非同步任務機制可替換，但業務流程不變

---

## 6. 技術選型

### 6.1 推薦語言

Python

### 6.2 核心技術

* Cloudflare Workers：Discord gateway
* FastAPI：主 API 與 task handler
* Cloud Tasks：Cloud Run 版非同步任務執行
* pixivpy3：Pixiv API client
* EbookLib：EPUB 生成
* httpx：HTTP client
* SMTP：Send to Kindle
* Pydantic：API schema、settings
* dataclass：少量內部 domain value object（可選）
* Jinja2：EPUB 模板
* pytest：測試

### 6.3 Model 使用原則

* **API input/output schema**：統一使用 Pydantic
* **內部純 domain object**：可用 dataclass
* 若想簡化，也可在實作時統一全部用 Pydantic；此為允許選項，不強制

---

## 7. 專案結構

```text
project/
  apps/
    api_server/
      main.py
      routes/
        interactions.py
        enqueue.py
        health.py
        tasks.py
      dependencies.py

    worker_gateway/
      src/
        index.ts
      wrangler.toml

  packages/
    core/
      config.py
      exceptions.py

      domain/
        models.py
        value_objects.py

      services/
        pixiv_to_kindle_service.py
        pixiv_service.py
        translation_service.py
        epub_service.py
        kindle_service.py
        discord_notifier.py

      providers/
        pixiv/
          pixivpy_client.py
          resolver.py
          fallback_parser.py

        translation/
          base.py
          noop.py
          gemini.py
          openai.py

        kindle/
          smtp_sender.py

        discord/
          webhook_client.py
          bot_rest_client.py   # optional fallback

      queue/
        base.py
        cloud_tasks.py
        local_background.py

      utils/
        text_splitter.py
        sanitizer.py
        retry.py
        file_utils.py
        time_budget.py

      templates/
        chapter.xhtml.j2
        styles.css

  deploy/
    cloudrun/
      Dockerfile
      service.yaml
    vm/
      systemd/
        api.service
        worker.service
      nginx/
        site.conf

  tests/
    unit/
    integration/

  .env.example
  requirements.txt
  README.md
  SPEC.md
```

---

## 8. Discord 指令規格

### 8.1 指令名稱

`/pixiv2kindle`

### 8.2 M1 指令參數

#### `novel`

* type: string
* required: true
* 說明：pixiv 小說 URL 或小說 ID

#### `translate`

* type: boolean
* required: false
* default: false

#### `target_lang`

* type: string
* required: false
* default: `zh-TW`

### 8.3 M1 不提供的參數

以下參數在 M1 **不註冊到 Discord slash command**：

* `series_mode`
* `layout`

原因：

* M1 尚不支援系列
* `layout` 在 M1 直接由 `translate` 推導即可，避免規格與實作矛盾

### 8.4 M3 之後可追加參數

#### `layout`

* allowed:

  * `mono`
  * `bilingual`
* default:

  * `mono` when translate = false
  * `bilingual` when translate = true

#### `series_mode`

* allowed:

  * `auto`
  * `single`
  * `series`

---

## 9. API 與資料模型

### 9.1 Workers -> Backend Enqueue API

#### Endpoint

`POST /internal/enqueue/pixiv-to-kindle`

#### Request

```json
{
  "request_id": "uuid",
  "discord": {
    "application_id": "123456789",
    "interaction_token": "abcdef",
    "channel_id": "optional",
    "guild_id": "optional"
  },
  "user": {
    "discord_user_id": "11111111"
  },
  "command": {
    "novel_input": "12345678",
    "translate": true,
    "target_lang": "zh-TW"
  }
}
```

#### Response

```json
{
  "accepted": true,
  "queued": true
}
```

### 9.2 Cloud Tasks / Local Worker Task Payload

```json
{
  "request_id": "uuid",
  "discord": {
    "application_id": "123456789",
    "interaction_token": "abcdef",
    "channel_id": "optional",
    "guild_id": "optional"
  },
  "user": {
    "discord_user_id": "11111111"
  },
  "command": {
    "novel_input": "12345678",
    "translate": true,
    "target_lang": "zh-TW"
  },
  "deadline": {
    "followup_deadline_epoch_ms": 0
  }
}
```

### 9.3 Health Check

`GET /healthz`

---

## 10. Domain Models

### 10.1 Pydantic Models for API

```python
class DiscordContext(BaseModel):
    application_id: str
    interaction_token: str
    channel_id: str | None = None
    guild_id: str | None = None

class UserContext(BaseModel):
    discord_user_id: str

class CommandPayload(BaseModel):
    novel_input: str
    translate: bool = False
    target_lang: str = "zh-TW"

class EnqueueRequest(BaseModel):
    request_id: str
    discord: DiscordContext
    user: UserContext
    command: CommandPayload
```

### 10.2 Internal Domain Objects

```python
@dataclass
class PixivNovel:
    novel_id: int
    title: str
    author_name: str
    caption: str | None
    text: str
    tags: list[str]
    series_id: int | None = None
    series_title: str | None = None
```

```python
@dataclass
class BilingualBlock:
    source: str
    translated: str | None
```

---

## 11. Pixiv 整合規格

### 11.1 使用策略

主方案固定使用 `pixivpy3`。

### 11.2 同步 / 非同步策略

`pixivpy3` 為同步函式庫，因此在 FastAPI / async service 中：

* 不直接在 event loop 內呼叫阻塞函式
* 以 `asyncio.to_thread()` 包裝 pixivpy3 呼叫
* 若未來需要，可替換為自製 async adapter，但外部 service 介面不變

### 11.3 主要能力

* 單篇小說 detail
* 單篇小說本文
* 後續可擴充 series

### 11.4 認證

使用 refresh token。

### 11.5 token 失效策略

若 pixiv refresh token 失效：

* 任務立即失敗
* Discord follow-up 回覆「pixiv 認證失效，需更新 refresh token」
* 不做自動重新登入流程
* 由維運者手動更新 env var 後重試

### 11.6 Fallback parser

保留 fallback parser 模組，但第一版僅作預留，不作主路徑。

---

## 12. 翻譯規格

### 12.1 翻譯開關

* `translate=false`：原文模式
* `translate=true`：雙語模式

### 12.2 輸出形式

採段落級雙語：

```text
原文段落
譯文段落
```

### 12.3 切分策略

1. 先以雙換行切段
2. 過長段落再依句點、問號、驚嘆號拆分
3. 避免單一 block 過長

### 12.4 翻譯原則

* 保留專有名詞
* 保留人物稱謂
* 不摘要
* 不省略
* 一段對一段

### 12.5 Provider 介面

```python
class TranslationProvider(Protocol):
    async def translate_blocks(self, blocks: list[str], target_lang: str) -> list[str]:
        ...
```

### 12.6 時間預算策略

由於 Discord follow-up 有效期限制，本系統對翻譯任務設下：

* 預估處理時間上限：12 分鐘
* 若估算翻譯量可能超過限制，策略如下：

  1. 直接拒絕並回覆「內容過長，請關閉翻譯或改為較短作品」
  2. 後續可擴充為自動切冊

### 12.7 降級策略

可配置：

* `FAIL_ON_TRANSLATION_ERROR=true`：翻譯失敗即整體失敗
* `FAIL_ON_TRANSLATION_ERROR=false`：翻譯失敗則降級為原文 EPUB

---

## 13. EPUB 規格

### 13.1 輸出格式

* `.epub`

### 13.2 Metadata

* Title：小說標題
* Creator：作者
* Identifier：pixiv novel id

### 13.3 雙語 HTML 結構

```html
<div class="block">
  <p class="src">原文內容</p>
  <p class="dst">譯文內容</p>
</div>
```

### 13.4 CSS

```css
body {
  font-family: serif;
  line-height: 1.6;
}

.block {
  margin-bottom: 1.1em;
}

.src {
  margin: 0 0 0.2em 0;
}

.dst {
  margin: 0 0 0.8em 0;
  font-size: 0.92em;
  opacity: 0.78;
}
```

### 13.5 檔名規則

```text
[pixiv][novel_{novel_id}]_{safe_title}.epub
```

### 13.6 檔案大小限制

在寄送前必須檢查檔案大小：

* 若單一 EPUB 超過 Kindle email 可接受大小，任務失敗
* 第二階段可支援「分冊輸出」

---

## 14. Kindle 寄送規格

### 14.1 方式

SMTP 寄送 EPUB 到 Kindle email。

### 14.2 必要設定

* `KINDLE_EMAIL`
* `SMTP_HOST`
* `SMTP_PORT`
* `SMTP_USERNAME`
* `SMTP_PASSWORD`
* `SMTP_FROM`

### 14.3 流程

1. 產生 EPUB
2. 檢查檔案大小
3. 建立信件
4. 附加 EPUB
5. 寄送
6. 清理暫存檔

### 14.4 失敗處理

* SMTP 失敗：回 Discord 錯誤訊息
* 附件過大：回 Discord 指出需縮小內容或未來使用分冊

---

## 15. Discord 通知規格

### 15.1 主要通知機制

完成後使用 interaction follow-up webhook 回覆。

### 15.2 follow-up deadline

任務建立時應計算：

* `followup_deadline = interaction_created_at + 15 minutes - safety_margin`
* safety margin 建議 2~3 分鐘
* 本系統以 12 分鐘作為內部目標上限

### 15.3 超時策略

若任務已接近或超過 follow-up deadline：

* 不再嘗試 interaction follow-up
* 任務標記為 `NOTIFY_TIMEOUT`
* 可選 fallback：

  * 一般 bot REST message 至原頻道
  * 記錄失敗並由管理者人工查看

### 15.4 第一版 fallback 政策

M1 先不實作 bot REST fallback，僅記錄 log 並回報任務超時。
M2+ 可擴充 bot token fallback 通知。

---

## 16. Workers 規格

### 16.1 Workers 職責

* 驗簽 Discord Interactions
* 驗證是否為允許使用者
* 立即回 deferred response
* 使用 `ctx.waitUntil()` 呼叫 backend enqueue API

### 16.2 Workers 不負責

* 抓 pixiv
* 翻譯
* 產 EPUB
* 寄送 Kindle
* 長時間背景處理

### 16.3 Workers 偽代碼

```ts
export default {
  async fetch(request, env, ctx) {
    // 1. verify discord signature
    // 2. authorize user
    // 3. parse command
    // 4. ctx.waitUntil(fetch(BACKEND_ENQUEUE_URL, ...))
    // 5. return deferred ack
    return new Response(JSON.stringify({ type: 5 }), {
      headers: { "content-type": "application/json" }
    });
  }
}
```

### 16.4 內部安全

Workers 呼叫 backend 時必須帶：

* `X-Internal-Token`
  或
* OIDC / mTLS（後續可擴充）

---

## 17. Cloud Run / VM 後端規格

### 17.1 Cloud Run 模式

Cloud Run 僅負責：

* 接收 enqueue 請求
* 建立 Cloud Tasks
* 執行 task handler

### 17.2 為何要用 Cloud Tasks

避免：

* request 回應後 CPU 被停用或受限
* 長任務與 HTTP 生命周期耦合
* 重試與可靠投遞自行實作

### 17.3 VM 模式

VM 可選：

* local background worker
* 直接同步任務 handler
* 或自行接入 queue

### 17.4 Queue 抽象

```python
class TaskQueue(Protocol):
    async def enqueue_send_novel(self, payload: dict) -> None:
        ...
```

實作：

* `CloudTasksQueue`
* `LocalBackgroundQueue`

---

## 18. 核心服務規格

### 18.1 主用例

`PixivToKindleService`

責任：

1. 驗證時間預算
2. 抓取小說
3. 清理與切分內容
4. 可選翻譯
5. 生成 EPUB
6. 檢查大小
7. 寄送 Kindle
8. 發 Discord follow-up

### 18.2 介面

```python
class PixivService(Protocol):
    async def fetch_novel(self, novel_input: str) -> PixivNovel:
        ...
```

```python
class EpubService(Protocol):
    async def build(self, novel: PixivNovel, blocks: list[BilingualBlock]) -> str:
        ...
```

```python
class KindleSender(Protocol):
    async def send(self, file_path: str) -> None:
        ...
```

```python
class DiscordNotifier(Protocol):
    async def send_followup(self, application_id: str, interaction_token: str, content: str) -> None:
        ...
```

---

## 19. 詳細流程

### 19.1 enqueue 流程

1. Workers 收到 interaction
2. 驗簽成功
3. 驗證 user id
4. 回 deferred ack
5. `ctx.waitUntil()` 呼叫 `/internal/enqueue/pixiv-to-kindle`
6. backend 建立 queue task
7. backend 回 accepted

### 19.2 task handler 流程

1. 接收 task payload
2. 檢查剩餘 follow-up 時間是否足夠
3. 解析 novel input
4. 用 `asyncio.to_thread()` 呼叫 pixivpy3
5. 清理文字
6. 視需要翻譯
7. 建立 EPUB
8. 檢查附件大小
9. 寄送 Kindle
10. 在 deadline 內發 follow-up
11. 清理暫存

### 19.3 失敗流程

任一步驟失敗：

* 寫入 log
* 若仍在 follow-up deadline 內，回 Discord 錯誤訊息
* 若已超時，記錄 `NOTIFY_TIMEOUT`

---

## 20. 例外與錯誤處理

### 20.1 錯誤類型

* `InvalidInputError`
* `UnauthorizedUserError`
* `PixivAuthError`
* `PixivFetchError`
* `TranslationError`
* `TimeBudgetExceededError`
* `EpubBuildError`
* `AttachmentTooLargeError`
* `KindleDeliveryError`
* `DiscordNotifyError`

### 20.2 使用者可理解訊息

* 無法解析 pixiv 連結或 ID
* pixiv 認證失效，需更新 refresh token
* 找不到小說或無法讀取
* 內容過長，翻譯可能超過可通知時限
* EPUB 檔案過大，無法寄送到 Kindle
* Kindle 寄送失敗
* 任務完成，但通知逾時未能傳回 Discord

---

## 21. 權限與安全

### 21.1 Discord User 限制

僅允許單一 Discord User ID。

### 21.2 Secrets

* Discord public key
* Pixiv refresh token
* SMTP credentials
* Kindle email
* Translation API keys
* Internal API token

### 21.3 檔案保存

預設不永久保存全文與 EPUB。
可配置保留最近 N 份成功產物。

---

## 22. 設定與環境變數

```env
APP_NAME=pixiv2kindle
APP_ENV=dev
LOG_LEVEL=INFO

DISCORD_PUBLIC_KEY=
DISCORD_APPLICATION_ID=
DISCORD_BOT_TOKEN=
ALLOWED_DISCORD_USER_ID=

PIXIV_REFRESH_TOKEN=

KINDLE_EMAIL=
SMTP_HOST=
SMTP_PORT=
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM=

TRANSLATION_PROVIDER=noop
GEMINI_API_KEY=
OPENAI_API_KEY=
FAIL_ON_TRANSLATION_ERROR=false

TEMP_DIR=./tmp
KEEP_RECENT_EPUB_COUNT=0
MAX_EPUB_BYTES=50000000

INTERNAL_API_TOKEN=
BACKEND_BASE_URL=

QUEUE_BACKEND=cloud_tasks
CLOUD_TASKS_PROJECT_ID=
CLOUD_TASKS_LOCATION=
CLOUD_TASKS_QUEUE_NAME=
CLOUD_TASKS_TASK_HANDLER_URL=

FOLLOWUP_SOFT_DEADLINE_SECONDS=720
FOLLOWUP_HARD_DEADLINE_SECONDS=900
```

---

## 23. 日誌與觀測

### 23.1 每次任務記錄

* request_id
* discord_user_id
* novel_input
* resolved_novel_id
* translate
* target_lang
* task_backend
* result_status
* notify_status
* elapsed_ms

### 23.2 任務狀態

* `QUEUED`
* `RUNNING`
* `SUCCEEDED`
* `FAILED`
* `NOTIFY_TIMEOUT`

---

## 24. 測試規格

### 24.1 單元測試

* URL / ID 解析
* follow-up deadline 計算
* time budget 判斷
* pixivpy3 同步呼叫包裝
* 段落切分
* bilingual block 組裝
* EPUB metadata
* 檔案大小檢查

### 24.2 整合測試

* pixivpy3 可取得測試小說
* enqueue API 可成功建立任務
* task handler 可完成整體流程
* SMTP 可成功建立郵件
* Discord follow-up 可送出

### 24.3 手動驗收

* Discord 手機端指令正常
* 原文模式成功寄送
* 翻譯模式成功寄送
* 超長作品能正確被拒絕或降級
* Kindle 可正常開啟 EPUB

---

## 25. 里程碑

### M1

* FastAPI API
* pixivpy3 單篇小說抓取
* 原文 EPUB
* Kindle 寄送
* Discord follow-up
* LocalBackgroundQueue（VM 版）

### M2

* Cloudflare Workers
* Cloud Tasks
* Cloud Run 正式部署
* follow-up deadline 控制
* 檔案大小檢查

### M3

* 翻譯 provider
* 雙語 EPUB
* 時間預算估算與拒絕策略
* 失敗降級策略

### M4

* 系列小說
* 分冊策略
* bot token fallback 通知
* fallback parser

---

## 26. 偽代碼

```python
async def execute_send_novel(req: TaskPayload) -> SendNovelResult:
    ensure_time_budget(req.deadline)

    novel = await pixiv_service.fetch_novel(req.command.novel_input)

    source_blocks = split_text_into_blocks(novel.text)

    if req.command.translate:
        ensure_translation_budget(source_blocks, req.deadline)
        translated = await translation_provider.translate_blocks(
            source_blocks,
            req.command.target_lang
        )
        blocks = [
            BilingualBlock(source=s, translated=t)
            for s, t in zip(source_blocks, translated)
        ]
    else:
        blocks = [
            BilingualBlock(source=s, translated=None)
            for s in source_blocks
        ]

    file_path = await epub_service.build(novel, blocks)

    ensure_file_size(file_path)

    await kindle_sender.send(file_path)

    if within_followup_deadline(req.deadline):
        await discord_notifier.send_followup(
            application_id=req.discord.application_id,
            interaction_token=req.discord.interaction_token,
            content=f"已寄送《{novel.title}》到 Kindle"
        )
    else:
        mark_notify_timeout(req.request_id)

    return SendNovelResult(
        success=True,
        title=novel.title,
        novel_id=novel.novel_id,
        file_path=file_path,
        message="done"
    )
```

---

## 27. 最終定案

本專案正式架構如下：

* Discord 入口：Cloudflare Workers
* 主 API：FastAPI
* Cloud Run 非同步執行：Cloud Tasks
* Pixiv 整合：pixivpy3
* 同步函式庫非同步化：`asyncio.to_thread()`
* 翻譯：可插拔 provider
* 電子書：EPUB
* 投遞：SMTP -> Kindle email
* 一般主機兼容：以 LocalBackgroundQueue 取代 Cloud Tasks
* 所有核心邏輯固定集中於 Python core

此設計可同時支援：

* Cloudflare Workers + GCP Cloud Run
* 一般雲端 VM / VPS
* 地端主機
* 本機開發

```

```

[1]: https://docs.discord.com/developers/interactions/receiving-and-responding?utm_source=chatgpt.com "Receiving and Responding to Interactions - Documentation"
[2]: https://github.com/upbit/pixivpy?utm_source=chatgpt.com "upbit/pixivpy: Pixiv API for Python"
[3]: https://docs.cloud.google.com/run/docs/tips/general?utm_source=chatgpt.com "General development tips | Cloud Run"
[4]: https://developers.cloudflare.com/workers/runtime-apis/context/?utm_source=chatgpt.com "Context (ctx) - Workers"
[5]: https://www.amazon.com/gp/help/customer/display.html?nodeId=G7NECT4B4ZWHQ8WV&utm_source=chatgpt.com "Learn How to Use Your Send to Kindle Email Address"
