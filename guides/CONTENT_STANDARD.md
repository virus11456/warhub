# WARHUBS 避難指南 — 文章產出規格與流程

> 這份文件是所有「避難指南」文章的**發佈標準與流程**，每次新增或改寫文章都必須逐項通過。
> 目的：確保文章實用、可信、原創、對搜尋友善，並與站內其他文章互相串連。

## 發佈前檢查清單（7 項，缺一不可）

| # | 項目 | 標準 | 如何驗證 |
|---|------|------|----------|
| 1 | 純中文正文字數 | **> 2000 字**（只計中文字，不含標點/英數/程式） | 見下方「字數檢查」指令 |
| 2 | 外部權威連結 | **≥ 2 個**（政府／WHO／CDC／紅十字會／NCDR 等，`target="_blank" rel="noopener"`） | 人工確認來源可信＋連結回應 200 |
| 3 | 三層內鏈 | ①麵包屑（首頁→指南→本文）②內文脈絡連結 ③文末相關文章卡片 | 檢視三處皆有站內連結 |
| 4 | CC 授權圖片 | 下載自 Wikimedia Commons 等，**存放於 `guides/img/`**，`<figcaption>` 標註作者＋授權＋原始連結 | 檢視 figure/figcaption |
| 5 | HTML 表格 | **至少 1 個 `<table>`**，把數字/比例/比較整理成表 | grep `<table>` |
| 6 | FAQ 區塊 | 頁面含 `<h2>常見問答</h2>` ＋ `application/ld+json` 的 **FAQPage** 結構化資料 | grep `FAQPage` |
| 7 | 發佈前查重 | 與站內其他文章、及外部來源比對，確保**原創、非重複**（見下方查重流程） | 見「查重流程」 |

## 撰寫流程（每篇）

1. **選題與定位**：確認屬於哪一分類（戰爭前／戰爭時／災難生存），主關鍵字是什麼。
2. **找權威來源**：先蒐集 ≥2 個可信來源，實際開啟確認內容與連結有效（`curl -I` 或瀏覽器）。
3. **找 CC 圖片**：到 Wikimedia Commons 找 CC BY / CC0 / 公有領域圖片，記下作者與授權，`curl` 下載後用 PIL 壓到寬約 1200px、存 `guides/img/`。
4. **撰寫正文**：用自己的話原創撰寫（不可貼原文），> 2000 中文字；加入 ≥1 表格、脈絡內鏈、warning/tip/check 提示框。
5. **加 FAQ**：5–6 題常見問答 ＋ 對應的 FAQPage JSON-LD。
6. **三層內鏈**：麵包屑、內文連到相關文章、文末相關卡片。
7. **查重**：跑查重腳本，確認與既有文章無過度重疊。
8. **驗證**：跑字數與規格檢查腳本，全綠才發佈。
9. **更新總覽頁** `guides/index.html`：把該文章從「即將推出」改為正式連結。

## 字數與規格檢查（指令）

```bash
python3 - <<'PY'
import re,glob,os
for f in sorted(glob.glob('guides/*.html')):
    if os.path.basename(f)=='index.html': continue
    h=open(f,encoding='utf-8').read()
    b=re.sub(r'<head>.*?</head>','',h,flags=re.S)
    b=re.sub(r'<script.*?</script>','',b,flags=re.S)
    b=re.sub(r'<[^>]+>',' ',b)
    zh=len(re.findall(r'[一-鿿]',b))
    print(f"{os.path.basename(f):26} 中文{zh:5}  表格{h.count('<table>')}  FAQ{'✔' if 'FAQPage' in h else '�’'}  外部{len(re.findall(chr(34)+'https?://(?!warhubs)',h))}  CC{'✔' if 'creativecommons' in h or 'commons.wikimedia' in h else '✗'}")
PY
```

## 查重流程（發佈前）

- **站內查重**：跑下方腳本，計算新文章與每篇既有文章的 3-gram 重疊率；> 30% 需改寫。
- **對來源查重**：正文一律用自己的話改寫，不可整段貼上來源原文；數據與定義可引用但需重寫敘述並標註出處。

```bash
python3 - <<'PY'
import re,glob,os,itertools
def toks(f):
    h=open(f,encoding='utf-8').read()
    b=re.sub(r'<[^>]+>',' ',re.sub(r'<script.*?</script>|<style.*?</style>','',h,flags=re.S))
    z=re.findall(r'[一-鿿]',b); return set(''.join(z[i:i+3]) for i in range(len(z)-2))
fs=[f for f in glob.glob('guides/*.html') if os.path.basename(f)!='index.html']
for a,b in itertools.combinations(fs,2):
    A,B=toks(a),toks(b)
    if A and B:
        j=len(A&B)/len(A|B)*100
        if j>15: print(f"{j:5.1f}%  {os.path.basename(a)} vs {os.path.basename(b)}")
print("（未列出＝重疊 <15%，視為原創）")
PY
```

## 已用過的權威來源（可重複使用，先確認仍為 200）

- WHO 飲用水：https://www.who.int/news-room/fact-sheets/detail/drinking-water
- WHO 家戶淨水：https://www.who.int/teams/environment-climate-change-and-health/water-sanitation-and-health/water-safety-and-quality/household-water-treatment-and-safe-storage
- 衛福部疾病管制署（台灣 CDC）：https://www.cdc.gov.tw/
- 國家災害防救科技中心 NCDR：https://www.ncdr.nat.gov.tw/

## 文章狀態

| 分類 | 檔案 | 狀態 |
|------|------|------|
| 戰爭前 | emergency-bag.html | ✅ 完整版（2,090 字）|
| 戰爭前 | home-stockpile.html | ✅ 完整版（2,085 字）|
| 戰爭前 | family-plan.html | ✅ 完整版（2,039 字）|
| 戰爭時 | air-raid.html | ✅ 完整版（2,130 字）|
| 戰爭時 | evacuate-or-stay.html | ✅ 完整版（2,035 字）|
| 戰爭時 | comms-blackout.html | ✅ 完整版（2,040 字）|
| 災難生存 | **water-purification.html** | ✅ **完整版（符合全部 7 項，範本）** |
| 災難生存 | power-water-outage.html | ✅ 完整版（2,285 字）|
| 災難生存 | first-aid-basics.html | ✅ 完整版（2,123 字）|
| 災難生存 | nbc-basics.html | ✅ 完整版（2,063 字）|

> **全部 10 篇皆已達標**（純中文 >2000、表格、FAQPage、≥2 外部權威、CC 圖片、三層內鏈、站內查重 <15%）。

> 追加圖片授權：
> - `img/power-outage.jpg` — ViajeroExtraviado，CC0（公有領域）
> - `img/first-aid-kit.jpg` — 美國 CDC，公有領域
> - `img/emergency-radio.jpg` — Joe Haupt，CC BY 2.0（emergency-bag）
> - `img/radiation-symbol.png` — Garam，公有領域
> - `img/stockpile.jpg` — 美國國會圖書館館藏歷史照片（作者不詳），公有領域（home-stockpile）
> - `img/assembly.jpg` — Philip Mallis，CC BY-SA 4.0（family-plan）
> - `img/air-raid.jpg` — Alex Blokha，CC BY-SA 4.0（air-raid，烏克蘭第聶伯羅防空避難標示）
> - `img/evacuate.jpg` — DimiTalen，CC0（evacuate-or-stay）

> 圖片授權：`guides/img/boiling-water.jpg` — 作者 GRAN，CC BY 3.0，來源 https://commons.wikimedia.org/wiki/File:Boiling_water.jpg
