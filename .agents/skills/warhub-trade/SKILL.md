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

專案目前用 UN Comtrade public preview (`https://comtradeapi.un.org/public/v1/preview/C/M/HS`)，不是 WTO API。鏡像是選定出口國 `flowCode=X, partnerCode=156` 的對中出口；中國直報是 `reporterCode=156, flowCode=M, partnerCode=0`。兩者涵蓋範圍不同，不能直接拼成同口徑同比或稱為中國完整進口量。

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

官方資料可用性API（getDa）依官方文件需要訂閱key；現有public preview不具同等語意。COMTRADE_API_KEY尚未驗證前，不宣稱已接入，也不能把空資料說成官方尚未公布。月份公布沒有固定期限。來源：https://uncomtrade.org/docs/data-availability/ 。
