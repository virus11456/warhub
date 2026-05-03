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

# Pentagon-area pizza shops (matches the list in index.html)
# baseline = typical busyness for this time slot (used to detect anomalies)
# Run scripts/find_places.py to obtain real place_ids once you have a
# Google Maps API key. Until then, these are placeholders and the fetcher
# will fall back to mock data.
PIZZA_SHOPS = [
    {"name": "We The Pizza",          "place_id": "PLACE_ID_HERE", "baseline": 45},
    {"name": "Pizzato Pizza",         "place_id": "PLACE_ID_HERE", "baseline": 40},
    {"name": "Papa Johns Pizza",      "place_id": "PLACE_ID_HERE", "baseline": 38},
    {"name": "Domino's Pizza",        "place_id": "PLACE_ID_HERE", "baseline": 35},
    {"name": "Extreme Pizza",         "place_id": "PLACE_ID_HERE", "baseline": 30},
    {"name": "District Pizza Palace", "place_id": "PLACE_ID_HERE", "baseline": 32},
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
    """抓取披薩店繁忙度。若無 Google API key 或 place_id 為佔位符則使用模擬資料"""
    have_real_ids = all(s["place_id"] != "PLACE_ID_HERE" for s in PIZZA_SHOPS)

    if not google_api_key or not have_real_ids:
        if not google_api_key:
            log.warning("GOOGLE_MAPS_API_KEY not set - using mock data")
        else:
            log.warning("Place IDs are still placeholders - using mock data. "
                        "Run scripts/find_places.py to fill them in.")
        return _mock_pizza()

    try:
        import populartimes  # type: ignore
    except ImportError:
        log.warning("populartimes package not installed - using mock data")
        return _mock_pizza()

    results = []
    for shop in PIZZA_SHOPS:
        entry = _shop_template(shop, busyness=0, is_open=False)
        try:
            data = populartimes.get_id(google_api_key, shop["place_id"])
            live = data.get("current_popularity")
            if live is None:
                live = _estimate_busyness(data) or 0

            entry["busyness"] = int(live)
            entry["is_open"]  = bool(_is_open_now(data))
            entry["status"]   = "open" if entry["is_open"] else "closed"
        except Exception as e:
            log.warning(f"Failed for {shop['name']}: {e}")
        results.append(entry)
    return results


def _shop_template(shop: dict, *, busyness: int, is_open: bool) -> dict:
    return {
        "name":     shop["name"],
        "place_id": shop["place_id"],
        "baseline": shop.get("baseline", 40),
        "busyness": busyness,
        "is_open":  is_open,
        "status":   "open" if is_open else "closed",
    }


def _estimate_busyness(data: dict) -> Optional[int]:
    now = datetime.now()
    popular = data.get("populartimes", [])
    if len(popular) > now.weekday():
        day_data = popular[now.weekday()].get("data", [])
        if len(day_data) > now.hour:
            return day_data[now.hour]
    return None


def _is_open_now(data: dict) -> bool:
    """從 populartimes 回傳的資料推斷店家現在是否營業"""
    times = data.get("time_spent")  # populartimes returns this when open
    if data.get("current_popularity") is not None:
        return True
    # Fallback: check if today's typical popularity at this hour is non-zero
    return (_estimate_busyness(data) or 0) > 0


def _mock_pizza() -> list[dict]:
    """無 API key 時的模擬資料 - 還原 'closed' 為主、夾雜異常的演示狀態"""
    import random
    # 模擬：白天大部分開、晚上關；隨機把幾家拉高觸發異常
    is_business_hours = 11 <= datetime.now().hour <= 21
    results = []
    for i, shop in enumerate(PIZZA_SHOPS):
        if is_business_hours:
            base = shop.get("baseline", 35)
            busyness = max(0, min(100, base + random.randint(-10, 25)))
            is_open = True
        else:
            busyness = 0
            is_open = False
        results.append(_shop_template(shop, busyness=busyness, is_open=is_open))
    return results


def calculate_score(pizza: list[dict], polymarket: list[dict]) -> dict:
    """綜合威脅指數：Pizza 40% + Polymarket 60%"""
    open_shops = [s for s in pizza if s.get("is_open")]
    if open_shops:
        pizza_score = sum(s["busyness"] for s in open_shops) / len(open_shops)
    else:
        pizza_score = 0.0
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
