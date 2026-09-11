#!/usr/bin/env python3
"""
提交前的歷史資料防覆蓋守門員。

背景：update-data.yml 的提交步驟會 `git reset --soft origin/main` 後 `git add data/`，
把「這個 run 工作區算出的檔案」整份蓋到最新遠端上。若這個 run 在某個回填 PR 合併「之前」
checkout（工作區是舊資料），就會把遠端較完整的累積歷史蓋掉——回填進來、但當下新聞已抓不到
的日子（例如共軍架次的舊日期）會被永久抹除。

解法：提交前先把 origin/main 的歷史檔「聯集」回工作區（逐鍵取較大值 / 補齊缺鍵），
再依聯集後的 pla 歷史重算 data.json 的 pla 區塊。這樣任何 run 都只會「補齊」歷史、
永不縮水。此腳本需在 `git fetch origin main` 之後、`git add` 之前執行。
"""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_FILE = DATA_DIR / "data.json"
PLA_FILE = DATA_DIR / "pla_adiz.json"


def _remote(path_rel: str):
    try:
        raw = subprocess.check_output(["git", "show", f"origin/main:{path_rel}"],
                                      stderr=subprocess.DEVNULL)
        return json.loads(raw)
    except Exception:
        return None


def _load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _union_days(local: dict, remote: dict, key="aircraft") -> dict:
    """逐日聯集：遠端有而本地無 → 補上；兩邊都有 → 取 aircraft 較大者。"""
    ld = dict((local or {}).get("days") or {})
    rd = (remote or {}).get("days") or {}
    for k, v in rd.items():
        cur = ld.get(k)
        if cur and cur.get('verified') and not v.get('verified'):
            continue
        if (not cur) or (v.get('verified') and not cur.get('verified')) or (v.get(key, 0) or 0) > (cur.get(key, 0) or 0):
            ld[k] = v
    return ld


def _union_months(local: dict, remote: dict) -> dict:
    """月歷史：遠端有而本地無的月份補上（本地為準，只補缺）。"""
    lm = dict((local or {}).get("months") or {})
    rm = (remote or {}).get("months") or {}
    for k, v in rm.items():
        lm.setdefault(k, v)
    return lm


def merge_pla():
    remote = _remote("data/pla_adiz.json")
    local = _load(PLA_FILE)
    if remote is None and local is None:
        return
    days = _union_days(local or {}, remote or {})
    # 滾動保留 30 天（與 fetch_data.py 一致）
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) + timedelta(hours=8) - timedelta(days=30)).date().isoformat()
    days = {d: v for d, v in days.items() if d >= cutoff}
    PLA_FILE.write_text(json.dumps({"days": days}, ensure_ascii=False), encoding="utf-8")

    # 依聯集後的歷史，重算 data.json 的 pla 區塊，讓圖表立即一致
    data = _load(DATA_FILE)
    if data is None:
        return
    series = [{"date": d, **days[d]} for d in sorted(days)]
    acs = [x["aircraft"] for x in series]
    baseline = sorted(acs)[len(acs) // 2] if acs else 0
    data["pla"] = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "days": series, "baseline": baseline,
        "latest": series[-1] if series else None,
        "note": "新聞標題架次估計（未逐筆核對國防部，發稿日非觀測日）· 非即時 · 過去 30 天滾動累積",
    }
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def merge_months(rel: str, path: Path):
    remote = _remote(rel)
    local = _load(path)
    if remote is None:
        return
    months = _union_months(local or {}, remote or {})
    path.write_text(json.dumps({"months": months}, ensure_ascii=False), encoding="utf-8")


def merge_metrics_daily():
    """每日指標長期封存：遠端有而本地無的日期補上（本地為準，只補缺），保留 ~2 年。"""
    from datetime import timedelta
    path = DATA_DIR / "metrics_daily.json"
    remote = _remote("data/metrics_daily.json")
    local = _load(path)
    if remote is None and local is None:
        return
    days = dict((remote or {}).get("days") or {})
    for k, v in ((local or {}).get("days") or {}).items():
        days[k] = v  # 本地（這次執行）為準
    cutoff = (datetime.now(timezone.utc) + timedelta(hours=8) - timedelta(days=730)).date().isoformat()
    days = {d: v for d, v in days.items() if d >= cutoff}
    path.write_text(json.dumps({"days": days}, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    merge_pla()
    merge_months("data/food_history.json", DATA_DIR / "food_history.json")
    merge_months("data/strat_history.json", DATA_DIR / "strat_history.json")
    merge_metrics_daily()
    print("history merge guard applied")
