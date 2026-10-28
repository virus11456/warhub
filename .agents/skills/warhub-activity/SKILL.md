---
name: warhub-activity
description: "Maintain WARHUB pizza-shop and bar foot-traffic collectors (own BestTime account). Use for missing shop data, setup/forecast state, closed-versus-unavailable states, usual-week baselines and paid-query cadence."
---

# WARHUB 披薩與酒吧人流

讀 `scripts/fetch_data.py` 的 `fetch_pizza`、`fetch_bars`、`besttime_live`，`scripts/pizza_traffic.py`（純函式，不發請求），`scripts/besttime_setup.py`（手動建檔）及 `scripts/data_quality.py`。執行與封存規則見 [抓取與封存](../warhub-collection/SKILL.md)。

| 入口 | 來源 | 輸出 |
|---|---|---|
| `fetch_pizza` | BestTime `/api/v1/forecasts/live`（與酒吧共用 `besttime_live`），只查 `data/besttime_venues.json` 已有 venue_id 的店 | `data.json.pizza`、`pizza_summary`、`pizza_index`（WPI z）、`pizza_events` |
| `fetch_bars` | BestTime `/api/v1/forecasts/live` | `data.json.bars`；需 `BESTTIME_API_KEY` |
| `besttime_setup.py`（非排程） | BestTime `POST /api/v1/forecasts`，每店成功 2／失敗 1 credit | `data/besttime_venues.json`：披薩店 venue_id＋usual_week、酒吧 venue_id、errors |

2026-10-28 起披薩人流只用自有 BestTime 帳號（使用者決定），已移除 PizzINT 來源、DEFCON、48小時回測卡與 pizza_backtest；research/ 與 archives/ 舊資料保留不改。網頁不顯示 PizzINT 名稱。下方較早日期的 PizzINT 筆記僅為歷史紀錄。

店家清單在 `pizza_traffic.PIZZA_VENUES`（顯示名 → BestTime 查詢名稱＋地址）。平常人流 usual_week 只在建檔時取得並存檔（BestTime 週一=0、每日 6AM–5AM；轉成週日=0、索引＝華府時鐘小時，18–23 格屬隔天），排程不重查週預測；重建檔才會更新。即時值僅美東 `America/New_York` 16:00–24:00、且已建檔的店查詢，每店每輪 1 credit；未建檔不查，以免付費拿 409／404。hourly_24h 由前一份 data.json 的同店紀錄累積，只留 24 小時內自己的讀數。

狀態要分開：`setup_needed`（未建檔）、`waiting`（非查詢時段）、`unavailable`（查詢失敗，保留 error_message）、`closed`（BestTime 明確 Closed）、有值時 `quiet`／`normal`／`busy`／`spike`。busy 需 ≥150% 且比平常 +20；spike 需 ≥200% 且 +30（≥250% 且 +40 為 EXTREME，供 alerts）；低於平常 60% 為 quiet。0 是有效空店。區塊等級：任一 spike 或 ≥2 家 busy＝爆單，1 家 busy＝偏忙，其餘正常。異常指數＝可比店家 max(0, 百分比−100) 平均（上限 100），少於 2 家可比時為 None，不當 0。

建檔須使用者同意花 credit：手動執行 `.github/workflows/besttime-setup.yml`，confirm 輸入 SPEND 才扣點，否則只列出店家與最多花費；預設只建尚未有 venue_id 的店，redo 才重建。排程更新從不建檔。

Google Maps Popular Times／BestTime 是店家人流訊號，無法直接證實外送訂單、軍方加班或軍事行動；酒吧冷清與披薩忙碌可能有共同原因，不能宣稱已驗證交叉預警能力。不記錄包含 private key 的完整請求 URL。

離線測試在 `tests/test_pizza_traffic.py` 與 `tests/test_integrity.py`。需覆蓋週預測轉換、未建檔／非時段／失敗／打烊分流、有效零、24 小時累積、只查已建檔店，以及建檔目標篩選。線上檢查可能耗用 BestTime credit，先用既有快照定位，只在需要時做有限請求。勿以測試本 skill 為由觸發 Telegram。

WPI v4.0 的人工權重公式與歷史維持原樣，calculate_wpi 標記 experimental=true；舊 WPI／披薩／酒吧放在預設收合實驗區。alerts.run_notifications 對 experimental=true 或缺旗標的舊快照停用 WPI 升級與披薩異常警報（環境開關也不覆蓋此限制），保留更新摘要及獨立熱異常觀測。摘要標示實驗，不顯示 DEFCON。不得宣稱人流證實加班、獨立驗證或已回測；不改抓取頻率、不刪歷史。tests/test_alert_delivery.py 以 mock 驗證停止警報且摘要／熱異常仍有效，前端測試驗證實驗區收合。

Telegram摘要由alerts._fmt_pizza_shops呈現：只有新鮮、is_open=true、有效0至100忙碌度與已知狀態的店家算即時樣本；明確未營業、缺值／過期分別計數。無即時樣本不能說沒有異常，部分样本的「未見偏忙／爆量」只限定有效樣本。已過期／失敗店家不出現在偏忙名單；缺percentage_of_usual不補0，標缺平時比較值。來源整體stale／unavailable優先顯示。tests/test_alert_content.py驗證有效零、缺值、打烊與過期；不改人流來源、通知政策或歷史。


2026-09-22 披薩48小時研究：scripts/pizza_backtest.py 純離線讀取 research/pizza-observations.json 與既有 archives/YYYY/MM 下分析快照；同輪 output 的 updated_at 為分析截止，來源 defcon_details.at_time 原樣保存。正常 fetch_data 產生 pizza_backtest 摘要，不新增API請求／排程／通知，不改WPI。分開DEFCON≤3與≤2，只計前次在門檻外、本次首次進入的觀測跨越；持續高警戒及重複來源時間不重算。缺值、來源過期超6小時、觀測間隔超6小時或衝突後高警戒列起點不明；觀測時間不是精確升級時刻。歷史每日值及軼聞不補造成觸發。
research/pizza-reviews.json 保存版本化重大行動定義與逐事件審核；候選空襲不是命中。只有附來源、審核時間、完整落在48小時內的行動時間範圍才算確認；負例須明確完成整個窗口核對，沒有新聞不等於無行動。尚有成熟窗口待核實則整組比例維持null，不從少數已確認正例推算命中率。兩組與窗口可重疊，Wilson區間未校正相依；未建立對照期基準前不得宣稱預測能力。reviewed_fraction僅診斷，不當作整組率；baseline_rate/predictive_lift保持null。讀檔錯誤不當零，封存讀取失敗停顯比例。
初次研究檔包含101份觀測（100封存加一份main快照）；原封存與歷史均不改寫。網站 pizza-backtest.js 使用靜態審核結果作初次顯示，之後採較新的快照摘要，不把舊研究時間說成即時。中英文切換不重新抓資料。tests/test_pizza_backtest.py、test_pizza_backtest.cjs及既有DOM suite驗證門檻、去重、缺值、48h邊界、審核、反序回覆與雙語；禁止執行fetch_data作測試。


2026-09-22證據呈現修正：pizza-reviews新增screenings，保存逐窗口的初步查找、雙語摘要、來源與checked_at；inconclusive／complete_window=false不改正式reviews，不轉為reviewed_no或命中。本輪只核對到候選動武、反恐空襲、計畫暫緩，部分官方頁403且精確時點／範圍不足，不能宣稱6窗已核實。前端獨立讀screenings與現有觀測摘要，不刷新歷史時間，主畫面直接列每次訊號與證據；四格改為確認符合／完整核對未見／仍不確定／觀測中，缺率顯示尚不能估計，方法另收合。沿用既有8bit主题Cubic11與PressStart2P，不改觀測演算法。

2026-09-23披薩48h呈現：統計常駐、事件與證據預設details收合，計算方法為獨立details。重繪分別保存兩者open，語言／門檻／資料更新不強制收合使用者已開啟的內容。只改UI，不改訊號自動累積或人工查核流程。
私有GitHub原始封存連結不再出現在公開披薩回測UI；保留原觀測時間與公開證據連結，後端archive欄位與歷史檔不刪除。

2026-10-27店家24小時長條圖：`pizza_hourly`（由`transform_pizza_shops`呼叫，同一次PizzINT請求，不增加請求或排程）另存兩欄。`hourly_24h`為上游`sparkline_24h`最近24筆`{at: 原recorded_at, v}`，v只收0–100，None＝無資料，0是有效空店，不互補。`usual_week`為`baseline_popular_times`轉成`'0'`(週日)…`'6'`(週六)各24格（索引＝美東小時），無效日鍵／小時／數值丟棄成None；週日＝0依店家平日／週末型態判斷，上游改格式時先比對辦公區店家（如We, The Pizza）平日高、週末低再調整。舊`sparkline`保留相容。前端`pizzaHourlyChart`以快照最新觀測時間的美東日期與星期：灰柱＝該星期平常值，亮柱＝同一美東日期的實測，虛線框＝資料時間所在小時；昨日點不畫，圖例只在格子上方顯示一次。這是Google平常人潮與實測對照，不代表訂單量。測試：tests/test_pizza_hourly.py、tests/test_frontend.cjs。

2026-10-27 PizzINT 上游停更：dashboard-data 每家店 data_source='none'、current_popularity 與 sparkline_24h 全為 null（24小時內0筆實測），屬上游無資料，非本站解析錯誤。前端 renderPizzaRadar 在全部店家 data_source==='none' 時顯示「來源 PizzINT 目前沒有提供即時人流（上游暫停，不是店家打烊）」，不當作打烊或零。Nighthawk Brewery & Pizza 已不在上游清單，從 SHOPS_TO_DISPLAY 與前端 PIZZA_SHOPS_DATA 移除；歷史快照不改。以 BestTime 為披薩店備援會耗用付費額度，需使用者另行同意。

2026-10-27 披薩店 BestTime 備援（使用者同意，僅美東下班時段）：fetch_pizza_besttime 只在 BAR_QUERY_ET_HOURS（美東16–24時，含夏令）且有 BESTTIME_API_KEY 時執行，只查 PizzINT current_popularity 為 null 且非 is_closed_now 的店（最多6家／輪，約每2小時一輪），不重試。場地用 PIZZA_BESTTIME_VENUES 的名稱＋地址（由 PizzINT Google Maps 座標反查）；BestTime 回傳場地座標須在 PizzINT 座標 0.4 公里內，無座標時門牌號與街名須相符，否則丟棄（避免同名分店）。只採 venue_live_busyness_available=true 的值；無值不補零、不代表打烊。transform_pizza_shops 只在 PizzINT 缺值時填入：busyness＝BestTime 即時值、percentage_of_usual＝即時÷預測×100（預測缺或為0則 None）、data_source='besttime'、recorded_at＝查詢時間，並把該點附加到 hourly_24h（source='besttime'）。PizzINT 有值時一律以 PizzINT 為準。pizza_index／DEFCON 仍只用 PizzINT，不以備援值計算。前端卡片標「來源：BestTime 備援」，source_health 註明備援店數。測試：tests/test_pizza_hourly.py（時段、只查缺值店、座標／地址比對、PizzINT 優先、有效零）、tests/test_frontend.cjs。

2026-10-27 備援診斷：首輪（美東16:35）結果 0/6，無位置不符警告，原因無從判斷。fetch_pizza_besttime 現在逐店記錄原因 used／no_live_value／venue_mismatch／http_<狀態>／invalid_schema／request_failed，寫入 log 與 data.json.pizza_backup={queried_at, reasons}（非下班時段或無 key 時為 null）。只供診斷，不影響店家值或指數；備援無值不補零。

2026-10-28 BestTime 錯誤說明：2026-10-27 23:08 一輪披薩6店與酒吧4家全部 HTTP 409（帳號層級問題，非地址或比對）。besttime_live 在非200時讀回應的 message（或 status／原文），去空白、遮蔽 API key、截 200 字，存為 error_message 並寫 log；酒吧在 data.json.bars[].error_message，披薩在 pizza_backup.messages{店名: 說明}。不重試、不改查詢時段或次數。

2026-10-28 披薩48小時卡簡化（使用者要求）：pizza-backtest.js 移除「展開事件與證據」「查看計算方法」兩個收合區與 research/pizza-reviews.json 前端讀取，四格數字改成一句：升到 DEFCON N 或更緊張共 X 次：確認有行動／核對後沒有／仍不確定／未滿48小時（起點不明>0 時另列不納入）；比例缺值顯示「準確率尚不能估計」，並保留「未核實不當成沒有行動」。後端 pizza_backtest.py 與審核檔不變。雷達摘要的上游暫停文字不寫來源名稱。WPI 覆蓋文字列出缺值因子（暫缺：披薩人流…；熱異常不計分）。

2026-10-28 BestTime 409 原因確定（使用者授權執行 besttime-setup，scope=all）：10 家店全部回 HTTP 409「Your free forecast credits are used up. Choose a plan to continue using Radar.」＝帳號免費額度已用完，不是程式或建檔流程問題；建檔與即時查詢都需付費方案。errors 已寫入 data/besttime_venues.json。換方案或補額度後，重跑 besttime-setup（confirm=SPEND）即可。
