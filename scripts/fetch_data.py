"""
WarHub - 靜態網站資料抓取器
由 GitHub Actions 每 15 分鐘執行，輸出 data/data.json 供前端讀取
"""

import asyncio
import aiohttp
import json
import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger("warhub")

POLYMARKET_API = "https://gamma-api.polymarket.com"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_FILE = DATA_DIR / "data.json"

PIZZA_SHOPS = [
    {"name": "Domino's Pizza - Arlington",   "place_id": "ChIJ2Q6XXXXX"},
    {"name": "Papa John's - Pentagon City",  "place_id": "ChIJ3R7YYYYY"},
    {"name": "Pizza Hut - Crystal City",     "place_id": "ChIJ4S8ZZZZZ"},
    {"name": "Domino's - Alexandria",        "place_id": "ChIJ5T9AAAAA"},
]

WAR_KEYWORDS = [
    "war", "strike", "attack", "invasion", "conflict",
    "ceasefire", "nuclear", "missile", "troops", "military",
    "Iran", "Taiwan", "Ukraine", "Korea", "China",
    "Israel", "NATO",
]


async def fetch_polymarket(session: aiohttp.ClientSession) -> list[dict]:
    """從 Polymarket Gamma API 抓取戰爭/衝突相關市場"""
    url = f"{POLYMARKET_API}/markets"
    params = {"limit": 200, "active": "true", "closed": "false", "tag_slug": "geopolitics"}

    war_markets = []
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                log.warning(f"Polymarket API returned {resp.status}")
                return []
            data = await resp.json()

        markets = data if isinstance(data, list) else data.get("data", [])
        log.info(f"Fetched {len(markets)} Polymarket markets")

        for m in markets:
            text = ((m.get("question") or "") + " " + (m.get("description") or "")).lower()
            if not any(kw.lower() in text for kw in WAR_KEYWORDS):
                continue

            yes_price = no_price = None
            for o in m.get("outcomes", []) or []:
                name = (o.get("name") or "").lower()
                price = float(o.get("price", 0) or 0)
                if name == "yes":
                    yes_price = price
                elif name == "no":
                    no_price = price

            war_markets.append({
                "id":         m.get("conditionId") or m.get("id"),
                "question":   m.get("question"),
                "yes_price":  yes_price,
                "no_price":   no_price,
                "volume":     float(m.get("volume", 0) or 0),
                "category":   m.get("category") or "geopolitics",
                "slug":       m.get("slug"),
                "end_date":   m.get("endDate"),
            })

        log.info(f"Filtered {len(war_markets)} war-related markets")
    except Exception as e:
        log.error(f"Polymarket error: {e}")

    return war_markets


def fetch_pizza(google_api_key: str) -> list[dict]:
    """抓取披薩店繁忙度。若無 Google API key 則使用模擬資料"""
    if not google_api_key:
        return _mock_pizza()

    try:
        import populartimes  # type: ignore
    except ImportError:
        log.warning("populartimes package not installed - using mock data")
        return _mock_pizza()

    results = []
    for shop in PIZZA_SHOPS:
        try:
            data = populartimes.get_id(google_api_key, shop["place_id"])
            live = data.get("current_popularity")
            if live is None:
                live = _estimate_busyness(data) or 0
            results.append({
                "shop_name":    data.get("name", shop["name"]),
                "place_id":     shop["place_id"],
                "busyness_pct": live,
                "is_anomaly":   int(live > 70),
            })
        except Exception as e:
            log.warning(f"Failed for {shop['name']}: {e}")
    return results


def _estimate_busyness(data: dict) -> Optional[int]:
    now = datetime.now()
    popular = data.get("populartimes", [])
    if len(popular) > now.weekday():
        day_data = popular[now.weekday()].get("data", [])
        if len(day_data) > now.hour:
            return day_data[now.hour]
    return None


def _mock_pizza() -> list[dict]:
    import random
    base = [45, 38, 72, 55]
    return [
        {
            "shop_name":    s["name"],
            "place_id":     s["place_id"],
            "busyness_pct": base[i] + random.randint(-5, 5),
            "is_anomaly":   int(base[i] > 65),
        }
        for i, s in enumerate(PIZZA_SHOPS)
    ]


def calculate_score(pizza: list[dict], polymarket: list[dict]) -> dict:
    """綜合威脅指數：Pizza 40% + Polymarket 60%"""
    pizza_score = (
        sum(s["busyness_pct"] for s in pizza) / len(pizza)
        if pizza else 0.0
    )
    pizza_score = min(100, pizza_score)

    total_volume = sum(m["volume"] for m in polymarket if m["yes_price"] is not None)
    if total_volume > 0:
        weighted = sum(m["yes_price"] * m["volume"] for m in polymarket if m["yes_price"] is not None)
        poly_score = (weighted / total_volume) * 100
    else:
        poly_score = 30.0

    combined = pizza_score * 0.40 + poly_score * 0.60

    if combined >= 70:
        level = "CRITICAL"
    elif combined >= 50:
        level = "HIGH"
    elif combined >= 30:
        level = "ELEVATED"
    else:
        level = "NORMAL"

    return {
        "pizza_score":      round(pizza_score, 2),
        "polymarket_score": round(poly_score, 2),
        "combined_score":   round(combined, 2),
        "alert_level":      level,
    }


async def main():
    google_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")

    async with aiohttp.ClientSession() as session:
        polymarket = await fetch_polymarket(session)

    pizza = fetch_pizza(google_key)
    score = calculate_score(pizza, polymarket)

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "score":      score,
        "pizza":      pizza,
        "polymarket": polymarket[:20],
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"Wrote {DATA_FILE} - combined: {score['combined_score']} [{score['alert_level']}]")


if __name__ == "__main__":
    asyncio.run(main())
