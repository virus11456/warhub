---
name: warhub-activity
description: "Maintain WARHUB PizzINT and BestTime foot-traffic collectors. Use for missing shop data, closed-versus-unavailable states, live baselines and paid-query cadence."
---

# WARHUB 披薩與酒吧人流

讀 `scripts/fetch_data.py` 的 `fetch_pizzint`、`transform_pizza_shops`、`fetch_bars` 及 `scripts/data_quality.py`。執行與封存規則見 [抓取與封存](../warhub-collection/SKILL.md)。

| 入口 | 來源 | 輸出 |
|---|---|---|
| `fetch_pizzint` | `https://www.pizzint.watch/api/dashboard-data` | 原始店家經轉換產生 `data.json.pizza`、`pizza_index` 等，供 WPI 與店家卡 |
| `fetch_bars` | BestTime `/api/v1/forecasts/live` | `data.json.bars`；需 `BESTTIME_API_KEY` |

PizzINT 每輪快來源；以 `SHOPS_TO_DISPLAY` 精確對應上游名稱。先檢查店家是否存在，再判斷目前人流、營業狀態和可比較基準。店家清單有資料不表示即時人流可用。`current_popularity=None` 不得填零；沒有任何有效即時店家時，披薩指數不能當有效零分。

BestTime 目前僅美東 `America/New_York` 16:00–24:00 查詢，時區含夏令時間；非時段不查詢，以免浪費額度。需檢查回應 analysis 結構、即時可用旗標與 baseline；未設定 key、API 失敗、未營業、非查詢時段要分開呈現。不記錄包含 private key 的完整請求 URL。

Google Maps Popular Times／BestTime 是店家人流訊號，無法直接證實外送訂單、軍方加班或軍事行動；酒吧冷清與披薩忙碌可能有共同原因，不能宣稱已驗證交叉預警能力。

離線測試在 `tests/test_integrity.py`。需覆蓋不存在店家、缺即時值、有效零、結構錯誤及無 baseline。線上檢查可能耗用 BestTime credit，先用既有快照定位，只在需要時做有限請求。勿以測試本 skill 為由觸發 Telegram。

WPI v4.0 的人工權重公式與歷史維持原樣，calculate_wpi 標記 experimental=true；舊 WPI／披薩／酒吧放在預設收合實驗區。alerts.run_notifications 對 experimental=true 或缺旗標的舊快照停用 WPI 升級與披薩異常警報（環境開關也不覆蓋此限制），保留更新摘要及獨立熱異常觀測。摘要標示實驗，不顯示 DEFCON。不得宣稱人流證實加班、獨立驗證或已回測；不改抓取頻率、不刪歷史。tests/test_alert_delivery.py 以 mock 驗證停止警報且摘要／熱異常仍有效，前端測試驗證實驗區收合。

Telegram摘要由alerts._fmt_pizza_shops呈現：只有新鮮、is_open=true、有效0至100忙碌度與已知狀態的店家算即時樣本；明確未營業、缺值／過期分別計數。無即時樣本不能說沒有異常，部分样本的「未見偏忙／爆量」只限定有效樣本。已過期／失敗店家不出現在偏忙名單；缺percentage_of_usual不補0，標缺平時比較值。來源整體stale／unavailable優先顯示。tests/test_alert_content.py驗證有效零、缺值、打烊與過期；不改人流來源、通知政策或歷史。


2026-09-22 披薩48小時研究：scripts/pizza_backtest.py 純離線讀取 research/pizza-observations.json 與既有 archives/YYYY/MM 下分析快照；同輪 output 的 updated_at 為分析截止，來源 defcon_details.at_time 原樣保存。正常 fetch_data 產生 pizza_backtest 摘要，不新增API請求／排程／通知，不改WPI。分開DEFCON≤3與≤2，只計前次在門檻外、本次首次進入的觀測跨越；持續高警戒及重複來源時間不重算。缺值、來源過期超6小時、觀測間隔超6小時或衝突後高警戒列起點不明；觀測時間不是精確升級時刻。歷史每日值及軼聞不補造成觸發。
research/pizza-reviews.json 保存版本化重大行動定義與逐事件審核；候選空襲不是命中。只有附來源、審核時間、完整落在48小時內的行動時間範圍才算確認；負例須明確完成整個窗口核對，沒有新聞不等於無行動。尚有成熟窗口待核實則整組比例維持null，不從少數已確認正例推算命中率。兩組與窗口可重疊，Wilson區間未校正相依；未建立對照期基準前不得宣稱預測能力。reviewed_fraction僅診斷，不當作整組率；baseline_rate/predictive_lift保持null。讀檔錯誤不當零，封存讀取失敗停顯比例。
初次研究檔包含101份觀測（100封存加一份main快照）；原封存與歷史均不改寫。網站 pizza-backtest.js 使用靜態審核結果作初次顯示，之後採較新的快照摘要，不把舊研究時間說成即時。中英文切換不重新抓資料。tests/test_pizza_backtest.py、test_pizza_backtest.cjs及既有DOM suite驗證門檻、去重、缺值、48h邊界、審核、反序回覆與雙語；禁止執行fetch_data作測試。

