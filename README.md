# WarHub — 戰爭預測情報中心

整合 OSINT（開源情報）的地緣政治衝突監控平台，原網站 [warhubs.com](https://warhubs.com/)。

**架構**：純靜態網站（HTML + CSS + JS）+ GitHub Actions 自動更新資料 + GitHub Pages 部署。

---

## 專案結構

```
warhub/
├── index.html                     # 主頁面（戰爭預測儀表板）
├── data/
│   └── data.json                  # 由 GitHub Actions 每 15 分鐘自動更新
├── scripts/
│   ├── fetch_data.py              # 抓取 Polymarket + Pizza 指數
│   ├── alerts.py                  # Telegram / Discord 警報推播
│   └── requirements.txt
├── .github/
│   └── workflows/
│       ├── update-data.yml        # 每 15 分鐘執行 fetch_data.py
│       └── deploy.yml             # push 到 main 自動部署到 GitHub Pages
├── .env.example                   # 本地開發用環境變數範本
└── .gitignore
```

---

## 核心功能

| 模組 | 描述 |
|------|------|
| **WPI v2.0** | War Pressure Index — 加權多源指數 |
| **PizzINT** | 五角大廈披薩外送異常監控（Pentagon Pizza Index）|
| **Polymarket** | 預測市場機率聚合 |
| **AVI** | 軍機 / 加油機航空監控（ADS-B）|
| **FIRMS** | NASA 衛星火點資料 |
| **避險指標** | 黃金 / 布倫特原油 / VIX |
| **熱點地圖** | 俄烏、中東、台海衝突區即時狀態 |
| **末日時鐘** | 距午夜倒數 |

---

## 部署到 GitHub Pages

1. **Settings → Pages → Source** 選 `GitHub Actions`
2. 將程式碼推到 `main` 分支
3. `deploy.yml` 會自動部署
4. 完成後可在 `https://<username>.github.io/warhub/` 看到網站

### 自訂網域（warhubs.com）

於 GitHub 倉庫 **Settings → Pages → Custom domain** 填入 `warhubs.com`，並到 DNS 設定加入：
- `A` record 指向 GitHub Pages IPs
- 或 `CNAME` 指向 `<username>.github.io`

---

## 設定資料抓取

在 GitHub 倉庫 **Settings → Secrets and variables → Actions** 新增（皆為選用）：

| Secret | 用途 |
|--------|------|
| `GOOGLE_MAPS_API_KEY` | 取得 Pizza 店繁忙度（沒設定時用模擬資料）|
| `TELEGRAM_BOT_TOKEN` | 警報推播到 Telegram |
| `TELEGRAM_CHAT_ID` | Telegram 接收頻道 |
| `DISCORD_WEBHOOK_URL` | 警報推播到 Discord |

`update-data.yml` 會每 15 分鐘執行 `scripts/fetch_data.py`，把結果寫入 `data/data.json` 並 commit。

---

## 接上真實 Pizza 資料（Google Maps API）

預設情況下 Pizza 指數使用模擬資料。要接上真實的 Pentagon 周邊披薩店繁忙度，需要四個步驟：

### 1. 申請 Google Cloud API key

1. 到 [Google Cloud Console](https://console.cloud.google.com/) 建立或選擇一個專案
2. 啟用 **Places API**（左側選單 → APIs & Services → Library → 搜尋 Places API → Enable）
3. 建立 API key（左側選單 → APIs & Services → Credentials → Create Credentials → API key）
4. 強烈建議**限制這把 key 只能用 Places API**

> ⚠️ 費用：Places API 每月 $200 免費額度。本專案每 15 分鐘抓 6 家店，約佔 ~$73/月（在免費額度內）。

### 2. 找出真實的 Place ID

在本機執行：

```bash
export GOOGLE_MAPS_API_KEY=你的key
pip install -r scripts/requirements.txt requests
python scripts/find_places.py
```

它會在 Pentagon 周邊 5 km 內搜尋，列出每家店的 `place_id` 候選，並輸出可貼回 `fetch_data.py` 的程式片段。

### 3. 更新 `scripts/fetch_data.py`

把上一步輸出的 `PIZZA_SHOPS = [...]` 區塊整個取代到 `fetch_data.py` 裡。

### 4. 把 API key 設為 GitHub Secret

GitHub 倉庫 → Settings → Secrets and variables → Actions → New repository secret：

- Name: `GOOGLE_MAPS_API_KEY`
- Value: 你的 API key

下次 `update-data.yml` 執行時（每 15 分鐘），就會抓真實資料。也可以到 Actions 頁面手動觸發 "Update data" workflow 立即生效。

---

## 本地開發

```bash
# 1. 抓資料
pip install -r scripts/requirements.txt
python scripts/fetch_data.py

# 2. 預覽網站
python -m http.server 8000
# 開啟 http://localhost:8000
```

---

## 免責聲明

本網站資訊僅供研究與觀察用途，不構成任何投資、軍事或政策建議。Pizza 指數為民間 OSINT 觀察，非官方情報；Polymarket 數據反映市場參與者預測，非事實。
