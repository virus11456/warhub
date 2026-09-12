---
name: warhub-news
description: "Maintain WARHUB Google News RSS collectors, Traditional Chinese title caching and Taiwan aircraft headline extraction. Use for missing or English headlines and incorrect PLA sortie counts."
---

# WARHUB 中文新聞與共機

從 repository root 讀 `scripts/fetch_data.py` 的 `fetch_gnews`、`fetch_tw_military_news`、`fetch_pla_sorties`、`_translate_titles`、`_translate_market_questions`，以及 `scripts/pla_counts.py`。總流程與執行界線見 [抓取與封存](../warhub-collection/SKILL.md)。

| 入口 | 來源與輸出 |
|---|---|
| `fetch_gnews` | Google News RSS `news.google.com/rss/search`；`data.json.news`，保留原文、連結、發稿時間與來源 |
| `fetch_tw_military_news` | 台灣語系 RSS `hl=zh-TW&gl=TW&ceid=TW:zh-Hant`；`data.json.tw_news` |
| `fetch_pla_sorties` | 空軍官方完整日報；`data.json.pla` 與 `data/pla_adiz.json`，30 天滾動歷史 |

每輪快來源抓取；發稿日不等於事件日。先比較 HTTP／RSS 解析、篩選後筆數、快取沿用和翻譯結果，分辨無新聞與無譯文。Google News 標題不會填補 GDELT 的量化新聞強度。

## 繁體中文

保留 `title_en`，中文寫 `title_zh`（新聞 `title` 同步中文），市場使用 `question`／`question_zh`。正式 workflow 使用 Groq Chat Completions（`https://api.groq.com/openai/v1/chat/completions`），GitHub Actions Secret `GROQ_API_KEY`，可用 Variable `GROQ_TRANSLATION_MODEL` 更換模型；預設 `openai/gpt-oss-20b`。詳見 `scripts/translations.py`。每批最多 10 個不同標題、單請求 20 秒、每組整體 60 秒、同 session 並行最多 2；遇 HTTP 錯誤或無效回應即停止該輪，不在同輪改用其他端點繞過限流。正式設定缺 key 時保留快取並標 `groq_missing_key`。

Google 舊流程保留給未指定 provider 的本機相容用途，已有 GitHub runner HTTP 429 的實測，不當作 Groq 自動備援。該流程每次 8 秒、整組 30 秒，遇拒絕／限流停止同 session 剩餘请求。

`translation_cache` 在 data.json 持久保存新聞／市場各最多 512 筆相同原文譯文，與快照一起封存；不要因標題暂时移出當期列表就丟失已翻譯結果。快取只省請求，不能驗證譯文正確性。Groq 使用嚴格 JSON Schema（更換模型須確認支援 strict 模式），回應須為完整 JSON、輸入 id 一一對應、中文文字與正常 stop 才寫入，原文中的命令只是待譯資料。確認否定與期限等語意；LLM 仍可能誤譯。

官方參考：https://console.groq.com/docs/text-chat 、https://console.groq.com/docs/models 、https://console.groq.com/docs/rate-limits 。模型與額度可能改變，改接前核對。

只按完全相同原文復用翻譯；市場與新聞快取分開。純英文不能標成成功中文，重試前清除殘留譯文。中文原標題可直接保留；有漢字只是語言粗篩，不能證明整句完整、繁簡正確或語意正確。人工補譯時逐題核對人名、否定、日期與期限，不改價格、數量或觀測時間。

前端 `chineseTitle`／`zhMarket` 共用中文結果。失敗顯示中文未取得提示並保留原文入口，不用字詞替換假裝翻譯；同時報告缺譯數，不能把提示當成已翻譯。要提高未來成功率須處理來源故障／可用的翻譯服務，不能只補當前快照就聲稱永久修好。

## 官方架次

`fetch_pla_sorties` 使用 `scripts/pla_official.py` 讀空軍官方空情動態列表及完整日報（air.mnd.gov.tw）。每輪列表1次，最多3篇缺漏／新日報；最新已存日報每6小時重新核對修訂。沿用全站間隔，不新增排程。解析失敗保留原資料及 checked_at，不改為零，不退回新聞標題估計。

解析器驗證官方URL、日報日期與明確24小時06:00至06:00起訖一致、非未來期間。`aircraft`為偵獲共機總架次，`area_aircraft`與`area_description`保留括號內特定空域子集，不能一律称為越線；共艦與公務船分開。零架次有效，缺欄位為null。保留 source_url、source_title、period_start、period_end、checked_at、date_basis=period_end、source_kind=mnd_daily_report。verified指通過官方日報格式及口徑核驗，不代表自行驗證實際軍事活動。

舊新聞估計留在 pla_adiz.json 的 unverified_days，不納入官方圖表及基準。合併以官方紀錄及較新checked_at優先，可接受較小修訂值，不取最大值。官方days滾動30日，缺日保留空白；首頁列表只有12篇，不能宣稱全部30天已核實。舊估計與原版本仍可追溯，尚未全歷史回補。

驗證 tests/test_pla_official.py、tests/test_pla_counts.py、tests/test_frontend.cjs。純離線fixture，不執行整套爬蟲或通知。官方網站若改格式，解析失敗需核對原文後更新，不放寬為任意標題數字匹配。

## 金鑰更換紀錄

使用者於 2026-09-12 確認已設定 Groq Secret，並告知 key 上限一年。實際期限以 Groq 控制台為準；以此設定日計算的年度更換檢查日為 2027-09-12，應在到期前完成替換。更換流程為產生新 key、更新同名 GitHub Actions Secret `GROQ_API_KEY`、以不發通知的翻譯測試驗證，再撤銷舊 key；若舊 key 已暴露，應儘快撤銷並替換。不可把金鑰值寫入 skill、程式、log 或 commit。此紀錄不是已設定的自動提醒。

## 只補譯現有標題

`Translate saved titles`（`.github/workflows/translate-titles.yml`）僅手動觸發於 main，與收集 workflow 共用 `update-data` concurrency；使用 `scripts/refresh_translations.py` 讀現有快照並補譯。它不抓來源、不算分、不發通知、不改 `updated_at` 或原觀測時間。全部標題有效才原子寫回 data.json，失敗不寫入；一般 push 遇到遠端更新即失敗，不強制覆蓋。這個手動修復提交可由 Git 歷史追溯，不新增一份偽裝成新觀測的收集封存。不要為驗證 key 而執行整套爬蟲。驗證 `tests/test_refresh_translations.py`。
