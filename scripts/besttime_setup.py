"""One-off BestTime forecasts for the pizza shops and bars (spends credits; run by hand only).

Each successful forecast costs 2 BestTime credits (1 when it fails). The scheduled data
update never calls this: it is run from the "BestTime setup" workflow after the owner
approves the spend. Results go to data/besttime_venues.json:
  venues: pizza shops → venue_id, returned name/address/coordinates, forecast_at, usual_week
  bars:   bars → venue_id, forecast_at (live bar readings only need the forecast to exist)
  errors: name → BestTime's message, so a failed venue can be fixed and retried
"""
import argparse
import asyncio
import json
import os
from datetime import datetime, timezone

import aiohttp

from fetch_data import PENTAGON_BARS, USER_AGENT, _besttime_error_message
from pizza_traffic import PIZZA_VENUES, VENUES_FILE, load_venues, usual_week_from_besttime

FORECAST_API = "https://besttime.app/api/v1/forecasts"
CREDITS_PER_FORECAST = 2


async def forecast(session, key, venue):
    params = {"api_key_private": key, "venue_name": venue["name"], "venue_address": venue["address"]}
    async with session.post(FORECAST_API, params=params, timeout=aiohttp.ClientTimeout(total=60),
                            headers={"User-Agent": USER_AGENT}) as resp:
        if resp.status != 200:
            return {"error": f"HTTP {resp.status}: {await _besttime_error_message(resp, key)}"}
        data = await resp.json(content_type=None)
    info = data.get("venue_info") or {} if isinstance(data, dict) else {}
    if not info.get("venue_id"):
        return {"error": "回應缺少 venue_id"}
    days = [{"day_int": (d.get("day_info") or {}).get("day_int"), "day_raw": d.get("day_raw")}
            for d in data.get("analysis") or [] if isinstance(d, dict)]
    return {"venue_id": info["venue_id"], "venue_name": info.get("venue_name"),
            "venue_address": info.get("venue_address"), "lat": info.get("venue_lat"),
            "lng": info.get("venue_lon", info.get("venue_lng")),
            "forecast_at": datetime.now(timezone.utc).isoformat(),
            "usual_week": usual_week_from_besttime(days)}


def targets(scope, store, only_missing):
    pizza = [] if scope == "bars" else [(n, v) for n, v in PIZZA_VENUES.items()]
    bars = [] if scope == "pizza" else [(b["name"], b) for b in PENTAGON_BARS]
    if only_missing:
        pizza = [(n, v) for n, v in pizza if not (store.get("venues") or {}).get(n, {}).get("venue_id")]
        bars = [(n, v) for n, v in bars if not (store.get("bars") or {}).get(n, {}).get("venue_id")]
    return pizza, bars


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=("all", "pizza", "bars"), default="all")
    ap.add_argument("--all", action="store_true", help="re-forecast venues that already have a venue_id")
    ap.add_argument("--dry-run", action="store_true", help="list venues and the maximum credit cost, call nothing")
    args = ap.parse_args()
    store = load_venues()
    pizza, bars = targets(args.scope, store, not args.all)
    names = [n for n, _ in pizza + bars]
    print(f"{len(names)} venues, up to {len(names) * CREDITS_PER_FORECAST} credits: {', '.join(names) or '(none)'}")
    if args.dry_run or not names:
        return
    key = os.environ.get("BESTTIME_API_KEY", "").strip()
    if not key:
        raise SystemExit("BESTTIME_API_KEY is not set")
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*(forecast(session, key, v) for _, v in pizza + bars))
    store.setdefault("version", 1)
    errors = store.setdefault("errors", {})
    for (name, _), result in zip(pizza + bars, results):
        group = "venues" if (name, _) in pizza else "bars"
        if result.get("error"):
            errors[name] = result["error"]
            print(f"✗ {name}: {result['error']}")
            continue
        errors.pop(name, None)
        if group == "bars":
            result = {k: result[k] for k in ("venue_id", "venue_name", "venue_address", "forecast_at")}
        store.setdefault(group, {})[name] = result
        print(f"✓ {name} → {result.get('venue_name')} | {result.get('venue_address')}")
    store["updated_at"] = datetime.now(timezone.utc).isoformat()
    VENUES_FILE.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n")
    if any(r.get("error") for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
