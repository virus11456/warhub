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
- AVI 軍機追蹤: api.adsb.lol/v2/mil
  ─ 全球 ADS-B 軍用飛機即時位置（無金鑰、無速率限制）
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
# Public ADS-B "/mil" feeds — try in order, both return identical schema
ADSB_MIL_FEEDS  = [
    "https://opendata.adsb.fi/api/v2/mil",
    "https://api.adsb.lol/v2/mil",
]
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
# AVI - Military aviation tracking via adsb.lol
# ─────────────────────────────────────────────────────────────
# ICAO type code → role mapping
_TANKERS = {"K35R", "K35E", "K35", "K135", "KC135", "KC46", "K46",
            "KC10", "KDC1", "VC10", "A332", "A330MRTT"}
_AWACS   = {"E3", "E3CF", "E3TF", "E767", "E7", "E737", "A50",
            "E2", "E2C", "E2D", "E8", "E8C", "E8B"}
_UAV     = {"GLOB", "RQ4", "GHWK", "MQ9", "Q9", "MQ4", "HALE",
            "HERN", "RPAS", "MQ1", "SHE2"}
_TRANSPORT = {"C5", "C5M", "C17", "C130", "C30J", "C160", "A400", "C295", "B350"}
_FIGHTER = {"F15", "F16", "F18", "F22", "F35", "FA18", "EUFI", "TYPH", "RFAL"}
_C4ISR   = {"RC35", "RC135", "E6", "E6B", "P3", "P8", "P8I", "U2"}

# ICAO type → human-readable label (subset)
_TYPE_NAMES = {
    "K35R": "KC-135R", "K35E": "KC-135E", "K135": "KC-135",
    "K46": "KC-46A",   "KC46": "KC-46A",  "KC10": "KC-10",
    "C5":  "C-5",      "C5M":  "C-5M Super Galaxy",
    "C17": "C-17 Globemaster III",
    "C130": "C-130",   "C30J": "C-130J",
    "A400": "A400M",
    "E3":  "E-3 Sentry", "E3CF": "E-3 Sentry", "E3TF": "E-3 Sentry",
    "E7":  "E-7A Wedgetail", "E737": "E-7A Wedgetail",
    "E767": "E-767", "E2": "E-2 Hawkeye", "E2C": "E-2C", "E2D": "E-2D",
    "E8C": "E-8C JSTARS", "E8B": "E-8B",
    "GLOB": "RQ-4 Global Hawk", "RQ4": "RQ-4 Global Hawk",
    "MQ9": "MQ-9 Reaper",  "Q9": "MQ-9 Reaper",
    "MQ4": "MQ-4 Triton",  "MQ1": "MQ-1 Predator",
    "F22": "F-22 Raptor",  "F35": "F-35 Lightning II",
    "F15": "F-15", "F16": "F-16", "F18": "F/A-18", "FA18": "F/A-18",
    "P8":  "P-8 Poseidon", "P8I": "P-8I Neptune",
    "RC135": "RC-135 Rivet Joint", "RC35": "RC-135",
    "E6":  "E-6B Mercury", "E6B": "E-6B Mercury",
    "U2":  "U-2 Dragon Lady",
}


def _classify_aircraft(t: str) -> str:
    """Map ICAO type code to a role category"""
    t = (t or "").upper()
    if t in _TANKERS:   return "tanker"
    if t in _AWACS:     return "awacs"
    if t in _UAV:       return "uav"
    if t in _TRANSPORT: return "transport"
    if t in _FIGHTER:   return "fighter"
    if t in _C4ISR:     return "c4isr"
    return "other"


def _region_from_latlon(lat, lon) -> str:
    """Rough geographic region for display"""
    if lat is None or lon is None:
        return "未知"
    if 24 <= lat <= 50 and -125 <= lon <= -66:
        return "北美"
    if 35 <= lat <= 72 and -10 <= lon <= 60:
        return "歐洲"
    if 30 <= lat <= 60 and 60 <= lon <= 140:
        return "歐亞 / 中東"
    if 12 <= lat <= 35 and 25 <= lon <= 60:
        return "中東"
    if 5 <= lat <= 50 and 100 <= lon <= 145:
        return "西太平洋"
    if -45 <= lat <= 5 and 90 <= lon <= 180:
        return "南太平洋"
    return f"{lat:.1f},{lon:.1f}"


async def fetch_aviation(session: aiohttp.ClientSession) -> dict:
    """
    從公開 ADS-B 鏡像抓取目前全球可見的軍用飛機。
    依序試 ADSB_MIL_FEEDS，遇到第一個成功就用。
    回傳 {summary: {tankers, awacs, uav, ...}, aircraft: [...], source}
    """
    payload = None
    used_source = None
    for url in ADSB_MIL_FEEDS:
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=20),
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            ) as resp:
                if resp.status != 200:
                    log.warning(f"AVI feed {url} returned {resp.status}, trying next")
                    continue
                payload = await resp.json()
                used_source = url
                break
        except Exception as e:
            log.warning(f"AVI feed {url} failed: {e}, trying next")
            continue

    if payload is None:
        log.error("All AVI feeds unavailable")
        return {"summary": {"tankers": 0, "awacs": 0, "uav": 0,
                            "transport": 0, "fighter": 0, "c4isr": 0,
                            "total": 0, "anomaly_pct": 0},
                "aircraft": [],
                "source": None,
                "error": "all_feeds_unavailable"}

    raw = payload.get("ac", []) or []
    counts = {"tanker": 0, "awacs": 0, "uav": 0,
              "transport": 0, "fighter": 0, "c4isr": 0, "other": 0}
    aircraft = []

    for a in raw:
        t       = (a.get("t") or "").upper()
        flight  = (a.get("flight") or "").strip()
        hexid   = (a.get("hex") or "").upper()
        alt     = a.get("alt_baro")
        lat, lon = a.get("lat"), a.get("lon")
        role    = _classify_aircraft(t)
        counts[role] = counts.get(role, 0) + 1

        # 只把「值得追蹤的類型」放進 aircraft list
        if role not in ("other",):
            try:
                alt_ft = int(alt) if alt and alt != "ground" else 0
            except (ValueError, TypeError):
                alt_ft = 0
            aircraft.append({
                "icao24":   hexid,
                "callsign": flight or "—",
                "type":     _TYPE_NAMES.get(t, t or "—"),
                "type_code": t,
                "role":     role,
                "alt_ft":   alt_ft,
                "lat":      lat,
                "lon":      lon,
                "region":   _region_from_latlon(lat, lon),
            })

    # 排序：先 tanker、awacs、uav，然後依 callsign
    role_order = {"awacs": 0, "uav": 1, "tanker": 2, "c4isr": 3,
                  "fighter": 4, "transport": 5, "other": 9}
    aircraft.sort(key=lambda a: (role_order.get(a["role"], 99), a["callsign"]))

    summary = {
        "tankers":   counts["tanker"],
        "awacs":     counts["awacs"],
        "uav":       counts["uav"],
        "transport": counts["transport"],
        "fighter":   counts["fighter"],
        "c4isr":     counts["c4isr"],
        "total":     len(raw),
    }
    log.info(f"AVI: {summary['total']} mil aircraft global ({used_source}); "
             f"tankers={summary['tankers']} awacs={summary['awacs']} "
             f"uav={summary['uav']} transport={summary['transport']}")

    return {"summary": summary, "aircraft": aircraft[:30], "source": used_source}


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
        pizzint_task  = asyncio.create_task(fetch_pizzint(session))
        poly_task     = asyncio.create_task(fetch_polymarket(session))
        aviation_task = asyncio.create_task(fetch_aviation(session))
        pizzint_data, polymarket, aviation = await asyncio.gather(
            pizzint_task, poly_task, aviation_task
        )

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
        "aviation":      aviation,
        "sources": {
            "pizza":      "https://www.pizzint.watch/",
            "polymarket": "https://gamma-api.polymarket.com/",
            "aviation":   "https://api.adsb.lol/v2/mil",
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
