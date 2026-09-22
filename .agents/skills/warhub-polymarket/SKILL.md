---
name: warhub-polymarket
description: "Maintain WARHUB Polymarket Gamma collection, market selection, event direction and Chinese questions. Use when market cards are empty, prices are suspect or ceasefire questions are scored incorrectly."
---

# WARHUB 預測市場

入口 `scripts/fetch_data.py::fetch_polymarket`，輸出 `data.json.polymarket`；計分見 `scripts/scoring.py::market_risk`、`market_average`。執行界線見 [抓取與封存](../warhub-collection/SKILL.md)，翻譯見 [中文新聞](../warhub-news/SKILL.md)。

每輪快來源，使用 Gamma 公開 API：先讀 `https://gamma-api.polymarket.com/tags/slug/geopolitics` 取得 tag id，再向 `/markets` 傳 `tag_id`、active=true、closed=false。目前按 volume24hr 降序最多三頁，每頁 100，依 conditionId／id 去重；這是篩選範圍，不代表全市場資料。

盤口空白時分層檢查 tag 查詢、分頁回應、到期／關閉狀態、軍事主題篩選及二元 outcome 解析。不要以 `tag_slug` 取代目前參數，也不要因國名命中就納入足球、電玩等市場。

依 Yes／No 標籤對應價格，勿假設第一個 outcome 永遠是 Yes。價格應為有限數值且在 0–1，交易量、到期日、原文與 slug 應保留；舊格式或失效市場不強制計分。停火／和平市場的 Yes 方向與軍事升級相反，方向判斷依 `market_risk` 的資格規則，不把所有 Yes 機率平均稱為戰爭機率。

`question_zh` 只對應相同 `question`。核對 by／before（期限前）、on（當日）、through（持續至）與 test／use 核武等差異；未知句型不得套模板改變事件。前端列表、地區卡、跑馬燈共用 `zhMarket`，保留原文 tooltip 與市場連結。

可展示市場價格不代表已驗證預測準確率；不同期限／事件定義不能直接比較。核對 `tests/test_integrity.py` 的市場案例、`tests/test_news_translation.py` 及 `tests/test_frontend.cjs`。驗證缺譯時仍保留正確價格與原文入口，而非捏造中文事件。


Kalshi共用篩選準備：scripts/market_selection.py::selected_market_risk抽出原fetch_polymarket的EXCLUDE_KEYWORDS前置排除，再原樣呼叫scoring.market_risk。Polymarket題目、價格、期限、停火方向與原篩選集合不变；WAR_KEYWORDS並不是現行fetch_polymarket的最終資格判斷。Kalshi離線select_markets使用同函式，無需跨平台配對才納入；同題價差配對另做審核。Kalshi仍須active有效雙邊報價，量單位contracts不等於Gamma美元volume。共用篩選已納入程式；Kalshi網路抓取與網站展示尚未啟用。tests/test_kalshi_market_data.py以原排除清單加market_risk比對兩平台選取結果，test_integrity.py驗證現有收集器。


2026-09-22後續：Kalshi現已透過獨立fetch_kalshi及網站區塊接線；使用者允許的外交／制裁／軍事政策背景題走明確series範圍，不改Polymarket原篩選。Kalshi不塞入polymarket陣列或market_average；同題價差仍須審核事件／期限／條款，不自動平均。詳見warhub-kalshi最新文件。
