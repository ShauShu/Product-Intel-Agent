# Product Intel Agent — 技術文件

產品競品與市場情報員。一個基於 Google ADK + MCP 框架的多智能體系統，每天自動搜集競品動態、與自家產品規格比對，並產出結構化的競爭分析報告。

---

## 目錄

1. [系統架構](#1-系統架構)
2. [目錄結構](#2-目錄結構)
3. [核心元件說明](#3-核心元件說明)
4. [MCP 工具層](#4-mcp-工具層)
5. [資料模型](#5-資料模型)
6. [API 規格](#6-api-規格)
7. [環境變數](#7-環境變數)
8. [本地開發](#8-本地開發)
9. [部署至 Google Cloud](#9-部署至-google-cloud)
10. [基礎設施資源](#10-基礎設施資源)
11. [依賴套件](#11-依賴套件)

---

## 1. 系統架構

```
使用者 / Cloud Scheduler
        │
        ▼ POST /analyze
┌─────────────────────────────────────────┐
│           FastAPI 應用伺服器             │
│         (fast_api_app.py)               │
│                                         │
│  ┌──────────────────────────────────┐   │
│  │       ADK Runner + Session       │   │
│  │   (InMemory / Vertex AI Memory)  │   │
│  └──────────────┬───────────────────┘   │
└─────────────────┼───────────────────────┘
                  │
                  ▼
     ┌────────────────────────┐
     │  product_intel_agent   │  ← 根 Orchestrator
     │  (gemini-2.0-flash)    │
     └──────┬─────────────────┘
            │ 依序委派
     ┌──────▼──────┐     ┌──────────────┐
     │  Researcher  │ ──► │   PM Lead    │
     │   Agent      │     │   Agent      │
     └──────┬───────┘     └──────┬───────┘
            │                    │
     ┌──────▼───────┐    ┌───────▼──────────┐
     │ Search MCP   │    │ KnowledgeBase MCP │
     │ Scraper MCP  │    │ (agent/docs/*.md) │
     └──────────────┘    └──────────────────┘
```

**執行流程：**

1. `/analyze` 收到競品名稱請求
2. Orchestrator 委派給 **Researcher Agent**，使用搜尋與爬蟲工具蒐集原始情報
3. Researcher 的結果透過 `output_key="researcher_findings"` 傳遞給 **PM Lead Agent**
4. PM Lead 讀取自家產品文件，進行比對分析，輸出 `CompetitorIntelReport`
5. 結果回傳給呼叫端；若啟用 Vertex AI Memory，本次對話會被記憶以避免重複報告

---

## 2. 目錄結構

```
product-intel-agent/
├── agent/
│   ├── __init__.py
│   ├── agent.py                        # 智能體定義、提示詞、資料模型
│   ├── fast_api_app.py                 # FastAPI 伺服器、Runner、記憶庫連線
│   ├── app_utils/
│   │   ├── __init__.py
│   │   └── env.py                      # 環境變數統一讀取
│   ├── docs/
│   │   └── my_product_spec.md          # 自家產品規格書（需自行填寫）
│   └── tools/
│       ├── __init__.py
│       ├── mcp_config.py               # MCP 工具連線設定
│       └── web_scraper_mcp/
│           ├── search_server.py        # Serper.dev 搜尋 MCP 伺服器
│           ├── scraper_server.py       # 網頁爬蟲 MCP 伺服器
│           ├── knowledge_base_server.py # 本地知識庫 MCP 伺服器
│           └── requirements.txt        # MCP 子進程依賴
├── deployment/
│   └── terraform/
│       └── main.tf                     # 完整 GCP 基礎設施定義
├── .env                                # 本地機密（不提交 Git）
├── .gitignore
├── Dockerfile
└── pyproject.toml
```

---

## 3. 核心元件說明

### `agent/agent.py`

系統的大腦，定義三個 LlmAgent 與一個 Pydantic 輸出模型。

| 元件 | 類型 | 模型 | 工具 | 輸出 Key |
|------|------|------|------|----------|
| `market_researcher` | LlmAgent | gemini-2.0-flash | Search MCP, Scraper MCP | `researcher_findings` |
| `pm_lead` | LlmAgent | gemini-2.0-flash | KnowledgeBase MCP | `intel_report` |
| `product_intel_agent` | LlmAgent (Orchestrator) | gemini-2.0-flash | — (sub_agents) | — |

**智能體提示詞設計原則：**

- Researcher：強調「去噪」，只萃取新功能發布、定價變動、重大合作，忽略行銷話術
- PM Lead：強調「可行動性」，報告直送 CPO，必須嚴格遵守輸出 Schema
- 兩者都內建記憶檢查邏輯：7 天內已報告的競品動態，改為追蹤市場反應而非重複報告

### `agent/fast_api_app.py`

HTTP 入口與 ADK 執行環境。

- 使用 `InMemorySessionService` 管理對話 Session
- 若 `MEMORY_BANK_ID` 有設定，自動啟用 `VertexAiMemoryBankService` 實現跨 Session 長期記憶
- 若未設定，自動降級為無記憶模式，方便本地測試，不影響功能

### `agent/app_utils/env.py`

所有環境變數的單一讀取點，避免各模組散落 `os.getenv()` 呼叫。

---

## 4. MCP 工具層

所有工具均透過 **Model Context Protocol (MCP)** 標準化，以 `stdio` 子進程方式運行，由 `McpToolset` 統一管理連線。

### 工具一覽

| 工具名稱 | 伺服器檔案 | 傳輸方式 | Timeout | 用途 |
|----------|-----------|----------|---------|------|
| `competitor_search_tool` | `search_server.py` | stdio | 60s | 搜尋競品新聞 |
| `web_scraper_tool` | `scraper_server.py` | stdio | 60s | 讀取網頁全文 |
| `list_product_docs` | `knowledge_base_server.py` | stdio | 30s | 列出自家產品文件 |
| `read_product_doc` | `knowledge_base_server.py` | stdio | 30s | 讀取指定文件內容 |

### `competitor_search_tool`

```
輸入：query (str), num_results (int, 預設 10)
輸出：list[{title, link, snippet}]
外部依賴：Serper.dev API（需 SERPER_API_KEY）
```

呼叫 `https://google.serper.dev/search`，回傳 Google 搜尋結果的標題、連結與摘要。

### `web_scraper_tool`

```
輸入：url (str)
輸出：{title, content} 或 {error}
內容上限：8,000 字元（避免超出 LLM context window）
```

使用 `httpx` 抓取網頁，`BeautifulSoup` 移除 `script`、`style`、`nav`、`footer`、`header` 標籤後萃取純文字。

### `list_product_docs` / `read_product_doc`

```
list_product_docs()
  輸出：list[str]  ← agent/docs/ 下所有 .md 檔名

read_product_doc(filename: str)
  輸出：{filename, content} 或 {error}
  路徑：由環境變數 DOCS_PATH 控制，預設為 agent/docs/
```

### MCP 連線設定（`mcp_config.py`）

所有工具均透過 `uv run <server_path>` 啟動，確保在隔離環境中執行：

```python
# 以 search_server 為例
StdioConnectionParams(
    server_params=StdioServerParameters(
        command="uv",
        args=["run", "agent/tools/web_scraper_mcp/search_server.py"],
        env={**os.environ, "SERPER_API_KEY": api_key},
    ),
    timeout=60.0,
)
```

**重要：** 所有 MCP 伺服器的 log 均強制輸出至 `sys.stderr`，避免污染 `stdout` 的 MCP 通訊協定。

---

## 5. 資料模型

### `CompetitorIntelReport`

PM Lead Agent 的強制輸出格式（Pydantic BaseModel + `output_schema`）：

```python
class CompetitorIntelReport(BaseModel):
    competitor_name: str          # 競品名稱
    new_feature_summary: str      # 新功能摘要
    pricing_change: Optional[str] # 定價變動（無則為 null）
    threat_level: Literal[        # 威脅等級
        "low",      # 與核心市場無關
        "medium",   # 有路線圖可回應
        "high",     # 影響用戶留存的功能差距
        "critical"  # 直接複製我方核心差異化優勢
    ]
    our_counter_strategy: str     # 具體反制策略
    source_urls: list[str]        # 情報來源 URL
    already_reported: bool        # 7 天內是否已報告過
```

---

## 6. API 規格

### `POST /analyze`

觸發競品情報分析。

**Request Body：**
```json
{
  "competitor": "Notion",
  "session_id": "default",
  "user_id": "default-user"
}
```

| 欄位 | 類型 | 必填 | 說明 |
|------|------|------|------|
| `competitor` | string | ✅ | 競品名稱或搜尋關鍵字 |
| `session_id` | string | ❌ | 對話 Session ID，預設 `"default"` |
| `user_id` | string | ❌ | 使用者 ID，預設 `"default-user"` |

**Response：**
```json
{
  "competitor": "Notion",
  "report": "{ ...CompetitorIntelReport JSON... }"
}
```

**Error Response：**
```json
{
  "detail": "錯誤訊息"
}
```

### `GET /health`

健康檢查端點，供 Cloud Run 使用。

**Response：**
```json
{ "status": "ok" }
```

---

## 7. 環境變數

| 變數名稱 | 必填 | 說明 | 取得方式 |
|----------|------|------|----------|
| `GOOGLE_CLOUD_PROJECT` | ✅ | GCP 專案 ID | GCP Console |
| `GOOGLE_CLOUD_LOCATION` | ❌ | 部署區域，預設 `us-central1` | — |
| `SERPER_API_KEY` | ✅ | 搜尋 API 金鑰 | [serper.dev](https://serper.dev) |
| `MEMORY_BANK_ID` | ❌ | Vertex AI 記憶庫 ID，未設定則停用長期記憶 | Terraform output |
| `AI_ASSETS_BUCKET` | ❌ | GCS Bucket 名稱 | Terraform output |

本地開發時，將上述變數填入 `.env` 檔案（已加入 `.gitignore`，不會提交）。

---

## 8. 本地開發

### 前置需求

- Python 3.12+
- [uv](https://astral.sh/uv) 套件管理器
- Google Cloud CLI（已登入：`gcloud auth application-default login`）
- Serper.dev API Key

### 安裝與啟動

```cmd
REM 1. 安裝依賴
uv sync

REM 2. 填入環境變數
copy .env .env.local
REM 編輯 .env.local，填入實際值

REM 3. 啟動開發伺服器（含 hot-reload）
uv run uvicorn agent.fast_api_app:app --reload --port 8080
```

### 測試 API

```cmd
REM 分析單一競品
curl -X POST http://localhost:8080/analyze -H "Content-Type: application/json" -d "{\"competitor\": \"Notion\", \"session_id\": \"test-001\"}"

REM 健康檢查
curl http://localhost:8080/health
```

### 新增自家產品文件

在 `agent/docs/` 目錄下新增 `.md` 檔案，PM Lead Agent 會自動透過 `list_product_docs()` 發現並讀取：

```cmd
REM 範例：新增競品比較文件
copy agent\docs\my_product_spec.md agent\docs\competitor_comparison.md
```

---

## 9. 部署至 Google Cloud

### 步驟一：建置並推送 Docker 映像檔

```cmd
REM 設定變數
set PROJECT_ID=your-gcp-project-id
set REGION=us-central1
set IMAGE_URI=%REGION%-docker.pkg.dev/%PROJECT_ID%/product-intel/product-intel-agent:latest

REM 建置映像檔
docker build -t %IMAGE_URI% .

REM 推送至 Artifact Registry
docker push %IMAGE_URI%
```

### 步驟二：初始化 Terraform

```cmd
cd deployment\terraform
terraform init
cd ..\..\n```

### 步驟三：部署基礎設施

```cmd
set SERPER_API_KEY=your-serper-api-key

cd deployment\terraform
terraform apply ^
  -var="project_id=%PROJECT_ID%" ^
  -var="region=%REGION%" ^
  -var="image_uri=%IMAGE_URI%" ^
  -var="serper_api_key=%SERPER_API_KEY%"
cd ..\..\n```

Terraform 完成後會輸出：
- `cloud_run_url`：Cloud Run 服務 URL
- `ai_assets_bucket`：GCS Bucket 名稱

### 步驟四：設定 Vertex AI 記憶庫（選用）

```cmd
REM 在 GCP Console 建立 Memory Bank 後，更新 Cloud Run 環境變數
gcloud run services update product-intel-agent ^
  --update-env-vars MEMORY_BANK_ID=your-memory-bank-id ^
  --region %REGION%
```

### 常用指令速查

| 用途 | 指令 |
|------|------|
| 安裝 Python 依賴 | `uv sync` |
| 啟動本地開發伺服器 | `uv run uvicorn agent.fast_api_app:app --reload --port 8080` |
| 建置 Docker 映像檔 | `docker build -t %IMAGE_URI% .` |
| 推送映像檔 | `docker push %IMAGE_URI%` |
| 初始化 Terraform | `cd deployment\terraform && terraform init` |
| 部署（Terraform Apply） | `cd deployment\terraform && terraform apply ...` |

---

## 10. 基礎設施資源

由 `deployment/terraform/main.tf` 管理，所有資源均在同一 GCP 專案下：

| 資源 | 類型 | 說明 |
|------|------|------|
| `product-intel-agent` | Cloud Run v2 Service | 主要應用服務，按需計費 |
| `product-intel-daily` | Cloud Scheduler Job | 每天 08:30（台北時間）自動觸發 |
| `serper-api-key` | Secret Manager Secret | 安全儲存 Serper API Key |
| `{project_id}-intel-assets` | GCS Bucket | 儲存 AI 生成資產 |
| `intel-scheduler-sa` | Service Account | Cloud Scheduler 專用，僅有 `roles/run.invoker` 權限 |

**自動啟用的 GCP API：**
- `run.googleapis.com`
- `cloudscheduler.googleapis.com`
- `secretmanager.googleapis.com`
- `artifactregistry.googleapis.com`
- `aiplatform.googleapis.com`

### 修改排程競品

編輯 `deployment/terraform/main.tf` 中的 `body` 欄位：

```hcl
body = base64encode(jsonencode({
  competitor = "your-main-competitor",  # ← 修改此處
  session_id = "scheduled"
}))
```

---

## 11. 依賴套件

### 主要依賴（`pyproject.toml`）

| 套件 | 用途 |
|------|------|
| `google-adk` | Agent 框架、Runner、Session、Memory |
| `google-genai` | Gemini 模型呼叫 |
| `mcp` | MCP 協定基礎 |
| `fastmcp` | 快速建立 MCP 伺服器 |
| `pydantic` | 輸出資料模型驗證 |
| `fastapi` + `uvicorn` | HTTP 應用伺服器 |
| `httpx` | 非同步 HTTP 客戶端（搜尋、爬蟲） |
| `beautifulsoup4` | HTML 解析與文字萃取 |
| `google-cloud-aiplatform` | Vertex AI Memory Bank |
| `google-cloud-secret-manager` | 讀取 GCP Secret |
| `python-dotenv` | 本地 `.env` 讀取 |

### MCP 子進程依賴（`web_scraper_mcp/requirements.txt`）

```
httpx==0.27.*
beautifulsoup4==4.12.*
fastmcp==2.13.*
python-dotenv==1.0.*
```

---

## 常見問題

**Q：本地測試時不想設定 Vertex AI Memory，可以嗎？**  
A：可以。只要不設定 `MEMORY_BANK_ID` 環境變數，系統會自動使用 `InMemorySessionService`，功能完全正常，只是重啟後記憶不會保留。

**Q：如何同時監控多個競品？**  
A：對 `/analyze` 發送多個請求，每個請求帶不同的 `competitor` 值。建議使用不同的 `session_id` 區隔各競品的對話記憶。

**Q：搜尋結果不夠精準怎麼辦？**  
A：修改 `agent/agent.py` 中 `RESEARCHER_PROMPT` 的搜尋指示，或在呼叫 `/analyze` 時傳入更具體的關鍵字，例如 `"Notion AI features 2025"` 而非單純的 `"Notion"`。

**Q：如何新增更多自家產品文件？**  
A：直接在 `agent/docs/` 目錄下新增 `.md` 檔案，PM Lead Agent 會在下次執行時自動發現並讀取，無需修改程式碼。
