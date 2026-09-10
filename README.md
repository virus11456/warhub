# WARHUBS — 開源情報觀察儀表板

網站：https://warhubs.com/

靜態 HTML/CSS/JavaScript + Python 資料抓取器 + GitHub Actions + Vercel。
**網站分數是人工權重的觀察指數，尚未校準為開戰機率。缺資料不代表安全。**

## 資料流

1. `.github/workflows/update-data.yml` 每 2 小時（UTC 第 23 分）抓取上游來源，排程可能延遲。
2. `scripts/fetch_data.py` 輸出 `data/*.json` 並保留歷史；`scripts/scoring.py` 統一產生網站、歷史與推播使用的 WPI。
3. Vercel 連動 GitHub；合併至 `main` 會部署正式網站。
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
