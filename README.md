# WarHub — 戰爭預測情報中心

整合 OSINT（開源情報）的地緣政治衝突監控平台，正式上線於 [warhubs.com](https://warhubs.com/)。

本專案包含兩個子系統：

| 子系統 | 路徑 | 技術 | 用途 |
|--------|------|------|------|
| **ConflictWatch** | [`conflictwatch/`](./conflictwatch) | Python (FastAPI) + HTML | 後端資料抓取 + 獨立儀表板 |
| **WARWATCH** | [`wordpress/`](./wordpress) | WordPress 主題 | 正式網站前端（warhubs.com） |

---

## 專案結構

```
warhub/
├── README.md                       # 你正在讀的這個檔案
├── .gitignore
├── .env.example                    # ConflictWatch 環境變數範本
│
├── .github/
│   └── workflows/
│       └── fetch.yml               # 每 15 分鐘自動執行 fetcher.py
│
├── conflictwatch/                  # === Python 後端與獨立儀表板 ===
│   ├── README.md                   # ConflictWatch 安裝與架構說明
│   ├── requirements.txt
│   ├── backend/
│   │   ├── fetcher.py              # 資料抓取（Polymarket + Google Popular Times）
│   │   ├── server.py               # FastAPI 伺服器
│   │   └── alerts.py               # Telegram / Discord 警報推播
│   └── frontend/
│       └── index.html              # 獨立儀表板
│
└── wordpress/                      # === WordPress 主題（線上網站）===
    ├── README.md                   # WordPress 安裝指南
    ├── page-warwatch.php           # 頁面範本
    ├── functions.php               # 完整 Astra functions.php（含 WARWATCH 程式碼）
    ├── functions-warwatch.php      # 僅 WARWATCH 部分（貼至既有 functions.php 末尾）
    ├── warwatch.css
    ├── warwatch.js
    ├── war-prediction-dashboard.html
    ├── wp-config.example.php       # wp-config 範本（敏感資訊已移除）
    └── archive/                    # 舊版本備份
        ├── page-warwatch.old.php
        ├── warwatch.old.css
        └── warwatch.old.js
```

---

## 核心功能

| 模組 | 描述 |
|------|------|
| **WPI v2.0** | War Pressure Index — 加權多源指數，每 10 分鐘更新 |
| **PizzINT** | 五角大廈披薩外送異常監控（Pentagon Pizza Index）|
| **Polymarket** | 預測市場機率聚合 |
| **AVI** | 軍機 / 加油機航空監控（ADS-B）|
| **FIRMS** | NASA 衛星火點資料 |
| **避險指標** | 黃金 / 布倫特原油 / VIX |
| **熱點地圖** | 俄烏、中東、台海等衝突區即時狀態 |
| **末日時鐘** | 距午夜倒數 |

---

## 快速開始

### ConflictWatch（Python 後端）

```bash
cd conflictwatch
pip install -r requirements.txt
cp ../.env.example .env       # 填入你的 API key
python backend/server.py
# 開啟 http://localhost:8000
```

詳細說明見 [`conflictwatch/README.md`](./conflictwatch/README.md)。

### WARWATCH（WordPress 主題）

把 `wordpress/` 內的檔案上傳到 WordPress 主題目錄。

詳細安裝步驟見 [`wordpress/README.md`](./wordpress/README.md)。

---

## 安全提醒

- ⚠️ **絕對不要把真實的 `wp-config.php` 推到公開儲存庫**。本倉庫只保留 `wp-config.example.php`，敏感資料皆為佔位符。
- ⚠️ API key、Telegram token、Discord webhook 等請放在 `.env`（已被 `.gitignore` 排除）。

---

## 免責聲明

本網站資訊僅供研究與觀察用途，不構成任何投資、軍事或政策建議。Pizza 指數為民間 OSINT 觀察，非官方情報；Polymarket 數據反映市場參與者預測，非事實。
