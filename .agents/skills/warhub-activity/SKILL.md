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
