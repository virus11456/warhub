# WARWATCH — WordPress 上線安裝指南

## 檔案清單與放置位置

```
/wp-content/themes/你的主題/
├── css/
│   └── warwatch.css          ← CSS 樣式
├── js/
│   └── warwatch.js           ← 前端邏輯（Pizza 警報 + Polymarket fetch）
├── page-warwatch.php         ← 頁面範本（放佈景主題根目錄）
└── functions.php             ← 把 functions-warwatch.php 內容貼入
```

---

## 安裝步驟（5分鐘完成）

### Step 1 — 上傳檔案
```
warwatch.css  → /wp-content/themes/your-theme/css/warwatch.css
warwatch.js   → /wp-content/themes/your-theme/js/warwatch.js
page-warwatch.php → /wp-content/themes/your-theme/page-warwatch.php
```

### Step 2 — 更新 functions.php
打開 `/wp-content/themes/your-theme/functions.php`，
將 `functions-warwatch.php` 的**全部內容**貼到檔案**最底部**。

### Step 3 — 建立頁面
1. WordPress 後台 → 頁面 → 新增頁面
2. 標題：`WARWATCH 戰爭預測情報中心`
3. 右側「頁面屬性」→ 範本：選「**WARWATCH 戰爭預測情報中心**」
4. 發布

### Step 4 — 完成！
訪問頁面 URL，儀表板即上線。

---

## 管理面板

後台出現「🍕 WARWATCH」選單：
- **手動更新披薩繁忙度**（直接輸入 Google Maps 觀察到的數值）
- **立即刷新 Polymarket**（或等 WP Cron 每小時自動執行）

---

## 功能說明

### 披薩異常警報邏輯
| busyness % | 狀態 |
|---|---|
| < 40 | NORMAL（綠色，無警報） |
| 40–59 | ELEVATED（黃色） |
| 60–69 | HIGH（橘色，顯示警告橫幅） |
| ≥ 70 | ANOMALY（觸發紅色戰爭警報） |

**2 家以上**店家達到 ANOMALY → 觸發「WAR ALERT」紅色橫幅 + 卡片脈衝動畫

### Polymarket 數據更新
- WP Cron 每小時自動執行，存入 `wp_options`
- 前端 JS 每 5 分鐘呼叫 Polymarket Gamma API（公開，不需 key）
- Fallback：若 API 無法連線，顯示 WP Options 中的靜態快取

### REST API
```
GET  /wp-json/warwatch/v1/pizza       → 當前披薩數據
POST /wp-json/warwatch/v1/pizza       → 更新（需管理員 cookie）
GET  /wp-json/warwatch/v1/polymarket  → Polymarket 快取數據
```

---

## 隱藏主題 Header/Footer

頁面範本已自動加入 `body.warwatch-fullpage` class。
在你的佈景主題 CSS 或 Additional CSS 加入：

```css
body.warwatch-fullpage .site-header,
body.warwatch-fullpage .site-footer,
body.warwatch-fullpage #colophon { display: none !important; }
body.warwatch-fullpage { background: #050a0e !important; }
body.warwatch-fullpage #page { margin: 0; padding: 0; }
```

（不同主題的 class 名稱可能不同，依實際主題調整）

---

## 讓頁面佔全螢幕（推薦搭配 Elementor）

如果使用 Elementor，直接用「Elementor Canvas」範本，
然後在頁面內貼入 `[warwatch_dashboard]` shortcode。

或用 Elementor Pro 的自訂頁面範本 → 隱藏 header/footer。

---

## 常見問題

**Q: Polymarket API 被封鎖？**
A: 台灣不在封鎖名單，通常可直接連。若有問題，改用 WP Cron 伺服器端抓取（已在 functions.php 實作）。

**Q: 披薩數據要去哪裡看真實數值？**
A: 前往 [pizzint.watch](https://pizzint.watch) 或 Google Maps 搜尋各店，查看「熱門時段 Live」百分比後手動填入後台。

**Q: 如何讓 Polymarket 顯示台灣相關題目？**
A: `warwatch.js` 的 `WAR_KEYWORDS` 陣列已包含 `Taiwan`，會自動篩選。

**Q: 可以嵌入到 iframe 嗎？**
A: 可以，在 functions.php 加入 `remove_action('send_headers', 'send_frame_options_header');` 即可。
