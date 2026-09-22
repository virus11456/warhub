---
name: warhub-osint
description: "Maintain WARHUB ADS-B, FIRMS, EONET, GDELT, USGS, Wikipedia and NOTAC/FAA NOTAM collectors. Use for source outages, observation freshness and raw-count versus anomaly-score mismatches."
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
| `fetch_notams` | NOTAC API（有 key）／FAA 舊路徑（無 key）；`notams` | 領空公告，查詢成功的空清單與 403／缺資料不同；不能用舊公告冒充新觀測 |

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

## 跨批次本機索引

`scripts/gdelt_event_index.py --source <批次目錄> --database <SQLite檔>` 純離線匯入已保存且通過manifest／ZIP驗證的批次。以GlobalEventID連結mentions；事件每批版本保留，mentions按eventID＋mentionTime＋URL＋sentence去重，批次來源另存。相同批次相同雜湊不重複匯入，內容變動拒絕而非覆蓋；一批交易寫入，失敗不留下半批。

早期事件主檔缺少的mentions保留，後補批次可自動連結；只計已取得首末批次間15分鐘缺漏範圍，沒有gap不等於完整全天。article URL數不是獨立媒體數，也不是已核實事件數。資料庫／summary保存於指定目錄，可重新開啟及累積；原ZIP為重建依據。

手動gdelt_events probe artifact新增index與summary，但每個GitHub runner仍是獨立目錄，尚未跨run下載舊artifact或建立正式排程儲存；不能宣稱伺服器已持續累積。tests/test_gdelt_event_index.py驗證孤立提及後補、去重、修訂版本、缺批與失敗保護。

## 正式定期取樣與跨runner保存

`scripts/collect_gdelt_events.py` 在既有Update data成功收集後檢查data.json.gdelt_events_sampling.attempted_at，至少6小時間隔；fast模式略過，沒有新增cron。每次僅latest單批（最多3請求），不保證完整15分鐘事件流。失敗保留原index／last_success_at，stale=true並記attempted_at，避免頻繁重試；不發通知、不參與WPI。

原始ZIP以base64包入gzip，含manifest／取得時間，保存到archives/gdelt-events/<批次>_<SHA256>.json.gz。沿用來源封存暫存及Git推送重試，純資料／來源archive不部署。artifact是30天復原副本，GitHub archives才是長期資料。Vercel排除archives部署檔案。

每輪從GitHub checkout保留的最近32批原始archive驗證並重建SQLite索引（暫存記憶體），summary寫data.json.gdelt_events_sampling.index；舊原始archive不刪除，可離線全量重建。index視窗之外的事件可能無法連結，不代表原始資料消失。summary標示已處理批次與內部缺批；仍未加入前台事件列表。

tests/test_gdelt_sampling.py驗證6h限制、錯誤保留舊資料、archive還原與跨目錄重建；tests/test_deploy.mjs驗證來源新增不部署。主workflow對此額外步驟設2分鐘上限且錯誤不阻斷其他資料提交；強制逾時可能來不及寫attempted_at，不能宣稱所有失敗都已保存。

## FAA 跨輪退避與正式介面

fetch_notams遇401／403／429沿用cooldown_active／cooldown_deadline，預設6小時，Retry-After秒數限制1至24小時，保存到地區cooldown_until。冷卻期間零請求、原觀測時間不變且stale；無歷史值只記缺資料，不填零。成功恢復的地區用新觀測取代冷卻標記。測試test_notam_backoff.py覆蓋首次拒絕、跨輪重用及到期恢復。此機制只减少無效請求，不代表資料恢復。

FAA官方NMS頁與FAQ目前指引透過7-AWA-NAIMES@faa.gov申請NMS-API存取及文件：https://www.faa.gov/about/initiatives/notam 、https://www.faa.gov/about/initiatives/notam/faqs 。現有NOTAM Search網頁端點不是已授權的新API；未取得介面文件及存取前不能猜測URL或宣稱已遷移。申請或寄信需依使用者授權，skill不授予外部訊息權限。

Telegram摘要使用「目前可見軍機（ADS-B覆蓋不完整）」，逐項顯示分類數；缺欄位不補0，有效0保留，部分資料明示。航空／FIRMS的來源或source_health過期與錯誤優先顯示狀態，不把舊值當目前數量；FIRMS熱異常明示不等於戰火。tests/test_alert_content.py純離線覆蓋partial、stale、error、零值及缺資料，不增加來源請求或測試推播。

## NOTAC 正式 API 接入

2026-09-15 Denis 回信確認指定 FIR 覆蓋、可公開衍生摘要及可留存 API 副本。帳戶已註冊，使用者確認已存 GitHub Secret `NOTAC_API_KEY`。官方 authentication 文件的「尚無自助註冊」與目前帳號頁不一致，以已登入頁面為準；terms 頁尚未完整核對，不展示 NOTAC 自動產生的 readings／長文，公開介面僅展示自算統計與來源連結。

入口仍為 fetch_data.py:fetch_notams；有 NOTAC_API_KEY 時使用 notac_client.collect_regions，沒有 key 保持 FAA 舊路徑。來源失敗不切回 FAA 假裝新觀測。五區沿用 REGION_FIRS（UKBV、OIIX/LLLL、RCAA、ZKKP、RPHI）；每區 GET /api/v1/notam/，fir列表、status=active、sort=newest，最多2頁，每頁2credits。每輪最多10請求／20credits，逐來源至少110分鐘（含失敗），約兩小時排程每31天最多7440credits；更密的110分鐘理論上限約8120，額外手動驗證另計。帳戶10,000月額度、UTC月初重置，Beta後可能縮減，不能保證永久免費。每次讀X-Credits-Remaining，低於20暫停至下月，不買超額。

401/403停止後續區域並保存24h冷卻；402至下一UTC月初；429遵循Retry-After，不立即重試。分頁next必須同HTTPS主機、路徑與篩選，禁止redirect與key進URL；2MB上限、每頁20秒、每區42秒。缺count/next、頁面總數不符、重複ID、FIR不符、非active均不完整。完整合法空清單才total=0；其他total未知。最新部分結果放latest_attempt，保留旧observed_at/total/score並stale，舊值不計分。NOTAC查詢時間是取得 API active 狀態公告樣本的時間，active 不保證已進入生效期間，不冒充公告發布時間；公告原effective_start/end等留在來源metadata。

完整結果沿用既有關鍵字候選與人工score公式；僅同NOTAC來源、相同FIR、兩次完整且間隔不超過6h才算total_change，不比較FAA舊值。變化不是戰爭機率或軍事行動證據。index.html新增五區NOTAM觀察，顯示缺值、部分樣本、舊時間及比較累積；root過期時重繪，6h後停判讀。

source metadata以notac/<取得時間>_<SHA256>.json.gz不可覆寫保存，沿用WARHUB_SOURCE_ARCHIVE_DIR与既有Git/artifact封存。只存ID、編號、FIR、Q-code、狀態與來源時間欄位，不存token、readings或完整原文；不能聲稱全部HTTP回應已封存。測試test_notac_client.py全用合成fixture與mock，驗證限額、部分資料、零值、來源退避、原時間保留和archive。

手動Verify NOTAC access workflow執行scripts/check_notac.py：只讀RCAA最多2頁（最多4credits），無其他爬蟲、無通知、無正式data寫入，提供30天去除rows的摘要artifact。這是真實API呼叫，不能當離線測試；依本次串接驗證授權單次執行，失敗先看代碼不連續重跑。完整查詢或已核實的分頁預算停止可確認存取，但後者不表示資料齊全。

官方文件：https://notac.aero/api/search-notams/ 、https://notac.aero/api/authentication/ 、https://notac.aero/api/credits/ 、https://notac.aero/api/rate-limits/ 。文件示例count與列數可能不一致，真實資料仍須檢查，不照示例放寬完整性。

2026-09-15 03:08（台北）單次 Verify NOTAC access 已實測金鑰可用：RCAA 來源回報600筆，依2頁上限只取40筆，使用4credits、剩9996；reason=page_budget_reached，complete=false。這只是取得當時回應，不是現在額度或正式快照；不能宣稱600筆已收齊。未發通知、未寫正式data，不以這份驗證摘要冒充正常排程觀測。

樣本分析：collect_regions 新增 sample_danger/sample_closure，只計已驗證返回的 rows，不外推全FIR；sample_timing 依有時區的 effective_start/end 分 current/future/ended/unknown，缺起訖／矛盾時間保留unknown，API active不等於目前已生效。這些樣本欄位隨來源metadata封存；失敗仍保留旧 observed_at，另存 observed_provider 區分舊FAA數值。前端逐區顯示樣本及完整性，不把0個關鍵字候選當作0公告或已證實沒有軍事用途。測試 test_notac_client.py 覆蓋時段、部分樣本與來源保存。

cross-context.js 是純前端衍生閱讀排序，使用既有台海洞察與 NOTAC 最新嘗試；同題20–28小時比較且未到期才按 abs(delta_pp) 找出目前已展示題目中最大變動，不平均／加總不同YES題目，不推論風險方向。並列公告樣本覆蓋與原查詢時間，時間超過6小時停止。不是新來源抓取、因果檢驗或戰爭機率模型；不寫資料、不改WPI、不通知。test_cross_context.cjs 離線驗證缺值、有效0、期限、部分資料、原資料不變。

NOTAC 封存路徑 archives/notac/<ISO查詢時間（冒號換連字號）>_<SHA256>.json.gz 已納入 vercel-ignore-build.cjs 純資料跳過清單；與live data／其他archive同改時不部署。未部署的程式仍會觸發build，來源收集與保存頻率不變。test_deploy.mjs 以真實Git差異驗證。


## 2026-09-22 第一階段：NOTAC Delta 續接
上述2頁search僅保留給check_notac手動工具；正常fetch_notams透過collect_regions(incremental=True)改用notac_sync.collect_delta。官方https://notac.aero/api/notam-delta/：首次不送cursor，依next/next_cursor原樣續接，追上後取得修訂與撤銷。未加category/tag等會變更的主題篩選，FIR範圍沿用既有設定（中東為OIIX/LLLL同範圍）。目前未另做每日全量重建；來源若將公告移出FIR且不發withdrawal可能造成鏡像殘留，此限制仍需後續核驗。
每區每輪最多2頁，但保存sync_state後下一輪接續，不重抓首頁。共享最多8請求／輪、90／UTC日、2800／UTC月；delta每請求3credits，月上限8400credits（只涵蓋本程式已保存計數，手動工具／其他客戶端另計）。讀remaining少於23停止，保留20credit餘裕，401/403/402/429沿用共享冷卻。無新cron、不強制收集。
sync_state在notams各區內保留不透明cursor、FIR範圍、as_of、逐ID最小metadata與已解析關鍵字布林，無token/readings/原文。每頁全量驗證後才原子更新records及cursor；重複ID為upsert，slim撤銷按ID移除；失敗保留上一成功位置。只在next=null、as_of有效且未過6h時complete=true；部分狀態不計分，舊observed_at保留。已到截止／尚未開始的公告不加入目前總量；原欄位在state保留。不同protocol不接續比較。
sync_budget保存每區請求計數，先扣再I/O，成功提交快照後跨runner沿用；整個job或提交失敗可能遺失該輪計數，不能宣稱帳戶硬性總額度。來源回應remaining與月初冷卻仍保護免費方案。正常analysis/source archive保留狀態版本，無需另寫data檔。
tests/test_notac_sync.py離線驗證跨輪補齊、重複與修訂、撤銷、失敗不跳頁、原資料不变、來源時間、跨日月與本輪預算、有效0、舊觀測保存；原search工具測試保留。合併或部署不等於自然排程已完成初始同步，需另查正常快照的protocol／sync_state與complete。
