#!/usr/bin/env python3
"""
提交前的歷史資料防覆蓋守門員。

必須在 git fetch origin main 後執行。工作流程先重設至最新 main 再放回本輪資料，
此處聯集遠端歷史，避免較早 checkout 的快照抹掉後來補齊的紀錄。
官方共機資料依核驗來源與檢查時間選擇；同月鏡像貿易避免失去已知回報國，
不相加重疊總量。維持各類歷史的既有保留期限；原始輪次另由 archives 保存。
"""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from pla_counts import usable_days
from pla_official import is_official, view as official_view

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_FILE = DATA_DIR / "data.json"
PLA_FILE = DATA_DIR / "pla_adiz.json"


def _remote(path_rel: str):
    """Required tracked histories must be readable; failure is never an empty history."""
    try:
        raw = subprocess.check_output(["git", "show", f"origin/main:{path_rel}"],
                                      stderr=subprocess.DEVNULL)
        value = json.loads(raw)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise RuntimeError(f"Cannot read required remote history: {path_rel}") from exc
    if path_rel == "data/history.json":
        valid = isinstance(value, list)
    else:
        field = "months" if path_rel in ("data/food_history.json", "data/strat_history.json") else "days"
        valid = isinstance(value, dict) and isinstance(value.get(field), dict)
    if not valid:
        raise ValueError(f"Invalid required remote history structure: {path_rel}")
    return value


def _load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _union_days(local: dict, remote: dict, key="aircraft") -> dict:
    """逐日聯集：遠端有而本地無 → 補上；兩邊都有 → 取 aircraft 較大者。"""
    ld = usable_days(dict((local or {}).get("days") or {}))
    rd = usable_days((remote or {}).get("days") or {})
    for k, v in rd.items():
        cur = ld.get(k)
        if is_official(v) or (cur and is_official(cur)):
            if is_official(v) and (not cur or not is_official(cur) or v.get('checked_at','') > cur.get('checked_at','')):
                ld[k] = v
            continue
        if cur and cur.get('verified') and not v.get('verified'):
            continue
        if (not cur) or (v.get('verified') and not cur.get('verified')) or (v.get(key, 0) or 0) > (cur.get(key, 0) or 0):
            ld[k] = v
    return usable_days(ld)


def _union_months(local: dict, remote: dict) -> dict:
    """Union months without losing previously covered reporters.

    Keep a whole saved monthly observation rather than adding overlapping totals.
    Equal/superset coverage still accepts local downward revisions, including zero.
    """
    from trade_quality import FOOD, codes, valid
    lm = dict((local or {}).get("months") or {})
    rm = (remote or {}).get("months") or {}
    for month, saved in rm.items():
        incoming = lm.get(month)
        if incoming is None or (saved.get("schema_version") == 2 and incoming.get("schema_version") != 2):
            lm[month] = saved
            continue
        if not (saved.get("schema_version") == incoming.get("schema_version") == 2
                and saved.get("src") == incoming.get("src") == "mirror"):
            continue
        for cmd, reporters in (saved.get("coverage") or {}).items():
            field = FOOD.get(str(cmd), str(cmd))
            known = codes(reporters)
            replacement = codes((incoming.get("coverage") or {}).get(cmd))
            if known and valid(saved.get(field)) and (
                    not known <= replacement or not valid(incoming.get(field))):
                lm[month] = saved
                break
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
    legacy = {**(remote or {}).get('unverified_days', {}), **(local or {}).get('unverified_days', {})}
    for d,row in list(days.items()):
        if not is_official(row):
            legacy.setdefault(d,row); del days[d]
    PLA_FILE.write_text(json.dumps({"days": days, "unverified_days": legacy}, ensure_ascii=False), encoding="utf-8")

    # 依聯集後的歷史，重算 data.json 的 pla 區塊，讓圖表立即一致
    data = _load(DATA_FILE)
    if data is None:
        return
    data["pla"] = official_view(days)
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def merge_months(rel: str, path: Path):
    remote = _remote(rel)
    local = _load(path)
    if remote is None:
        return
    months = _union_months(local or {}, remote or {})
    path.write_text(json.dumps({"months": months}, ensure_ascii=False), encoding="utf-8")


def merge_score_history(now=None):
    """Union observation times across push retries without fabricating factor metadata."""
    from datetime import timedelta
    path = DATA_DIR / "history.json"
    remote = _remote("data/history.json")
    local = _load(path)
    if remote is None and local is None:
        return
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=31)
    rows = {}
    # Local wins a same-time/model collision, except matching older-schema rows
    # must not strip known basis metadata. Conflicting scores remain whole rows.
    for source in (remote, local):
        for row in source if isinstance(source, list) else []:
            if not isinstance(row, dict):
                continue
            try:
                observed = datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
                if observed.tzinfo is None or not cutoff <= observed <= now:
                    continue
                model = row.get("model_version")
                if model is not None and not isinstance(model, str):
                    continue
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
            key = (observed, model)
            saved = rows.get(key)
            if (saved and isinstance(saved.get("score_basis"), dict)
                    and not isinstance(row.get("score_basis"), dict)
                    and {k: v for k, v in saved.items() if k not in ("ts", "score_basis")}
                        == {k: v for k, v in row.items() if k not in ("ts", "score_basis")}):
                row = saved
            rows[key] = row
    result = [row for _, row in sorted(rows.items(), key=lambda item: (item[0][0], item[0][1] or ""))]
    path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


def merge_metrics_daily(now=None):
    """Keep the newest whole daily record, with legacy rows retained as undated."""
    from datetime import date, timedelta
    path = DATA_DIR / "metrics_daily.json"
    remote = _remote("data/metrics_daily.json")
    local = _load(path)
    if remote is None and local is None:
        return
    now = now or datetime.now(timezone.utc)
    today = (now + timedelta(hours=8)).date()
    cutoff = today - timedelta(days=730)
    days, stamps = {}, {}
    for source in (remote, local):
        records = source.get("days") if isinstance(source, dict) else None
        for key, row in (records if isinstance(records, dict) else {}).items():
            if not isinstance(row, dict):
                continue
            try:
                day = date.fromisoformat(key)
                if day.isoformat() != key or not cutoff <= day <= today:
                    continue
                stamp = None
                if "recorded_at" in row:
                    stamp = datetime.fromisoformat(row["recorded_at"].replace("Z", "+00:00"))
                    if (stamp.tzinfo is None or stamp > now or
                            stamp.astimezone(timezone(timedelta(hours=8))).date() != day):
                        continue
            except (TypeError, ValueError, AttributeError):
                continue
            previous = stamps.get(key)
            if previous is not None and (stamp is None or stamp < previous):
                continue
            days[key], stamps[key] = row, stamp
    path.write_text(json.dumps({"days": dict(sorted(days.items()))}, ensure_ascii=False), encoding="utf-8")


def merge_news_samples(now=None):
    """Optional only before first rollout. Read errors never erase an existing archive."""
    from news_sampling import stamp
    from datetime import timedelta
    rel = 'data/news_samples.json'
    listed = subprocess.check_output(['git', 'ls-tree', '--name-only', 'origin/main', '--', rel],
                                     stderr=subprocess.DEVNULL, text=True).strip()
    path = DATA_DIR / 'news_samples.json'
    sources = []
    if listed:
        sources.append(json.loads(subprocess.check_output(['git', 'show', 'origin/main:' + rel],
                                                          stderr=subprocess.DEVNULL)))
    if path.exists():
        sources.append(json.loads(path.read_text(encoding='utf-8')))
    if not sources:
        return
    now = now or datetime.now(timezone.utc)
    regions = {}
    for source in sources:
        if not isinstance(source, dict) or source.get('version') != 1 or not isinstance(source.get('by_region'), dict):
            raise ValueError('Invalid news sample archive')
        for key, incoming in source['by_region'].items():
            if not isinstance(incoming, dict) or not isinstance(incoming.get('records'), list):
                raise ValueError('Invalid news sample region')
            saved = regions.get(key)
            if saved is None:
                regions[key] = incoming
                continue
            a, b = stamp(saved.get('attempted_at')), stamp(incoming.get('attempted_at'))
            newest = incoming if b and (not a or b >= a) else saved
            records = {}
            for row in saved['records'] + incoming['records']:
                if not isinstance(row, dict) or not isinstance(row.get('sample_id'), str) or stamp(row.get('ts')) is None:
                    raise ValueError('Invalid news sample')
                if stamp(row['ts']) < now - timedelta(days=90):
                    continue
                old = records.get(row['sample_id'])
                # Preserve earliest first-seen version; never replace original publication time.
                if old and (stamp(old.get('first_seen_at')) or now) <= (stamp(row.get('first_seen_at')) or now):
                    continue
                records[row['sample_id']] = row
            regions[key] = {**newest, 'records': sorted(records.values(), key=lambda r: r['ts'], reverse=True)}
    result = {'version': 1, 'method': 'regional-rss-v1', 'by_region': regions}
    path.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')


if __name__ == "__main__":
    merge_pla()
    merge_months("data/food_history.json", DATA_DIR / "food_history.json")
    merge_months("data/strat_history.json", DATA_DIR / "strat_history.json")
    merge_metrics_daily()
    merge_score_history()
    merge_news_samples()
    print("history merge guard applied")
