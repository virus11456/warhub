---
name: warhub-osint
description: "Maintain WARHUB ADS-B, FIRMS, EONET, GDELT, USGS, Wikipedia and FAA NOTAM collectors. Use for source outages, observation freshness and raw-count versus anomaly-score mismatches."
---

# WARHUB 航空與公開情資

入口均位於 `scripts/fetch_data.py`。執行／封存見 [抓取與封存](../warhub-collection/SKILL.md)。來源 URL、REGIONS 與時間預算以當前常數為準，不把程式舊註解的「無速率限制」或「15 分鐘」當現行設定。

| 入口 | 來源／輸出 | 判讀與驗證重點 |
|---|---|---|
| `fetch_aviation` | `opendata.adsb.fi/api/v2/mil`，失敗才試 `api.adsb.lol/v2/mil`；`aviation` | 目前可見軍機，非軍方全量。先成功的來源即停止切換；分清分類數、地區範圍與異常基準 |
| `fetch_firms` | NASA MODIS 全球 24h CSV；`firms` | 確認欄位、UTC 觀測時間與 24h 範圍；熱異常含野火、工業等，不能直接標成戰火 |
| `fetch_eonet` | NASA EONET v3 開放自然事件；`eonet` | 開放事件及其 geometry 時間，非戰爭事件；保留事件類別、座標與時間 |
| `fetch_gdelt` | GDELT DOC API timelinevol；`gdelt` | 新聞報導強度，非新聞條數／衝突機率。逐地區記錄成功與 stale，其他 RSS 有新聞不能補此因子 |
| `fetch_nuclear_seismic` | USGS FDSN event API；`nuclear_seismic` | 72h、試驗場周邊 150km 篩選；無地震須查詢成功才可成立，地震不等於核試 |
| `fetch_wikipedia_anxiety` | Wikimedia Pageviews；`wikipedia` | 英文條目、每日資料截至前一日；最近兩天均量比更早樣本中位數，至少 10 點才有值。是關注度代理，非群眾焦慮實測 |
| `fetch_notams` | FAA `notams.aim.faa.gov/notamSearch/search`；`notams` | 領空公告，查詢成功的空清單與 403／缺資料不同；不能用舊公告冒充新觀測 |

這些來源在每輪快收集中檢查，但實際觀測頻率不同。先核對各來源的資料时间和健康狀態，不只看根層 `updated_at`。GDELT／FAA 遇到封鎖、限流、非預期 HTML，保留缺值或 stale；遵循 `SourceBackoff`、來源總預算及單次 timeout，停止該輪來源，不能無限改 URL 或增加請求。

目前全球 WPI 的 FIRMS 因子與地區廣域軍機／火點不直接計分；依 `scoring.py` 保留此界線。198 架可見軍機與異常分數 0 可以同時成立，不能用原始筆數填上分數。資料不足的地區留空，不能為了滿版補安全等級。

驗證 `tests/test_source_budgets.py`、`tests/test_integrity.py` 與 `tests/test_frontend.cjs`。用 mock 檢查限流快速停止、來源整體 timeout、部分成功保留、新舊時間不混淆與原始數量仍可展示。若要換 API 或申請 key，先確認官方現行文件和帳戶可用權限，歷史 403／429 不代表永久不可用。
