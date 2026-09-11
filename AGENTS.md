# WARHUB 資料抓取維護

本專案的爬蟲 skills 位於 `.agents/skills/`。資料抓取、来源故障、解析或排程工作，先依 `.agents/skills/warhub-collection/SKILL.md` 選擇相關來源 skill。

新增或修改爬蟲時，同步維護對應 skill 的入口、欄位語意、頻率、錯誤處理與驗證方式；現有所有 `fetch_*` 入口都需有對應 skill。沿用 repository 中的實作，不複製成第二套爬蟲。文件變更不需實際執行收集或推播。

資料缺值、過期值與有效零值保持區別。保存歷史與原觀測時間，批次提交避免頻繁部署；實際更新及通知依使用者既有授權執行，skills 不構成額外授權。
