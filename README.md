# 🍕📊 ConflictWatch — 衝突指標觀測站

結合 **Pentagon Pizza Index (OSINT)** 與 **Polymarket 預測市場** 的戰爭風險儀表板。

---

## 架構總覽

```
┌─────────────────────────────────────────────────────────────┐
│                    ConflictWatch 架構                        │
├─────────────────┬───────────────────┬───────────────────────┤
│   數據來源       │   後端處理         │   前端呈現             │
│                 │                   │                       │
│  Polymarket     │  fetcher.py       │  index.html           │
│  Gamma API ────►│  (async aiohttp)  │  + Chart.js           │
│                 │         │         │  + 即時 API 呼叫       │
│  Google Maps    │         ▼         │                       │
│  Popular Times ►│  SQLite DB        │  儀表板元素：           │
│  (populartimes) │  ┌─────────────┐  │  • 綜合威脅指數        │
│                 │  │ snapshots   │  │  • Pizza 店狀態        │
│  @PenPizzaReport│  │ poly_data   │  │  • Polymarket 列表    │
│  (手動 / RSS) ──►│  │ combined    │  │  • 24H 趨勢圖         │
│                 │  └─────────────┘  │  • 末日時鐘            │
└─────────────────│         │         └───────────────────────┘
                  │         ▼
                  │  FastAPI server.py
                  │  GET /api/latest
                  │  GET /api/history
                  │  GET /api/polymarket/top
                  │         │
                  │         ▼
                  │  alerts.py
                  │  Telegram Bot ──► 你的手機
                  │  Discord Webhook ─► 你的伺服器
                  │
                  │  GitHub Actions (cron: */15 * * * *)
                  │  自動每15分鐘執行 fetcher.py
```

---

## 快速開始

### 1. 安裝依賴
```bash
git clone https://github.com/your-repo/conflictwatch
cd conflictwatch
pip install -r requirements.txt
```

### 2. 設定環境變數
```bash
cp .env.template .env
# 編輯 .env，填入：
# - GOOGLE_MAPS_API_KEY（取得 Popular Times 數據）
# - TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID（推播警報）
# - DISCORD_WEBHOOK_URL（Discord 推播）
```

### 3. 取得 Google Maps API Key
1. 前往 [Google Cloud Console](https://console.cloud.google.com)
2. 啟用 **Places API**
3. 建立 API Key（限制 Places API 範圍）
4. 填入 `.env` 的 `GOOGLE_MAPS_API_KEY`

### 4. 找到五角大廈披薩店的 Place ID
```python
import requests
# 搜尋 Pentagon 附近 Domino's
r = requests.get(
    "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
    params={
        "location": "38.8719,-77.0563",  # Pentagon 座標
        "radius": 3000,
        "keyword": "dominos pizza",
        "key": "YOUR_API_KEY"
    }
)
for p in r.json()["results"]:
    print(p["place_id"], p["name"], p["vicinity"])
```
把找到的 `place_id` 填入 `backend/fetcher.py` 的 `PIZZA_SHOPS` 列表。

### 5. 啟動伺服器
```bash
cd backend
python server.py
# 開啟 http://localhost:8000
```

### 6. 設定 GitHub Actions 自動抓取
在 GitHub repo 的 **Settings → Secrets** 新增：
- `GOOGLE_MAPS_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `DISCORD_WEBHOOK_URL`

然後啟用 `.github/workflows/fetch.yml`。

---

## Polymarket Gamma API

官方文件：https://gamma-api.polymarket.com/docs

```python
import requests

# 取得所有開放市場
r = requests.get("https://gamma-api.polymarket.com/markets", params={
    "active": "true",
    "tag_slug": "geopolitics",
    "limit": 100
})
markets = r.json()

# 每個市場的結構：
# {
#   "id": "...",
#   "question": "Will Israel attack Iran before Q2 2026?",
#   "outcomes": [{"name":"Yes","price":"0.28"},{"name":"No","price":"0.72"}],
#   "volume": 8200000,
#   "endDate": "2026-06-30T00:00:00Z"
# }
```

---

## 綜合威脅指數計算公式

```
Pizza Score (0-100)
  = 各店當前繁忙度的平均值
  （Google Popular Times 返回 0-100 百分比）

Polymarket Score (0-100)
  = Σ(市場YES機率 × 成交量) / Σ(成交量)
  （按交易量加權的平均機率，再 ×100）

Combined Score
  = Pizza Score × 0.40 + Polymarket Score × 0.60

警戒等級：
  ≥ 70 → CRITICAL  🔴
  ≥ 50 → HIGH      🟠
  ≥ 30 → ELEVATED  🟡
  < 30 → NORMAL    🟢
```

---

## V2 擴充功能

| 功能 | 實作方式 |
|------|----------|
| FlightRadar24 偵察機追蹤 | `adsbexchange.com` API 或 RapidAPI FlightRadar |
| 黃金/石油避險指標 | `yfinance` 抓取 GLD, USO ETF 價格 |
| X (Twitter) 戰爭關鍵字熱度 | Twitter API v2 `search/recent` |
| Kalshi 數據（美國監管版）| `kalshi.com/api/v2/markets` |
| AI 情緒分析 | Claude API 分析 OSINT 貼文情緒 |
| 多語言警報 | 中/英/日 推播 |

---

## 部署選項

| 平台 | 費用 | 適合 |
|------|------|------|
| **Vercel** (前端) + **Railway** (後端) | 免費起 | 輕量部署 |
| **Cloudflare Pages** + **Supabase** | 免費起 | 無伺服器 |
| **GitHub Pages** (純靜態 + Actions) | 完全免費 | 最簡單 |
| **VPS (Hetzner/DigitalOcean)** | $5/月起 | 完整控制 |

---

## 免責聲明

本工具僅供教育與研究用途。Pizza 指數是民間 OSINT 觀察，非官方情報。Polymarket 數據反映市場參與者預測，非事實。不構成任何投資、軍事或政策建議。
