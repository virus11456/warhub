"""
WarHub - 靜態網站資料抓取器
==========================
由 GitHub Actions 每 15 分鐘執行，輸出 data/data.json 供前端讀取。

資料來源：
- Pizza 指數: pizzint.watch 公開 API（/api/dashboard-data）
  ─ Pentagon 周邊披薩店即時繁忙度、24h sparkline、DEFCON 等級
  ─ Credit: https://www.pizzint.watch/
- Polymarket: gamma-api.polymarket.com 公開 API
  ─ 戰爭/衝突相關預測市場
"""

import asyncio
import aiohttp
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger("warhub")

PIZZINT_API     = "https://www.pizzint.watch/api/dashboard-data"
POLYMARKET_API  = "https://gamma-api.polymarket.com/markets"
DATA_DIR        = Path(__file__).resolve().parent.parent / "data"
DATA_FILE       = DATA_DIR / "data.json"
USER_AGENT      = "WarHub/1.0 (+https://github.com/virus11456/warhub)"

# index.html 上要顯示哪幾家店（pizzint.watch 列了 14 家，我們挑 6 家披薩店）
# 名稱必須與 pizzint.watch API 回傳的 name 完全相符（用於比對）
SHOPS_TO_DISPLAY = [
    "We, The Pizza",
    "Pizzato Pizza",
    "Papa Johns Pizza",
    "Domino's Pizza (Pentagon Closest)",
    "Extreme Pizza",
    "District Pizza Palace",
    "Nighthawk Brewery & Pizza",
]

WAR_KEYWORDS = [
    "war", "strike", "attack", "invasion", "conflict",
    "ceasefire", "nuclear", "missile", "troops", "military",
    "Iran", "Taiwan", "Ukraine", "Korea", "China",
    "Israel", "NATO",
]


# ─────────────────────────────────────────────────────────────
# Pizza data — pizzint.watch
# ─────────────────────────────────────────────────────────────
async def fetch_pizzint(session: aiohttp.ClientSession) -> dict:
    """
    從 pizzint.watch 抓取 Pentagon Pizza Index 即時資料。
    回傳完整的 dashboard payload（含每家店狀態、overall_index、DEFCON）。
    """
    try:
        async with session.get(
            PIZZINT_API,
            timeout=aiohttp.ClientTimeout(total=15),
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        ) as resp:
            resp.raise_for_status()
            return await resp.json()
    except Exception as e:
        log.error(f"pizzint.watch fetch failed: {e}")
        return {}


def transform_pizza_shops(pizzint_payload: dict) -> list[dict]:
    """把 pizzint.watch 的 shop list 轉成我們前端要的格式"""
    raw_shops = pizzint_payload.get("data", []) or []
    by_name = {s.get("name"): s for s in raw_shops}

    shops = []
    for display_name in SHOPS_TO_DISPLAY:
        src = by_name.get(display_name)
        if not src:
            log.warning(f"Shop not found in pizzint API: {display_name}")
            shops.append({
                "name":      display_name,
                "busyness":  0,
                "is_open":   False,
                "status":    "closed",
                "baseline":  35,
                "spike":     False,
                "place_id":  None,
                "address":   None,
            })
            continue

        cur_pop = src.get("current_popularity")  # 0-100 or None
        pct_usual = src.get("percentage_of_usual")  # deviation %
        is_open = cur_pop is not None
        busyness = int(cur_pop) if is_open else 0

        # status: closed / quiet / normal / busy / spike
        if not is_open:
            status = "closed"
        elif src.get("is_spike"):
            status = "spike"
        elif busyness >= 70:
            status = "busy"
        elif busyness >= 40:
            status = "normal"
        else:
            status = "quiet"

        shops.append({
            "name":      display_name,
            "busyness":  busyness,
            "is_open":   is_open,
            "status":    status,
            "baseline":  35,
            "spike":     bool(src.get("is_spike")),
            "spike_magnitude": src.get("spike_magnitude"),
            "percentage_of_usual": pct_usual,
            "place_id":  src.get("place_id"),
            "address":   src.get("address"),
            "data_source": src.get("data_source"),
            "recorded_at": src.get("recorded_at"),
        })
    return shops


# ─────────────────────────────────────────────────────────────
# Polymarket data
# ─────────────────────────────────────────────────────────────
def _parse_outcome_prices(market: dict) -> tuple[float | None, float | None]:
    """
    Polymarket Gamma API 回傳的 outcomes / outcomePrices 是 JSON 字串
    (e.g. '["Yes","No"]' 和 '["0.545","0.455"]')，需先解析。
    回傳 (yes_price, no_price)。
    """
    outcomes_raw = market.get("outcomes")
    prices_raw   = market.get("outcomePrices")
    try:
        names  = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw
        prices = json.loads(prices_raw)   if isinstance(prices_raw, str)   else prices_raw
    except (json.JSONDecodeError, TypeError):
        return None, None

    if not names or not prices or len(names) != len(prices):
        return None, None

    yes = no = None
    for name, price in zip(names, prices):
        try:
            p = float(price)
        except (TypeError, ValueError):
            continue
        n = (name or "").lower()
        if n == "yes":
            yes = p
        elif n == "no":
            no = p
    return yes, no


async def fetch_polymarket(session: aiohttp.ClientSession) -> list[dict]:
    """從 Polymarket Gamma API 抓取戰爭/衝突相關市場"""
    params = {"limit": 200, "active": "true", "closed": "false", "tag_slug": "geopolitics"}
    war_markets = []
    try:
        async with session.get(
            POLYMARKET_API, params=params,
            timeout=aiohttp.ClientTimeout(total=15),
            headers={"User-Agent": USER_AGENT},
        ) as resp:
            if resp.status != 200:
                log.warning(f"Polymarket returned {resp.status}")
                return []
            data = await resp.json()

        markets = data if isinstance(data, list) else data.get("data", [])
        log.info(f"Fetched {len(markets)} Polymarket markets")

        for m in markets:
            text = ((m.get("question") or "") + " " + (m.get("description") or "")).lower()
            if not any(kw.lower() in text for kw in WAR_KEYWORDS):
                continue

            yes_price, no_price = _parse_outcome_prices(m)

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


# ─────────────────────────────────────────────────────────────
# Combined score
# ─────────────────────────────────────────────────────────────
def calculate_score(pizza_index: int, polymarket: list[dict]) -> dict:
    """
    綜合威脅指數：Pizza 40% + Polymarket 60%
    pizza_index: pizzint.watch 已算好的 0-100 overall index
    """
    pizza_score = float(pizza_index or 0)

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
    async with aiohttp.ClientSession() as session:
        pizzint_task = asyncio.create_task(fetch_pizzint(session))
        poly_task    = asyncio.create_task(fetch_polymarket(session))
        pizzint_data, polymarket = await asyncio.gather(pizzint_task, poly_task)

    pizza_shops  = transform_pizza_shops(pizzint_data)
    pizza_index  = pizzint_data.get("overall_index", 0)
    defcon_level = pizzint_data.get("defcon_level")
    score        = calculate_score(pizza_index, polymarket)

    output = {
        "updated_at":    datetime.now(timezone.utc).isoformat(),
        "score":         score,
        "pizza":         pizza_shops,
        "pizza_index":   pizza_index,
        "defcon_level":  defcon_level,
        "defcon_details": pizzint_data.get("defcon_details"),
        "polymarket":    polymarket[:20],
        "sources": {
            "pizza":      "https://www.pizzint.watch/",
            "polymarket": "https://gamma-api.polymarket.com/",
        },
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    open_count = sum(1 for s in pizza_shops if s["is_open"])
    log.info(f"Wrote {DATA_FILE.name} - "
             f"pizza_index={pizza_index}, defcon={defcon_level}, "
             f"open_shops={open_count}/{len(pizza_shops)}, "
             f"combined={score['combined_score']} [{score['alert_level']}]")


if __name__ == "__main__":
    asyncio.run(main())
