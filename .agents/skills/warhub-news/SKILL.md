---
name: warhub-news
description: "Maintain WARHUB Google News RSS collectors, Traditional Chinese title caching and Taiwan aircraft headline extraction. Use for missing or English headlines and incorrect PLA sortie counts."
---

# WARHUB 中文新聞與共機

## 中英文顯示（2026-09-15）

首頁與 guides 使用 i18n.js、i18n.css 及 locales/en.js，每次新開頁面預設繁中；不讀瀏覽器語言或保存上次選擇。只改文字節點、標籤與 Canvas 文字，不改連結、價格、漲跌 class 或觀測時間；切換不呼叫爬蟲／翻譯服務。新聞及市場以同一筆資料的中英文題目對照，不能用字詞拼湊新聞譯文。英文原標題優先沿用；中文原新聞由既有 Groq helper 的 target=en 分支增加 title_english，title/title_zh/title_en（既有原文欄位）與 ts 均保留。失敗顯示英文未取得提示，不能把提示當作已翻譯。

english_titles 每輪在既有 session 中處理 news、tw_news，沿用相同 Groq 錯誤停止與請求限制；不啟用 Google 備援、不增加來源抓取頻率。english_translation_cache 按完全相同原文保存至多512筆，不改新聞觀測歷史。台海時間軸的新觀測可帶 title_english；舊紀錄不補造欄位或時間，前端可使用已存同原文快取。Translate saved titles 的 refresh_translations 也可補已存英文標題，須全組成功才原子寫入，仍不改 updated_at、價格、分數或通知回條。

固定介面／指南字串由 scripts/extract_ui_catalog.cjs 用 jsdom + acorn 離線解析，產生 locales/source.json；scripts/build_ui_assets.py 只接受齊全英文 catalogue，可合併人工覆核的 locales/overrides.json，產生靜態 en.js。UI 更動後重跑抽取／建置並檢查來源差異，勿手改 en.js。scripts/translate_ui.py 是明確一次性的公開介面譯文準備工具，使用既有 Groq Secret，不是定時收集或部署測試；最多120批、每批50項／1400字，保留合法數字占位符，個別不合格譯文留待覆核，不降低驗證。遵循回應 reset headers，429停止並保存 retry_at，不切換模型／端點規避限制。帳戶配額共用，不能擠掉正常新聞翻譯或升級付費。

驗證 test_translations.py、test_refresh_translations.py、test_ui_assets.py、test_i18n.cjs、test_site_languages.cjs；後者涵蓋21個指南頁與首頁的繁中預設、英文文字、更新後語言、原文還原、連結及數值。真實桌面／手機瀏覽器仍需驗收。指南中文正文及原權威連結保留；英文是翻譯版本，不新增未核實的醫療或避難建議。

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

舊新聞估計留在 pla_adiz.json 的 unverified_days，不納入官方圖表及基準。合併以官方紀錄及較新checked_at優先，可接受較小修訂值，不取最大值。官方days滾動30日，缺日保留空白；首頁列表只有12篇；若需回補更舊日報，從官方列表的 ASP.NET 分頁表單取得第2、3頁，保留 hidden fields 與對應 __EVENTTARGET，不能猜測日報ID。2026-09-12已逐篇取得8/14～9/12共30天完整官方日報並回補；這不代表30天以前歷史已核實。舊估計與原版本仍可追溯。

驗證 tests/test_pla_official.py、tests/test_pla_counts.py、tests/test_frontend.cjs。純離線fixture，不執行整套爬蟲或通知。官方網站若改格式，解析失敗需核對原文後更新，不放寬為任意標題數字匹配。

## 金鑰更換紀錄

使用者於 2026-09-12 確認已設定 Groq Secret，並告知 key 上限一年。實際期限以 Groq 控制台為準；以此設定日計算的年度更換檢查日為 2027-09-12，應在到期前完成替換。更換流程為產生新 key、更新同名 GitHub Actions Secret `GROQ_API_KEY`、以不發通知的翻譯測試驗證，再撤銷舊 key；若舊 key 已暴露，應儘快撤銷並替換。不可把金鑰值寫入 skill、程式、log 或 commit。此紀錄不是已設定的自動提醒。

## 只補譯現有標題

`Translate saved titles`（`.github/workflows/translate-titles.yml`）僅手動觸發於 main，與收集 workflow 共用 `update-data` concurrency；使用 `scripts/refresh_translations.py` 讀現有快照並補譯。它不抓來源、不算分、不發通知、不改 `updated_at` 或原觀測時間。全部標題有效才原子寫回 data.json，失敗不寫入；一般 push 遇到遠端更新即失敗，不強制覆蓋。這個手動修復提交可由 Git 歷史追溯，不新增一份偽裝成新觀測的收集封存。不要為驗證 key 而執行整套爬蟲。驗證 `tests/test_refresh_translations.py`。

台海交叉洞察由 scripts/taiwan_insights.py::build 以既有快照推導，主流程写入 data.json.taiwan_insight 並隨分析快照封存。官方共機最新日對照此前28日，至少14個有效日；第90百分位以上僅稱活動偏高，非作戰意圖。最新日報超過48小時不作當前判讀。RSS以相同標題去重保留7天最多120則，僅稱已收錄樣本，不估完整新聞量或獨立證據數。市場保留7天最多100輪、每輪8題，逐題識別 id/question/end_date 比較約24小時（±4h），截止日不同不混比；前端只展示前3題，同題歷史不足留空。時間軸最多20筆區分統計截止與新聞發稿，均不冒充事件發生時間。資料不額外抓取、不通知；前端快照6小時過期停止判讀。舊快照無此欄位顯示等待正常排程。tests/test_taiwan_insights.py 與 test_frontend.cjs 驗證零值、基準、同題比較、保存、過期與安全連結。

台海洞察的 news.input_status 僅描述本輪 tw_news 可用樣本：available／partial／stale／unavailable，不代表完整新聞覆蓋。空或無效輸入為 unavailable；既有7天樣本及原 ts 保留，sample_24h 為已保存且發稿在24小時內的筆數，0只表示保存窗口中沒有符合樣本。前端缺少統計顯示缺資料，舊快照可使用既有 source_health.tw_news 狀態，缺旗標不推定正常。顯示最近保存新聞的發稿時間、公務船與共艦分列；市場比較須有20–28小時前的 comparison_at、有效報價及未到期題目，並列出兩次快照時間，缺比較不補零。新增欄位只隨正常排程產生，不重算或覆寫歷史；tests/test_taiwan_insights.py 與 tests/test_frontend.cjs 離線驗證失敗沿用、缺值、有效零、過期題目與原時間保存。

固定字串抽取須遍歷 AST 物件屬性的 value（例如狀態 label 字典），不可一律略過 value。原有 emoji 轉 SVG 會移除文字中的圖示，i18n 同時建立去圖示的完整標籤對照，避免拆字混譯。每次新增 UI 後以 test_site_languages 驗證真實 renderer 動態文字；4032 是本次包含人工覆核與別名的靜態字串數，不是未來覆蓋保證。資源 URL 版本需與發布批次一致；本機驗收若看到舊樣式，核對實際 link href，不把舊畫面當新驗收。

英文新聞驗收修正（2026-09-15）：scripts/reviewed_english.py 保存完全相同原標題的人工覆核譯文，優先於舊英文快取；不套用到相似標題、不改中文／原文／ts。valid_english 在快取及新回應都拒絕「機艦→aircraft carriers」（原文未提航母時）、陸委會機關誤譯、高市人名及沖繩政治變天誤譯。這是針對已發現錯誤的有限檢查，不能保證未來每篇語意都正確。失敗移除錯誤title_english並標unavailable；仍沿用同一服務的失敗停止規則。test_reviewed_english.py 驗證合計機艦不變成航母、真正航母不被誤拒，以及既有人工譯文。
