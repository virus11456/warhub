---
name: warhub-news
description: "Maintain WARHUB Google News RSS collectors, Traditional Chinese title caching and Taiwan aircraft headline extraction. Use for missing or English headlines and incorrect PLA sortie counts."
---

# WARHUB 中文新聞與共機

從 repository root 讀 `scripts/fetch_data.py` 的 `fetch_gnews`、`fetch_tw_military_news`、`fetch_pla_sorties`、`_translate_titles`、`_translate_market_questions`，以及 `scripts/pla_counts.py`。總流程與執行界線見 [抓取與封存](../warhub-collection/SKILL.md)。

| 入口 | 來源與輸出 |
|---|---|
| `fetch_gnews` | Google News RSS `news.google.com/rss/search`；`data.json.news`，保留原文、連結、發稿時間與來源 |
| `fetch_tw_military_news` | 台灣語系 RSS `hl=zh-TW&gl=TW&ceid=TW:zh-Hant`；`data.json.tw_news` |
| `fetch_pla_sorties` | 共機相關 RSS 標題；`data.json.pla` 與 `data/pla_adiz.json`，30 天滾動歷史 |

每輪快來源抓取；發稿日不等於事件日。先比較 HTTP／RSS 解析、篩選後筆數、快取沿用和翻譯結果，分辨無新聞與無譯文。Google News 標題不會填補 GDELT 的量化新聞強度。

## 繁體中文

保留 `title_en`，中文寫 `title_zh`（新聞 `title` 同步中文），市場使用 `question`／`question_zh`。目前用 Google 翻譯端點 `translate.googleapis.com/translate_a/single` 的 `tl=zh-TW`，是有失敗風險的外部服務。單請求 8 秒、並行 2、整批 30 秒；不要為補齊標題無限重試。

只按完全相同原文復用翻譯；市場與新聞快取分開。純英文不能標成成功中文，重試前清除殘留譯文。中文原標題可直接保留；有漢字只是語言粗篩，不能證明整句完整、繁簡正確或語意正確。人工補譯時逐題核對人名、否定、日期與期限，不改價格、數量或觀測時間。

前端 `chineseTitle`／`zhMarket` 共用中文結果。失敗顯示中文未取得提示並保留原文入口，不用字詞替換假裝翻譯；同時報告缺譯數，不能把提示當成已翻譯。要提高未來成功率須處理來源故障／可用的翻譯服務，不能只補當前快照就聲稱永久修好。

## 架次解析

`21機艦`、`21機艦船` 是混合總數，不能記成 21 架飛機。只接受明確架次或可辨識的單獨機數；排除機型號碼、跨期累計。保存 `source_title`、`source_url`、`date_basis=publication_date`、`verified=False`；只有實際核對來源的紀錄才能標 verified。

同一天不同新聞不是可直接加總的獨立觀測。目前最大值合併只是估計；保留已核實紀錄，`usable_days` 防止舊混合總數從歷史合併回流。無來源的舊紀錄不是已核實，不能用填滿圖表當驗證。

驗證 `tests/test_news_translation.py`、`tests/test_pla_counts.py` 與涉及畫面的 `tests/test_frontend.cjs`；覆蓋翻譯失敗／原文變更、混合機艦數、機型數字與歷史合併。測試用 mock，不呼叫翻譯 API。
