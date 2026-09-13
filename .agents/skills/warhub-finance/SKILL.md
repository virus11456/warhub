---
name: warhub-finance
description: "Maintain WARHUB Yahoo Finance quotes and FRED credit-spread collection. Use for stale prices, daily history, moving-average deviations and risk-proxy interpretation."
---

# WARHUB 金融與信用利差

入口 `scripts/fetch_data.py::fetch_finance`、`fetch_fred`，輸出 `data.json.finance`、`fred`，每日累積至 `data/metrics_daily.json`；執行與保存見 [抓取與封存](../warhub-collection/SKILL.md)。

`fetch_finance` 每輪快來源逐個 FIN_TICKERS 讀 Yahoo Finance chart API（query1.finance.yahoo.com/v8/finance/chart，1d／3mo）；目前每標的最多兩次，重試間隔與 timeout 沿用程式。標的含黃金、布倫特、瑞郎、VIX、小麥、國防股與美債殖利率。先核對 regularMarketTime、price、每日 closes，區分休市最後一筆與取得新交易；沿用觀測時間不能冒充即時報價。

漲跌幅以程式選擇的前收基準計算；ma30 需要 30 個有效交易日。資料不足就留空，不能用較少樣本仍稱 30 日均線。Yahoo 指數／期貨／匯率／殖利率的單位與交易日不同，新增標的先核對官方定義。油價相對均線差額只是價格偏離，不是戰爭溢價的因果估計。

`fetch_fred` 為慢來源，需 `FRED_API_KEY`，目前取 `BAMLEMCBPIOAS` 與 `BAMLH0A0HYM2` 最新觀測。缺 key 返回空資料；值 `.`、空字串與 null 不得轉零。API 抓取時間不等於序列觀測日；保留原em_oas/hy_oas數值欄位，另在observations逐序列保存官方observation_date、fetched_at、series_id及status。缺報保留None，拒絕未來日期、NaN及無限值。每日metrics以fred_observation_dates保存原日期；歷史舊值不可事後猜日期。來源健康缺日期時標示不可核實；兩序列不同日期分別列出。錯誤日誌僅輸出例外類別，不可輸出含API key的URL。

保存 daily 指標時不能把當天抓取的休市舊值描述為當天成交，也不能把不同日的系列組成「同步」因果證據。FRED 與 Yahoo 失敗都要呈現缺值／沿用情況，金融情緒是觀察代理，不是投資建議或開戰概率。

相關驗證用 `tests/test_integrity.py` 與 `tests/test_frontend.cjs`；若改收盤基準，補能區分盤中／收盤及不足 30 筆的 mock 案例。外部驗證只查有疑問的標的，不為技能建立而全面抓取或觸發通知。

離線日期／缺值／錯誤日誌驗證：tests/test_fred_quality.py。

避險群聚使用 scoring.risk_off_cluster：金／油／VIX 上偏離、瑞郎及10年殖利率下偏離，門檻含5%；國防股任一達標即可確認亮訊號，但未達標須四檔均有效才能確認否。六類都可判讀才存0–6總數，否則為None；另存 risk_off_observed 及逐類 risk_off_signals。前端不將缺完整性欄位的舊總數當成已核實值，原始歷史仍保存。tests/test_risk_off_cluster.py 覆蓋完全缺值、部分缺值、有效零、方向及國防股不完整。
