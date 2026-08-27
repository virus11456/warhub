# WARHUBS 運維與資料說明（追溯用）

> 這份文件記錄本專案的**資料流、部署模型、資料來源與判讀原則、以及重要設定的原因**，
> 讓維護者、使用者、或未來的自動化／AI session 查 repo 就能一目了然、有跡可循。
> 程式與資料本身皆透過 PR 合併進 `main`（GitHub 有完整 commit／PR 紀錄）。

## 1. 資料更新節奏

- 排程：GitHub Actions `.github/workflows/update-data.yml`，cron **`23 */2 * * *`（每 2 小時、第 23 分）**。
  **為何不是每小時**：每小時 × 每次 ~4 分鐘 ≈ 每月 ~2,880 分鐘，超過私有 repo 免費的 **2,000 分鐘/月**，
  曾兩度在月中用爆被擋（額度用完 GitHub 會擋下後續 run，等月初重置）。改每 2 小時 ≈ 每月 ~1,500 分鐘，
  穩在額度內、不會再中途停擺。
- ⚠️ **GitHub 排程「盡力而為」**：仍可能被延後；第 23 分是為避開整點尖峰。
- 若要「更頻繁又不吃額度」，正解是設好 `GITHUB_TOKEN` 讓 `/api/data` 即時供資料（見下），
  workflow 就能維持低頻只負責把資料 commit 進 repo。
- **為何是每小時而非更頻繁 — GitHub Actions 分鐘額度**：私有 repo 每月免費 **2,000 分鐘**，
  每次 run 約需 3–6 分鐘。曾試每 30 分鐘，但月用量會逼近上限、月底恐停擺（額度用完 workflow 會暫停、
  等月初重置）。改回每小時較安全。另已優化 GDELT「快速失敗」把單次 run 從 ~6 分鐘降到 ~3 分鐘以省額度。
- 為何不是每 15 分鐘：同時考量 Actions 分鐘與 Vercel 部署次數（見下）。
- 用量查詢：GitHub 帳號 Settings → Billing → Usage（Actions）。

## 2. Vercel 部署模型

- 專案綁定 GitHub，**push 到 `main` 即自動部署 production**（warhubs.com、www.warhubs.com）。
- 免費（Hobby）方案每日部署上限約 **100 次**；每 30 分鐘的 data commit ≈ 48/天，安全。
- ⚠️ **機器人 commit 的 author email 必須是有效的 GitHub 帳號 email**
  （見 workflow 內 `git config user.email`）。否則 Vercel 會以
  「commit author email is not valid」**擋掉部署（狀態 BLOCKED）→ 網站凍結在舊快照**。
  （本專案曾因 `bot@warhub.local` 無效而卡住，改為有效 email 後解決。）
- 只有 `data/` 變動的 commit 也會照常部署（先前的 `ignoreCommand` 已移除，改走每 30 分部署更新快照）。

### （選配）即時資料 API
- `api/data.js`（Vercel Serverless）可從 GitHub 即時讀 `data/*.json`，讓資料不必等部署即最新。
- 需環境變數 `GITHUB_TOKEN`（fine-grained PAT，對本 repo 具 **Contents: Read-only**）。
- 未設定或權限不足時，前台 `wLoad()` 會自動退回「部署快照」（每 30 分更新），網站照常運作。

## 3. 資料來源與方法（含限制）

- **中國糧食／戰略物資進口**：中國自 2025 起停報 UN Comtrade → 改用**「出口國回推」**
  （把各主要出口國「對中國出口」的海關數據加總，回推中國進口量；原稱「鏡像數據」已更名）。
  - 限制：落後約 3–4 個月；近月常「資料未齊」（前台標**「資料待補」**，非「異常低」）；
    **抓不到經俄/伊等不通報管道**（石油即因此不納入）。屬慢速、看趨勢的佐證指標。
- **USDA FAS ESR**：美國對中國每週穀物出口銷售（週更、最即時的一條）。深度圖含：
  累計承諾趨勢、下單 vs 提貨（已訂未運 vs 已裝運）、美國佔中國進口比重（脫鉤訊號）。
- **其他即時源**：Polymarket、Pentagon Pizza（PizzINT）、酒吧人流（BestTime，僅美東傍晚）、
  NASA FIRMS 火點、ADS-B 軍機、GDELT/Google News、USGS 地震、FRED 信用利差、Yahoo 金融等。
- **長期封存（皆 commit 進 repo，可追溯）**：`data/metrics_daily.json`（730 天）、
  `data/food_hist.json`（60 月）、`data/strat_hist.json`、`data/pla_adiz.json`、`data/history.json` 等。

## 4. 推播（Telegram / Discord）

- 由 `scripts/alerts.py` 於每次資料更新後發送：
  - **每小時戰情回報（digest）**：綜合威脅指數＋等級、地區風險、五角大廈披薩指數＋**目前超標店家**
    （爆量/偏忙、忙碌度%、達平時%）、**全球軍機摘要**（無人機・加油機・預警機・偵察機）、
    衝突火點、最新頭條。
  - **即時異常警報**：等級升高、披薩爆量、火點激增。
- 推播頻率跟隨上面的資料排程；因此 GitHub 延後時，推播也會跟著延後（同一原因）。

## 5. 判讀原則（重要）

- 本站是**機率型的早期預警／態勢掌握工具，不是精密預測**。
- 正確讀法：**看多個獨立指標一起動的趨勢，不要押單一數字、不要信單月**。
- 各指標精確度不同：硬數據（衛星火點、ADS-B、地震、海關）較可信；
  軟訊號（披薩、酒吧、預測市場、新聞情緒）雜訊多、有假陽性，僅作佐證。
