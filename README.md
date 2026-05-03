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
