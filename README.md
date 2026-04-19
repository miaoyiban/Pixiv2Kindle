# Pixiv2Kindle Discord Bot

**Pixiv2Kindle** 是一個自用的 Discord 機器人，讓你可以在手機或電腦的 Discord 中，透過 `/pixiv2kindle` 指令輕鬆下載 Pixiv 上的小說，可選擇透過 **Google Gemini** 自動翻譯，並直接寄送到你的 Kindle 閱讀器。

> [!WARNING]
> ## ⚠️ 開發緣由與免責聲明
> 開發本專案的初衷，是因為開發者本人**視力逐漸惡化，加上板機指發作**，已經無法長時間手持手機或是緊盯著發光螢幕追連載。為了能繼續閱讀喜愛的作品，才開發了這個讓文章直接導入電子紙閱讀器（Kindle）的工具，以減輕對眼睛和手部的負擔。
> \
> 將他人的心血作品任意下載或轉載，是會讓創作者感到難過與受挫的行為。請各位使用者務必遵守：**本機器人僅供「個人離線閱讀使用」**，絕對禁止二次上傳或分享。在使用本系統取得更好的閱讀體驗之餘，也請**務必回到 Pixiv 去給您喜愛的作者留下您的「愛心」、「書籤」或「留言」**，多多鼓勵他們持續創作！
## 功能特色
- **Pixiv 小說下載**：支援透過網址或小說 ID 進行載入。
- **高品質的 AI 翻譯**：支援透過 Google Gemini 模型 (gemini-2.5-flash / gemini-3.1 等) 進行翻譯，內建完善的批次處理與分段重試機制，保證長篇小說不漏段。
- **雙語 EPUB 製作**：精美的雙語對照排版（日文原文 / 繁體中文譯文）。
- **直送 Kindle**：產生 EPUB 後自動透過 SMTP 發送到使用者的 `Send to Kindle` 信箱。
- **狀態即時回報**：任務處理完成後自動在 Discord 中 Follow-up 回報執行時間與結果。
- **靈活部署**：相容於一般的 Local VM / VPS 同步部署，或是基於 GCP Cloud Run + Cloud Tasks + Cloudflare Workers 的 Serverless 非同步部署！

---

## 系統架構

為了因應 Discord 規定的 **3 秒鐘 Ack 期限** 以及 **15 分鐘 Interaction Follow-up 期限**，本專案提供兩種部署架構可供自由選擇：

### 1. 一般主機部署（VM / VPS / Local）
這是一個適合個人、簡單直覺且不需要設定一堆雲端服務的做法。
- **架構流程**：Discord `➔` FastAPI Server
- Discord 會將 Interaction 送到你自建的 HTTP 端點。
- 專案使用內建的 Python Async / Background Tasks 響應，會立刻回覆 Discord `Accepted`，並在背景花幾分鐘慢慢下載與翻譯，最後再透過 Discord Webhook 傳送完成訊息。

### 2. 雲端 Serverless 部署（GCP Cloud Run + Cloudflare Workers）
這是一個不需要維護伺服器、可自動擴展，並且完美解決長任務 Timeout 限制的做法。也透過 Cloud Tasks 避免了 Cloud Run 的 request-based billing 在背景會限縮 CPU 的問題。
- **架構流程**：Discord `➔` Cloudflare Workers `➔` Cloud Tasks `➔` GCP Cloud Run (FastAPI)
- **Cloudflare Workers**：負責驗證 Discord Ed25519 數位簽章、辨識使用者 ID，並立即回傳 `Ack`。接著使用 `ctx.waitUntil()` 將任務 Enqueue 至後端。
- **GCP Cloud Run**：實際執行抓取 Pixiv、Gemini 翻譯以及發送信件等耗時且消耗 CPU 的工作。
- **Cloud Tasks**：確保非同步作業的穩定性與重試機制。

---

## 預先準備 (Prerequisites)

不管選擇哪一種部署方式，你都需要取得以下資訊：
1. **Discord 開發者帳號**：至 [Discord Developer Portal](https://discord.com/developers/applications) 建立一個 Application。
   - 取得 `Public Key`、`Application ID` 與 `Bot Token`。
2. **Pixiv Refresh Token**：
   - 需透過瀏覽器 Cookie 或指令碼取得自己的 Pixiv 帳號的 `Refresh Token` 供機器人存取被鎖定或需要登入的小說。
3. **Gemini API Key**：
   - 如果你需要翻譯功能，請至 [Google AI Studio](https://aistudio.google.com/) 取得免費的 Gemini API Key。
4. **SMTP 寄信伺服器**：
   - 強烈建議使用 SendGrid、Mailgun 等寄信服務，也可以使用 Gmail 的「應用程式密碼」。主要用於將 EPUB 大檔作為附件寄給你的 `@kindle.com` 信箱。
5. **你的 Kindle Email**：
   - 前往 Amazon 設定頁面取得你專屬的 Send-to-Kindle Email（結尾是 `@kindle.com`）。

---

## 環境變數 (.env)

你需要在專案根目錄建立一個 `.env` 檔案，內容可參考 `.env.example`。

```ini
# --- Application ---
APP_ENV=prod
LOG_LEVEL=INFO

# --- Discord ---
DISCORD_PUBLIC_KEY="你的 Discord Public Key"
DISCORD_APPLICATION_ID="你的 Application ID"
DISCORD_BOT_TOKEN="你的 Bot Token"
ALLOWED_DISCORD_USER_ID="只允許這名使用者的查閱與執行 (填寫使用者 ID 放行)"

# --- Pixiv ---
PIXIV_REFRESH_TOKEN="你的 Pixiv Refresh Token"

# --- Kindle / SMTP ---
KINDLE_EMAIL="your-name@kindle.com"
SMTP_HOST="smtp.gmail.com"  # 或者 smtp.sendgrid.net 等
SMTP_PORT=587
SMTP_USERNAME="寄件者信箱或帳號"
SMTP_PASSWORD="應用程式密碼或密碼"
SMTP_FROM="與寄件者信箱相同的 Sender Address"

# --- Translation ---
TRANSLATION_PROVIDER="gemini" # 目前支援 "gemini" 或 "noop"
GEMINI_API_KEY="你的 Gemini API Key"
GEMINI_MODEL="gemini-2.5-flash"
GEMINI_MAX_CHARS_PER_BATCH=4000 # 控制每個批次被打包送給翻譯的字元上限以提升翻譯品質

# --- FastAPI 基礎配置 ---
INTERNAL_API_TOKEN="自己亂數產生的一個密碼，保護 API 被除了 Worker 以外的人呼叫"
```

> **注意：如果使用 Cloud Run**，請將上述環境變數同時設定進 Cloud Run 的 Environment Variables 或 GCP Secret Manager 中。

---

## 部署與啟動方式

### 方法一：使用 VM / VPS (Local 部署)

1. **安裝依賴** (推薦使用 Python 3.11+)
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   pip install -e .
   ```

2. **確認 Queue 設定** (在 `.env` 中)
   確保你將 `QUEUE_BACKEND` 設定為了 `local`：
   ```ini
   QUEUE_BACKEND=local
   ```

3. **啟動 FastAPI**
   ```bash
   uvicorn apps.api_server.main:app --host 0.0.0.0 --port 8080
   ```

4. **設定 Discord Interactions Endpoint**
   使用 ngrok 或是反向代理 (Nginx) 加上 SSL 憑證，暴露出該主機的 port 8080。
   去 Discord Publisher Portal，將 `Interactions Endpoint URL` 設定為 `https://你的網域/api/interactions`。

---

### 方法二：GCP Cloud Run + Cloudflare Workers

1. **部署 Cloud Run (Docker)**
   專案內包含了對應的 `Dockerfile`。你可以直接透過 `gcloud` 指令從源碼部署：
   ```bash
   gcloud run deploy pixiv2kindle \
     --source . \
     --region asia-east1 \
     --allow-unauthenticated \
     --set-env-vars="QUEUE_BACKEND=cloud_tasks,INTERNAL_API_TOKEN=你的亂碼密碼,CLOUD_TASKS_PROJECT_ID=你的GCP專案,..." 
     # 或於平台介面上掛載環境變數
   ```
   *部署完成後，請記錄低下你專屬的 Cloud Run URL (例如 `https://pixiv2kindle-xxx-de.a.run.app`)*

2. **建立 Cloud Tasks 佇列**
   ```bash
   gcloud tasks queues create pixiv2kindle-queue --location=asia-east1
   ```
   請確定 `.env` 或是 Cloud Run 裡的環境變數 `CLOUD_TASKS_QUEUE_NAME` 設定與這個相符。

3. **部署 Cloudflare Workers**
   編輯 `apps/worker_gateway/wrangler.toml`：
   ```toml
   name = "pixiv2kindle-gateway"
   main = "src/index.ts"
   compatibility_date = "2024-03-01"

   [vars]
   BACKEND_QUEUE_URL = "https://你的-cloud-run-網址/api/queue/enqueue"
   INTERNAL_API_TOKEN = "對應你在 .env 的 INTERNAL_API_TOKEN"
   ```
   你可以透過 Secrets 管理放入 `DISCORD_PUBLIC_KEY`：
   ```bash
   cd apps/worker_gateway
   npx wrangler secret put DISCORD_PUBLIC_KEY
   ```
   最後發布 Worker：
   ```bash
   npx wrangler deploy
   ```

4. **設定 Discord Interactions Endpoint**
   到 Discord Developer Portal，將你剛剛發布的 Cloudflare Worker URL 設定為 `Interactions Endpoint URL`。

---

## 如何使用

加入你的機器人到伺服器後，你可以使用以下指令：

- **原文轉檔並送至 Kindle**：
  ```
  /pixiv2kindle novel:https://www.pixiv.net/novel/show.php?id=12345678
  ```
- **原文翻譯並產生雙語對照 EPUB**：
  ```
  /pixiv2kindle novel:12345678 translate:True target_lang:zh-TW
  ```

祝您閱讀愉快！

---

## 致謝 (Acknowledgments)

本專案的 **Gemini 翻譯核心邏輯** 與 **打批次策略 (Batch Packing)** 大致參考並借鑑了開源的 [shinkansen](https://github.com/jimmysu0309/shinkansen) 專案。特別感謝其關於「雙重門檻分批」及「純文字分隔符協定」等穩定性設計，讓我們徹底解決了 LLM 處理長篇日文小說時的 JSON 解析失敗與漏斷落問題。
