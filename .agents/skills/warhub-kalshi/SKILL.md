---
name: warhub-kalshi
description: Maintain bounded Kalshi public market collection, geopolitical background references and bilingual display.
---

# Kalshi 地緣政治背景

先讀 AGENTS.md、warhub-collection；Polymarket既有選題見warhub-polymarket。

## 入口與範圍

`scripts/fetch_data.py::fetch_kalshi` → `kalshi_client.refresh/collect` → `kalshi_market_data.normalize/select_markets`；輸出`data.json.kalshi`。正常收集內執行，不新增排程、推播或交易入口。使用者於2026-09-22明確允許外交、制裁、軍事政策作為地區分數參考。它們標為geopolitical_background/context_only，不把核協議Yes上升當軍事升級，不改WPI與地區既有權重，也不與Polymarket重複計權。

目前人工核對的系列：KXUSAIRANAGREEMENT（美伊核協議，中東）、KXSANCTIONRUSSIA（制裁俄羅斯，俄烏）、KXGREENLANDMILITARYBILL（格陵蘭軍事政策，無對應監測地區）。scope.all_platform_markets=false；這不是全平台掃描。新增系列須核對官方目錄與實際問題／YES條件，不以國名盲選人物、選舉、體育題。非背景市場仍沿用market_selection.selected_market_risk，Polymarket公式未變。

官方公開讀API：`https://external-api.kalshi.com/trade-api/v2/markets`，series_ticker、status=open、limit=100；不需金鑰。文件：https://docs.kalshi.com/api-reference/market/get-markets 。最多3個系列、全輪3次請求、間隔至少1秒、每次15秒／2MB；cursor重複或格式錯停止，禁止redirect，401/403/429停止全輪，不即時重試。429的retry_at跨輪保存；所有attempt至少相隔110分鐘，失敗也不繞過。authorized旗標是程式啟用選擇，不是資料授權證明。

先前客服只提供文件並明言不能確認external-project licensing；公開展示／保存授權仍未獲書面確認，不宣稱已取得授權。使用者已持續明確要求接入；待審閱的追問信不能自動寄出。

## 資料語意

保留provider/ticker/event_ticker/series_ticker、title_original、question原文+yes_sub_title（期限選項）、完整rules與指紋。close_time是交易關閉時間，不自動視為事件截止／結算時間。不同期限題目不去重為同一題，也不是多份獨立證據。

只接受binary、active、未到期、兩側正量且bid≤ask的0–1有限報價。中價display_midpoint與last_price分開；有效零可顯示，缺值或空簿不能補0。volume_contracts是合約數而非美元。source_updated_at不是已證實的報價時間；quote_observed_at保持空，fetched_at明示取得時間。

available僅指選定系列查完；完整空集合與失敗不同。partial不宣稱齊全。失敗沿用時保留原markets/fetched_at並stale；冷卻只改requests/reused，不修改舊觀測；6h過期。完整空結果不復活舊市場。原觀測隨現有immutable data.json快照保存，不覆寫／重算舊資料；本版尚無24h價差分析，不能補零宣稱已有比較。

翻譯沿用_translate_market_questions，明確傳入Kalshi自身精確question快取，不混用Polymarket快取。每輪最多翻譯12題；錯誤保留報價及原文，中文畫面顯示待補，不造假翻譯。復用／失敗舊快照不重新翻譯或改時間。

## 網站與驗證

index載入kalshi-markets.js/css，位於現有市場區下方；地區卡片data-kalshi-region對應參考入口。地區重繪須呼叫refreshKalshiReferences避免連結消失；中英文事件同步重繪。所有來源文字用textContent。客戶端檢查6h時效、未到期與有效中價；舊報價只在明示過期的細節供查閱。欄位不進WPI、Telegram警報或風險權重。

離線：python -m unittest discover -s tests -p 'test_kalshi*.py'；test_integrity.py含主流程mock。node tests/test_kalshi_frontend.cjs驗證空、零、過期、缺值、英文與注入；test_frontend.cjs引入此檢查，CI涵蓋。既有test_site_languages.cjs亦要通過。真瀏覽器以暫存快照／已取得來源回應驗收桌面1440與手機390，禁止把合成fixture寫入正式data。

有限實測：2026-09-22美伊系列8個open，其中7個符合雙邊報價／未到期條件；軍費、俄羅斯制裁、格陵蘭法案所查系列當時無開放市場。查詢成功不保證每次都有行情；不外推全平台無其他題目。自然排程最新資料才是正式來源驗收，程式部署≠行情已出現在正式快照。

首次上線備援：research/kalshi-initial.json是2026-09-22實際API取得的美伊系列初始快照，保留原fetched_at及原標題／期限，7題中文人工核對。尚無正式kalshi欄位時前端只讀一次，明示initial_probe；6h過期不顯示現時中價，較晚回應不能蓋過已載入正式kalshi（即使正式結果為空／失敗）。正常collector只從此檔讀精確翻譯快取，不把其報價改時間或當新收集。此檔作歷史種子保留，不滾動更新。

2026-09-22卡片整合：Kalshi卡片改加入poly-list-container同一網格，沿用poly-item／poly-bar／poly-percent；每張data-exchange及平台標籤，不另建Kalshi卡片區或平台篩選器。Polymarket重新渲染後refreshKalshiReferences重建Kalshi卡片，先移除舊Kalshi節點避免重複。交易量的美元與合約數維持區別；kalshi-market-container只留精簡來源狀態。此批為顯示，不增加系列、不改計分權重。

2026-09-23：兩平台卡片在同一網格交錯排列，各平台內部順序維持；不混用美元／合約量作跨平台排名。防止Kalshi全部排在列表尾端而看似消失，重繪仍先清除舊Kalshi卡片。
