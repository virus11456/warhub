---
name: warhub-kalshi
description: Prepare or maintain Kalshi market normalization and explicitly reviewed cross-platform comparisons.
---

# Kalshi 市場整合（離線轉換與共用篩選，資料接入尚未啟用）

先讀 AGENTS.md 與 warhub-collection／warhub-polymarket。2026-09-22尚未取得WARHUB公開展示、翻譯、歷史保存、衍生分析與再散布的明確資料授權；不把免金鑰API視為公開再利用授權。此次只有scripts/kalshi_market_data.py離線轉換與合成測試，無fetch入口、排程、HTTP請求、API key、推播或已上線UI。不得聲稱正式串接完成。

官方文件：https://docs.kalshi.com/getting_started/quick_start_market_data ，https://docs.kalshi.com/api-reference/market/get-markets 。API使用external-api.kalshi.com/trade-api/v2；公開讀取不需帳戶金鑰。使用條件參照https://kalshi-public-docs.s3.amazonaws.com/Kalshi-Developer-Agreement.pdf 第3.1節及資料條款；書面確認前只保留程式／合成fixture。不要改用網頁爬蟲規避同一資料限制。

normalize只接受binary，保留provider/ticker、標題原文、yes/no條件、規則指紋、close_time與其他expiration欄位；close_time不自動當成事件截止或結算時刻。美元價格0–1、量為contracts而非美元；yes_bid/ask與last_price分開。僅active未到期、兩側有正量且bid≤ask時顯示明確標示的bid/ask中價；空簿、缺值、過期不填零。更新時間保留source_updated_at，不冒充成交／報價觀測時間；fetched_at另存。不把中價稱為校準後真實機率。

reviewed_pair須有人審核同一事件、相同Yes方向、事件期限與結算條件，並核對雙方市場id與規則指紋；題目相似不自動配對，規則更動使審核失效。未來仍須補市場挑選、官方連結、中文翻譯、原觀測時間／7天以上歷史與約24h同題比較、頻率／分頁守門、錯誤／429處理、UI和端到端驗收；目前未完成這些連線層。不能直接塞入Polymarket陣列或WPI計分造成重複計權。

離線驗證：python -m unittest discover -s tests -p test_kalshi_market_data.py -v。所有案例為synthetic，不能顯示為真实市場紀錄。文件和測試不授予寄信、交易或付費升級權限。

使用者指定沿用現有Polymarket篩選：select_markets現在呼叫market_selection.selected_market_risk，共用原EXCLUDE_KEYWORDS及scoring.market_risk，不再建立另一份軍事關鍵字。先normalize有效報價，依id去重、原文title篩選，保留escalation/deescalation方向；不輸出risk_score、不加入WPI。同題配對是後續價差比較的獨立步驟，不是納入列表的先決條件。10項離線測試（含實際Polymarket collector的mock回歸）與26項現有integrity測試通過；仍無HTTP抓取／公開展示。
