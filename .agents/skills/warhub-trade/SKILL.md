---
name: warhub-trade
description: "Maintain WARHUB UN Comtrade food and strategic-material imports, monthly backfills and USDA ESR sales. Use for missing months, exporter coverage, mirror estimates and unit or marketing-year errors."
---

# WARHUB 中國進口與出口銷售

入口均在 `scripts/fetch_data.py`，相關組裝在 `scripts/usda.py`、合併在 `scripts/merge_history.py`。執行界線見 [抓取與封存](../warhub-collection/SKILL.md)。

| 入口 | 輸出 |
|---|---|
| `fetch_food_imports` | `data.json.food`，大豆／小麥／玉米當期與同期 |
| `fetch_food_history` | `food_hist` 與 `data/food_history.json` |
| `fetch_strategic_imports` | `data.json.strat`，天然橡膠／鎳礦砂／鉻礦砂／鐵礦砂 |
| `fetch_strategic_history` | `strat_hist` 與 `data/strat_history.json` |
| `fetch_usda_esr` | `data.json.usda`，美國對中國出口銷售；需 `USDA_FAS_API_KEY` |

## Comtrade 資料與覆蓋

專案透過 `scripts/comtrade_client.py` 共用傳輸層；設定 COMTRADE_API_KEY 時使用已驗證的 `data/v1/get/C/M/HS`，未設定才用 public/v1/preview/C/M/HS，不是 WTO API。金鑰只放 Ocp-Apim-Subscription-Key header，不能寫入 URL／報告。鏡像是選定出口國 `flowCode=X, partnerCode=156` 的對中出口；中國直報是 `reporterCode=156, flowCode=M, partnerCode=0`。兩者涵蓋範圍不同，不能直接拼成同口徑同比或稱為中國完整進口量。

商品 HS code 與出口國以 `FOOD_CMDS`、`FOOD_EXPORTERS`、`STRAT_MATERIALS` 為準。核對 period、flow、partner、商品、重量單位及總項／分項是否重複；netWgt 為 kg，除以 1e7 才是萬噸。不得拿貿易金額當重量。

空回應、缺商品、沒有 netWgt 都不等於零進口。保存 schema_version、src、coverage／reporter_codes、incomplete 與觀測期間；同期比較需檢查相同回報國，樣本不同則不能斷言異常變化。進口增減也可能是價格、季節、需求或延遲，不能單憑差額推論備戰。

## 節流與回填

auto 的慢來源 6 小時只代表檢查資格；有效 Comtrade 當期資料內部有 22 小時快取，USDA 有 6 小時快取。月歷史外層 24 小時檢查；沿用 `HIST_*_BUDGET`、`STRAT_HIST_*_BUDGET` 的既有額度與逐請求間隔，不因圖表缺月就一次抓多年。

戰略歷史目前按 `recheck_attempted_at` 輪替未核驗／不完整／缺月，留額度給最新月。完整性依每商品應回報國集合，不是只看 schema_version=2。新回應缺少先前回報國時，保留較完整舊商品值與覆蓋，不能把兩個重疊總數直接相加。未核驗舊格式不繪圖；缺月用 gap，而非零柱。保留歷史讓後续核驗，勿刪檔重建。

## USDA

使用官方 commodities、countries、datareleasedates 取得中國代碼、商品及可用年度，按商品的 marketing year 查詢，不用日曆年硬套。`scripts/usda.py` 將當年度與次年度淨銷售分開；可能有負數取消訂單，不能直接截成零。出口銷售／承諾量不等於已運抵進口量，也不代表中國全球總量。

驗證 `tests/test_trade_revalidation.py`、`tests/test_integrity.py` 及相關 DOM 歷史圖表案例。用代表性回應核對單位、部分回報、同一國去重、年度切換、歷史聯集；來源尚未回報就明確說資料待補，不承諾回填期限。

## 完整度與同比展示

`scripts/trade_quality.py` 從既有快照與歷史產生 current_complete、comparison_status、latest_complete。完整以每商品確切追蹤國集合判定，不只比國數；歷史必須 schema_version=2、src=mirror、coverage完全一致且數值有限非負。中國直報不得充作鏡像的最近完整月份。當期收齊與同比可比較分開：去年缺資料／零基期／stale不顯示同比，不以四捨五入後重量重算百分比。latest_complete可為零，但必須有完整回報。

糧食歷史回查若新結果僅涵蓋舊回報國的子集合，保留原商品值、覆蓋與美國分量；不得將部分新值與舊總量相加。驗證tests/test_trade_quality.py。

官方另提供免金鑰與認證資料目錄；目錄記錄不等於商品重量完整。月份公布沒有固定期限。來源：https://uncomtrade.org/docs/data-availability/ 。

## 可用性預覽節流

已整合 `scripts/trade_availability.py` 的免金鑰 `public/v1/getDA/C/M/HS`，按reporterCode與period查月度HS資料集，正式main共用session狀態與鎖，避免重複。每輪最多4次額外metadata請求、每次5秒；成功可用快取24小時，未列出／未知6小時；最多512筆保存在data.json.trade_availability，沿用時不刷新checked_at。碰到拒絕、限流、格式錯誤或逾時停止本輪metadata。

只有格式及查詢範圍驗證通過、count=0的明確空結果才略過該國該月商品查詢；名稱為not_listed，不宣稱官方未公布或零貿易。查詢錯誤、expired cache、預算耗尽均沿用原商品查詢流程，不能把未知變成未公布。正面資料集記錄也不能當作商品重量完整或追蹤國全數齊備。有金鑰時只沿用有效目錄快取，不再追加公共目錄請求，改由認證商品查詢確認資料，減少跨端點流量。

驗證tests/test_trade_availability.py：空結果、錯誤、錯誤國別／月份、預算、快取過期與同session去重。此module沿用現有收集排程，不觸發額外部署或通知。

## 認證商品傳輸與正式驗證

四個 `_comtrade_*` 入口共用 session 的鎖與至少3秒請求間隔；每輪最多80次商品查詢、180秒傳輸時間窗（單請求最多30秒）。遇401／403／429停止本輪，保存cooldown_until到data.json.trade_api；429使用Retry-After秒數（60秒至24小時），缺少／無法解析時1小時。錯誤不改走無金鑰端點繞過限制，也不將缺值轉零。保留既有當期快取與漸進回填排程。

trade_api只保存模式、狀態、請求／成功次數、冷卻期限；沒有金鑰。驗證回應國別、月份、商品、貿易方向、夥伴、運輸與海關總項；同商品重複總項、錯誤範圍、截斷或無效重量拒用。netWgt缺值保持缺值，有效0保留。

`.github/workflows/update-data.yml` 注入COMTRADE_API_KEY。手動 Probe upstream sources 選comtrade（預設）只執行 `scripts/probe_comtrade.py`，透過正式 `_comtrade_one` 查澳洲202607對中國鐵礦砂一筆，無資料寫入、無通知；all才是舊全來源探測。驗證 `tests/test_comtrade_client.py` 的scope、零／缺值、認證header、節流、跨輪冷卻與預算。

## 逐次查詢資料保存

`scripts/source_archive.py` 保存每次通過scope驗證的Comtrade回應：白名單查詢條件、fetched_at、官方回傳重量／金額／估算旗標等欄位與weights_kg。不是完整HTTP封包，不存header、key或任意回應欄位。空資料存空陣列／空字典，不能改成0。內容雜湊與時間命名gzip，不覆蓋舊版本；修訂值另存新檔。

正式workflow設WARHUB_SOURCE_ARCHIVE_DIR，將來源紀錄合併到本輪archives後隨既有資料提交保存GitHub；推送重試時保留遠端archives與本輪新檔。純archives檔案符合既有Vercel略過規則。另上傳30天Actions artifact供後續步驟失敗時取回；workflow被強制取消／逾時前尚未上傳的檔案不保證保存。

手動comtrade probe同樣保存來源artifact（30天），不改正式儀表板資料或推播。來源紀錄從此版啟用後開始；早先只有分析快照／log，不宣稱能還原當時所有原始回應。同session相同查詢重用副本，不再次網路查詢／刷新取得時間／重複存檔；跨輪仍依來源快取與重新核驗政策。驗證tests/test_source_archive.py的round-trip、修訂並存、零與缺值、憑證排除與重用。

## 當期重新查詢防縮水

`preserve_current_coverage` 保護food／strat當期整組快照：同ref_month若任一商品失去已知回報國、有效重量變缺值，或相同去年月份的基期覆蓋縮水，保留上一組快照與原updated_at，stale=true、last_attempted_at記本輪時間、refresh_status記原因。參考月倒退也不覆蓋。保留整組避免混用不同時間的總量；新的部分觀測仍留在來源archives，尚不直接拼接。

同一國集合的正式修訂可以降低至0；新月份照實顯示部分資料，不拿舊月份湊數。stale資料不算新同比或異常。驗證tests/test_trade_current_preservation.py的覆蓋縮水／換國、基期缺報、修訂為0、換月及原時間保存。
