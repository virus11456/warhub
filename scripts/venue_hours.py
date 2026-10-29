"""Google Maps opening hours for the Pentagon-area pizza shops and bars (SerpApi, run by hand).

Google no longer shows Popular Times to signed-out clients (SerpApi included), but opening
hours are still public. One run costs one SerpApi search per venue (10 in total); the
scheduled update never calls SerpApi and only copies the stored file into data.json.
The page decides "open now" from these hours in Washington time.

data/venue_hours.json:
  fetched_at: when this script ran
  venues: display name → kind, Google title/address/place_id, hours {'0'(Sunday)…'6': [[start, end] minutes]},
          raw (Google's text per weekday); end > 1440 means the shift runs past midnight
  errors: display name → why the venue was not stored (no match, wrong branch, request failed)
"""
import argparse
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOURS_FILE = Path(__file__).resolve().parent.parent / "data" / "venue_hours.json"
SERPAPI = "https://serpapi.com/search.json"
DAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
_TIME = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?", re.I)


def venues():
    from fetch_data import PENTAGON_BARS
    from pizza_traffic import PIZZA_VENUES
    out = [{"name": n, "kind": "pizza", "query": f"{v['name']}, {v['address']}", "address": v["address"]}
           for n, v in PIZZA_VENUES.items()]
    out += [{"name": b["name"], "kind": "bar", "query": f"{b['name']}, {b['address']}", "address": b["address"]}
            for b in PENTAGON_BARS]
    return out


def parse_range(text):
    """'11 AM–2 PM, 5–10 PM' → [[660, 840], [1020, 1320]]; 'Closed' → []; None when unreadable."""
    t = (text or "").replace(" ", " ").replace(" ", " ").strip()
    if not t:
        return None
    if re.fullmatch(r"closed", t, re.I):
        return []
    if re.search(r"open 24 hours", t, re.I):
        return [[0, 1440]]
    ranges = []
    for part in t.split(","):
        ends = re.split(r"\s*[–—-]\s*", part.strip())
        if len(ends) != 2:
            return None
        a, b = _TIME.fullmatch(ends[0].strip()), _TIME.fullmatch(ends[1].strip())
        if not a or not b or not b.group(3):
            return None
        def minutes(m, meridiem):
            h, mm = int(m.group(1)), int(m.group(2) or 0)
            if h > 12 or mm > 59:
                raise ValueError
            return (h % 12 + (12 if meridiem.upper() == "PM" else 0)) * 60 + mm
        try:
            end = minutes(b, b.group(3))
            start = minutes(a, a.group(3) or b.group(3))  # Google drops the first AM/PM when both match
        except ValueError:
            return None
        if end <= start:
            end += 1440  # closes after midnight
        ranges.append([start, end])
    return ranges


def parse_hours(rows):
    """SerpApi hours ([{'monday': '…'}, …] or {'monday': '…'}) → {'0'…'6': ranges}; None if a day is unreadable or missing."""
    days = {}
    for row in ([rows] if isinstance(rows, dict) else rows or []):
        if not isinstance(row, dict):
            continue
        for day, text in row.items():
            if day.lower() in DAYS:
                parsed = parse_range(text)
                if parsed is None:
                    return None
                days[str(DAYS.index(day.lower()))] = parsed
    return days if len(days) == 7 else None


def same_branch(expected_address, returned_address):
    """Same street and a house number within 30 (Google lists We, The Pizza at 2110 for our 2100)."""
    pat = r"\s*(\d+)\s+(?:[NSEW]\s+)?(\w+)"
    m, g = re.match(pat, expected_address or ""), re.match(pat, returned_address or "")
    return bool(m and g) and m.group(2).lower() == g.group(2).lower() and abs(int(m.group(1)) - int(g.group(1))) <= 30


def lookup(key, venue):
    params = {"engine": "google_maps", "type": "search", "q": venue["query"], "hl": "en", "gl": "us", "api_key": key}
    with urllib.request.urlopen(SERPAPI + "?" + urllib.parse.urlencode(params), timeout=90) as resp:
        data = json.loads(resp.read())
    if data.get("error"):
        return {"error": str(data["error"])[:200]}
    candidates = [data["place_results"]] if data.get("place_results") else data.get("local_results") or []
    place = next((p for p in candidates if isinstance(p, dict) and same_branch(venue["address"], p.get("address"))), None)
    if place is None:
        found = candidates[0].get("address") if candidates and isinstance(candidates[0], dict) else None
        return {"error": f"different branch: {found}" if found else "no place found"}
    base = {"kind": venue["kind"], "title": place.get("title"), "address": place.get("address"),
            "place_id": place.get("place_id"), "gps": place.get("gps_coordinates")}
    if re.search(r"permanently closed", str(place.get("open_state") or ""), re.I):
        return {**base, "permanently_closed": True, "hours": {str(d): [] for d in range(7)}, "raw": {}}
    rows = place.get("hours") or place.get("operating_hours")
    hours = parse_hours(rows)
    if hours is None:
        return {"error": "opening hours missing or unreadable"}
    raw = rows if isinstance(rows, dict) else {k: v for row in rows if isinstance(row, dict) for k, v in row.items()}
    return {**base, "hours": hours, "raw": raw}


def load(path=None):
    try:
        data = json.loads(Path(path or HOURS_FILE).read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="list venues and the search cost only")
    ap.add_argument("--only", nargs="*", help="display names to refresh (default: all)")
    args = ap.parse_args()
    targets = [v for v in venues() if not args.only or v["name"] in args.only]
    print(f"{len(targets)} venues, {len(targets)} SerpApi searches")
    if args.dry_run:
        for v in targets:
            print(f"  {v['kind']:5} {v['name']}")
        return
    key = os.environ.get("SERPAPI_API_KEY", "").strip()
    if not key:
        raise SystemExit("SERPAPI_API_KEY is not set")
    store = load()
    store.setdefault("venues", {})
    errors = {n: e for n, e in (store.get("errors") or {}).items() if n not in {v["name"] for v in targets}}
    for v in targets:
        try:
            result = lookup(key, v)
        except Exception as e:  # keep the other venues; never print the request URL (it holds the key)
            result = {"error": f"request failed: {type(e).__name__}"}
        if "error" in result:
            errors[v["name"]] = result["error"]
            print(f"  ✗ {v['name']}: {result['error']}")
        else:
            store["venues"][v["name"]] = result
            print(f"  ✓ {v['name']}")
    store.update({"fetched_at": datetime.now(timezone.utc).isoformat(), "source": "Google Maps via SerpApi",
                  "errors": errors})
    HOURS_FILE.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
