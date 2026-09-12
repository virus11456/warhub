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

## GDELT 時間與跨輪冷卻

`scripts/gdelt_quality.py` 從DOC timeline的UTC date取observed_at，另記fetched_at、window_start、point_count。至少6點、排序去重檢查，拒絕缺日期、非有限／負數／超過100的百分比、過遠未來與超出49小時窗口；最新點超過6小時標stale，不計分。6小時是本專案容忍門檻，不是官方服務承諾。

401／403／429保存cooldown_until到各地區紀錄（既有data快照會封存）；Retry-After秒數限制1至24小時，缺少或不可解析時6小時。冷卻期間零來源請求、舊觀測时间不刷新，無歷史數值僅存stale與冷卻欄位。保留區域輪替、來源總時間預算與已完成地區資料。tests/test_gdelt_quality.py、tests/test_source_budgets.py驗證。

其他官方可評估資料為Events、EventMentions、GKG及DOC/GEO產品（https://gdeltproject.org/data.html）。自動新聞事件不等於已證實事件；不可把Events計數替代原timelinevol百分比。批次檔案供應與解析尚待實測，不宣稱已接入。

## Events／Mentions 單批驗證工具

`scripts/probe_gdelt_events.py --output <資料夾>` 最多查lastupdate清單與同批export／mentions ZIP共3次，每次20秒／5MB上限。只允許官方主機、相同批次、有效清單MD5與位元組數，ZIP單一正確檔名／展開50MB上限；不extract路徑。以官方V2 codebook核對61與16欄，保留原始兩份ZIP、manifest、SHA256與帶時間JSON報告。同批檔案存在就驗證重用，報告另存時間版。

事件ID連結mentions、保留無法連結的早期事件數，去重鍵eventID＋mentionTime＋URL＋sentence。不把多篇提及當多個事件；confidence是辨識信心而非事實為真機率。ActionGeo國碼為FIPS，不混用Actor國碼。root13/15/18/19/20僅供候選，不等於軍事事件；不計WPI、不顯示為實證戰況、不發通知。

手動Probe upstream sources選gdelt_events，資料與報告提供30天artifact；正常排程尚未接入，沒有完整時間覆蓋。20260912141500本機樣本：1036事件／3126提及／3064去重提及，其中1980指向更早批次；跨批次索引是下一階段，不能把單批當一天全量。tests/test_gdelt_events_probe.py驗證清單限制、完整性、欄數、提及去重與未連結事件。
