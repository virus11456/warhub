# WARHUBS — 開源情報觀察儀表板

網站：https://warhubs.com/

靜態 HTML/CSS/JavaScript + Python 資料抓取器 + GitHub Actions + Vercel。
**網站分數是人工權重的觀察指數，尚未校準為開戰機率。缺資料不代表安全。**

## 資料流

1. `.github/workflows/update-data.yml` 每 2 小時（UTC 第 23 分）抓取上游來源，排程可能延遲。
2. `scripts/fetch_data.py` 輸出 `data/*.json` 並保留歷史；`scripts/scoring.py` 統一產生網站、歷史與推播使用的 WPI。
3. Vercel 連動 GitHub；程式合併至 `main` 會部署正式網站。只有六個 API 資料 JSON 變動時跳過重建，仍從 GitHub 讀最新資料；無法確認上次部署差異則正常重建。
4. 前端每 5 分鐘讀 `/api/data`，失敗退回同站 `data/` 部署快照。刷新網頁不代表上游資料剛更新。
5. `/api/data` 需要 Vercel 環境變數 `GITHUB_TOKEN`，對私人倉庫 `virus11456/warhub` 具有 Contents read 權限。GitHub Actions 內建 token 不會自動傳到 Vercel。

## 模型 v4.0

名義权重 P .28 / A .18 / G .10 / Z .14 / F .10 / S .12 / W .08。
可用權重至少 60%、至少三項有效因子才輸出 WPI；只對有效因子重新正規化。這是資料品質門檻，**不是統計信賴度**。

- P：標題通過保守軍事主題篩選、有效 Yes/No、未過期的事件盤，停火題反向。不同事件、期限及累計交易量仍不可解讀為同一事件機率。
- A：目前 ADS-B 可見軍機數相對過去七天樣本均值；至少 12 個樣本且歷史涵蓋六天。接收覆蓋、日夜與星期效應仍待校正。
- G：新取得的 GDELT 新聞佔比；沿用值不計分。
- Z：有店家即時人流時才使用上游 PizzINT 平滑指數。
- F：暫不計分。全球火點和矩形監測區熱異常沒有足夠證據代表戰火。
- S：至少三項有效金融偏離指標；基準為最後報價日之前 30 筆日線收盤，不使用硬編碼均線。
- W：Wikipedia 戰爭相關條目瀏覽量，相對過去基準。

地區指數另以市場 35%、新聞 25%、NOTAM 15% 為可用候選；有效權重至少 60%、至少兩因子。火點與廣域軍機數僅展示，不計分。來源不足時顯示「資料不足」。

舊版歷史保留以供追溯，但不同模型版本不接成同一分數趨勢。新版權重、門檻仍是暫定設計，需獨立回測。

## 開發與驗證

```sh
python -m venv .venv
.venv/bin/pip install -r scripts/requirements.txt
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_api.mjs
# 本機驗證抓取時禁用通知；會更新本機 data 檔案
WARHUB_NO_NOTIFY=1 .venv/bin/python scripts/fetch_data.py
python -m http.server 8000
```

選用來源需要 GitHub Actions Secrets：`USDA_FAS_API_KEY`、`BESTTIME_API_KEY`、`FRED_API_KEY`。
推播需要 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` 或 `DISCORD_WEBHOOK_URL`。
不可把金鑰放進前端、資料 JSON 或 Git。Vercel token 應只具有此倉庫唯讀權限。

詳見 [來源稽核與後續工作](docs/DATA_AUDIT.md) 與 [運維說明](docs/OPERATIONS.md)。

### 更新頻率與額度

來源抓取維持每 2 小時；前端每 5 分鐘重新讀取快照，不代表來源每 5 分鐘更新。資料流程僅排程或手動執行，程式推送不額外抓取。probe／隔離驗證僅手動啟動且不自動提交資料。PR 驗證避免 push 與 pull_request 重複觸發。

資料更新不必部署，但 API 失效時靜態備援可能較舊；請注意畫面更新時間與過期提示。更新 Vercel 環境變數後仍可手動重新部署同一版本。新抓取器於合併後下一次排程生效。

### 快慢資料分流

排程預設 `collection_mode=auto`：快來源每輪更新；Comtrade、USDA、FRED 最多每 6 小時啟動一次檢查（Comtrade 仍有既有 22 小時快取）；月度歷史補抓每 24 小時一次。首次缺少分流紀錄時自動初始化。仍由同一個互斥工作流程寫入，並未新增一套會同時覆蓋檔案的排程。

手動 `fast` 僅查快來源，慢資料缺值就保持缺值；`full` 執行完整流程。直接執行 Python 預設 full，可透過 `WARHUB_COLLECTION_MODE` 指定。慢資料保留原觀測／更新時間，來源面板註明本輪沿用；超過慢資料檢查期限時不標為新資料。

快照的 `collection` 保存各來源 `duration_seconds`、沿用來源和慢資料／歷史嘗試時間。嘗試時間不是成功時間或觀測時間；失敗也遵守間隔以避免頻繁重試。先觀察實際快輪耗時，再決定是否提高總排程頻率，目前未承諾分鐘級即時性。最近 25 次舊流程實測平均執行約 5.96 分鐘、啟動間隔約 4.81 小時，不能用「設定每 2 小時」代替實際新鮮度。

### 不可用來源的等待上限

GDELT 每輪最多等待約 45 秒、FAA NOTAM 約 30 秒（含串行間隔與重試，取消清理可能略多）。遇 HTTP 401／403／429 時，本輪停止該來源後續請求，不重試拒絕存取或限流。其他地區保留已完成的新資料，未完成的沿用原時間並標 stale，缺少備援時保持無資料。

查詢起點依兩小時 UTC 時段輪替，降低固定末尾地區受等待上限影響的機會。這不會繞過存取限制，也不保證所有地區更新成功；來源品質與覆蓋門檻不變。排程頻率仍未提高，需以實際新快照的 duration_seconds 檢查改善幅度。

### Telegram 推送時機與送達紀錄

Telegram／Discord 在資料收集完成後檢查推送條件，沒有獨立整點計時器。目前資料排程每兩小時啟動，GitHub 排隊與資料來源等待可能延後送出。`DIGEST_EVERY_HOURS`（預設 1）只控制摘要的去重時段，不代表每小時保證送達。頻道預設收摘要與異常；`TELEGRAM_CHANNEL_SCOPE=alerts` 只收異常。

Telegram 使用純文字，避免資料或新聞的特殊符號造成整則拒收。只有 API 確認成功才記錄摘要送達；各對象分別去重，同時段再次執行只補送未確認成功的對象。網路逾時不立即重送，避免短時間重複推送；若對方已收到但回應遺失，下次執行仍可能重複。異常警報仍依資料變化觸發，失敗結果記錄在 `_notify.delivery`，不建立無限重送佇列。

### 長期快照封存

每次成功完成收集，在同一次資料提交內新增 `archives/YYYY/MM/時間_SHA256.json.gz`，不增加排程、來源請求或通知。純資料與封存提交不觸發 Vercel 建置；封存不包含在網站部署或公開 API 中。封存失敗會使該次提交步驟失敗，不會悄悄略過。

每份壓縮檔包含六個資料 JSON 的收集完成版本、收集程式 commit SHA、快照時間及格式版本；不封存 `_notify` 推送對象／送達狀態。來源原有觀測時間、缺值、stale 與沿用標記原樣保存。這是整理後的完整分析快照，不是各服務的原始 HTTP 回應，也不保證每個來源該輪取得新資料。提交前歷史合併可能調整網站最新視圖，封存仍保留當輪收集器輸出。

不設定滾動刪除期限，以新檔保留修訂，不覆蓋先前版本；重試同一內容不增加副本。GitHub 是目前唯一封存儲存位置，並非異地備份。既有 Git 歷史不會自動重新匯入；啟用前的資料仍須從舊 commit 追溯。壓縮能降低增長速度，但需隨累積量評估移至物件儲存。

離線讀取範例（Python 標準函式庫）：

```python
import gzip, json
with gzip.open("archives/YYYY/MM/實際檔名.json.gz", "rt", encoding="utf-8") as stream:
    snapshot = json.load(stream)
latest = snapshot["files"]["data.json"]
```
