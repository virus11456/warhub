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
- FIRMS 衛星火點: NASA MODIS 24h 全球 CSV
  ─ 真實衛星偵測到的火點（戰爭打擊、工業火災、森林火災均可見）
- EONET 自然事件: NASA Earth Observatory 即時自然事件清單
"""

import asyncio
import aiohttp
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    ZoneInfo = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger("warhub")

PIZZINT_API     = "https://www.pizzint.watch/api/dashboard-data"
POLYMARKET_API  = "https://gamma-api.polymarket.com/markets"
# Public ADS-B "/mil" feeds — try in order, both return identical schema
ADSB_MIL_FEEDS  = [
    "https://opendata.adsb.fi/api/v2/mil",
    "https://api.adsb.lol/v2/mil",
]
# NASA FIRMS — 24h global active fires (MODIS, no API key needed)
FIRMS_CSV_URL   = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/modis-c6.1/csv/MODIS_C6_1_Global_24h.csv"
# NASA EONET — natural event feed (wildfires, volcanoes, etc.)
EONET_API       = "https://eonet.gsfc.nasa.gov/api/v3/events?status=open&days=7&limit=100"
# GDELT DOC 2.0 — 全球新聞衝突報導強度（免金鑰，限速每 5 秒 1 請求）
GDELT_API       = "https://api.gdeltproject.org/api/v2/doc/doc"
# USGS 地震 API — 核試驗場周邊淺層地震監測（免金鑰）
USGS_API        = "https://earthquake.usgs.gov/fdsnws/event/1/query"
# Wikimedia Pageviews — 戰爭相關條目瀏覽量（公眾焦慮指數，免金鑰）
WIKI_PV_API     = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user"
# FAA NOTAM Search — 衝突區 FIR 領空限制/關閉（非官方端點，免金鑰）
NOTAM_API       = "https://notams.aim.faa.gov/notamSearch/search"
# BestTime.app Live Foot Traffic — Pentagon 周邊酒吧即時繁忙度（需 BESTTIME_API_KEY）
BESTTIME_API    = "https://besttime.app/api/v1/forecasts/live"
# 歷史趨勢檔（供前端畫趨勢箭頭；保留 7 天）
HISTORY_FILE    = Path(__file__).resolve().parent.parent / "data" / "history.json"
DATA_DIR        = Path(__file__).resolve().parent.parent / "data"
DATA_FILE       = DATA_DIR / "data.json"
# 糧食進口月度歷史（近 5 年，供前端畫 1/3/5 年趨勢；逐步累積）
FOOD_HISTORY_FILE = DATA_DIR / "food_history.json"
# 共軍每日擾台架次歷史（過去 30 天，從國防部戰報新聞擷取；逐日累積）
PLA_HISTORY_FILE = DATA_DIR / "pla_adiz.json"
# 全指標每日快照長期封存（每日一筆、保留 ~2 年，供未來畫各指標長期趨勢）
METRICS_DAILY_FILE = DATA_DIR / "metrics_daily.json"
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
    "war", "strike", "airstrike", "attack", "invasion", "invade",
    "conflict", "ceasefire", "nuclear", "missile", "troops", "military",
    "annex", "blockade", "coup",
    "Iran", "Taiwan", "Ukraine", "Korea", "China",
    "Israel", "NATO",
]

# 用字界比對（允許複數型），避免 "war" 誤中 award / warming、"strike" 誤中 striker
_WAR_KW_RE = re.compile(
    r"\b(" + "|".join(re.escape(k.lower()) for k in WAR_KEYWORDS) + r")s?\b"
)

# 明顯與軍事衝突無關的主題（運動、娛樂、加密幣），先排除
# 例：'Will Iran win the 2026 FIFA World Cup?' 含 "Iran" 但不是戰爭市場
# 注意：不能排除 "GTA"——Polymarket 慣用「before GTA VI」當時間基準，
# 例如 'Russia-Ukraine Ceasefire before GTA VI?' 是正經的戰爭市場
EXCLUDE_KEYWORDS = [
    "world cup", "fifa", "olympic", "super bowl", "nba", "nfl", "mlb",
    "premier league", "champions league", "grammy", "oscar", "album",
    "box office", "bitcoin", "ethereum", "eurovision", "tiktok",
    "counter-strike", "esports", "valorant", "dota",
]

# ─────────────────────────────────────────────────────────────
# 地區風險引擎設定
# 每個地區的風險分數 = Polymarket 盤口 + GDELT 新聞強度
#                     + FIRMS 衝突區火點 + 該區軍機活動 加權
# ─────────────────────────────────────────────────────────────
REGIONS = {
    "ukraine": {
        "name": "俄烏戰爭", "flag": "🇺🇦",
        "poly_kw": ["ukraine", "russia", "putin", "zelensky", "kyiv", "moscow", "crimea"],
        "gdelt_q": "(ukraine OR russia) (war OR strike OR attack OR offensive)",
        "firms": ["ukraine", "russia"],
        "avi_regions": ["歐洲"],
    },
    "mideast": {
        "name": "美伊 / 中東", "flag": "🇮🇷",
        "poly_kw": ["iran", "israel", "hormuz", "khamenei", "hezbollah", "gaza",
                    "idf", "tehran", "strait"],
        "gdelt_q": "(iran OR israel) (war OR strike OR attack OR nuclear)",
        "firms": ["iran", "israel", "lebanon", "syria", "iraq", "yemen", "gaza"],
        "avi_regions": ["中東", "歐亞 / 中東"],
    },
    "taiwan": {
        "name": "台海", "flag": "🇹🇼",
        "poly_kw": ["taiwan", "invade taiwan", "blockade taiwan", "xi jinping"],
        "gdelt_q": "(taiwan china) (invasion OR military OR blockade OR war)",
        "firms": ["taiwan"],
        "avi_regions": ["西太平洋"],
    },
    "korea": {
        "name": "朝鮮半島", "flag": "🇰🇵",
        "poly_kw": ["north korea", "kim jong", "dprk", "pyongyang"],
        "gdelt_q": '"north korea" (missile OR nuclear OR war OR attack)',
        "firms": ["korea"],
        "avi_regions": ["西太平洋"],
    },
    "southsea": {
        "name": "南海爭議", "flag": "🌊",
        "poly_kw": ["south china sea", "philippines", "scarborough", "spratly"],
        "gdelt_q": '"south china sea" (conflict OR military OR clash OR standoff)',
        "firms": [],
        "avi_regions": ["西太平洋"],
    },
}

# 和平方向的盤（停火/協議）— 機率高代表風險下降，計分時反向
PEACE_MARKERS = ["ceasefire", "peace", "truce", "deal", "agreement", "normalization"]

# 公眾焦慮指數：監控的維基百科條目（瀏覽量激增 = 大眾感知風險上升）
WIKI_ANXIETY_PAGES = [
    "World_War_III",
    "Nuclear_warfare",
    "Doomsday_Clock",
    "Fallout_shelter",
    "Emergency_Alert_System",
]

# 各地區監控的 FIR（飛航情報區）— NOTAM 領空限制/關閉監測
REGION_FIRS = {
    "ukraine":  ["UKBV"],           # 基輔
    "mideast":  ["OIIX", "LLLL"],   # 德黑蘭、特拉維夫
    "taiwan":   ["RCAA"],           # 台北
    "korea":    ["ZKKP"],           # 平壤
    "southsea": ["RPHI"],           # 馬尼拉
}

# NOTAM 內容的警戒關鍵字
NOTAM_DANGER_RE = re.compile(
    r"\b(CLSD|CLOSED|PROHIBITED|DANGER|RESTRICTED|MILITARY EXER|MISSILE|GPS JAMMING|CONFLICT ZONE)\b",
    re.IGNORECASE,
)
NOTAM_CLOSURE_RE = re.compile(r"AIRSPACE\s+(IS\s+)?(CLSD|CLOSED)", re.IGNORECASE)

# Pentagon 周邊酒吧（反向指標：下班後異常冷清 = 幕僚留守加班）
# BestTime Live API 只在酒吧營業且 Google 有即時資料時回傳 busyness
PENTAGON_BARS = [
    {"name": "Sine Irish Pub",          "address": "1301 S Joyce St, Arlington, VA"},
    {"name": "Freddie's Beach Bar",     "address": "555 23rd St S, Arlington, VA"},
    {"name": "Highline RxR",            "address": "2010 Crystal Dr, Arlington, VA"},
    {"name": "Ireland's Four Courts",   "address": "2051 Wilson Blvd, Arlington, VA"},
]
# 只在美東傍晚下班時段查詢（省 API credit、也是訊號最關鍵的時段）
BAR_QUERY_ET_HOURS = range(16, 24)  # 16:00–23:59 ET

# 核試驗場座標（USGS 地震監測用）
NUCLEAR_TEST_SITES = [
    {"key": "punggye",  "name": "豐溪里（北韓）",     "lat": 41.28,  "lon": 129.09},
    {"key": "novaya",   "name": "新地島（俄羅斯）",   "lat": 73.40,  "lon": 54.80},
    {"key": "lopnur",   "name": "羅布泊（中國）",     "lat": 41.50,  "lon": 88.30},
    {"key": "nevada",   "name": "內華達 NNSS（美國）", "lat": 37.12,  "lon": -116.05},
    {"key": "semnan",   "name": "塞姆南（伊朗疑似）", "lat": 35.20,  "lon": 53.90},
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

        # 24h sparkline：壓縮成純數值序列（null = 該小時無資料/打烊）
        sparkline = [
            (int(p["current_popularity"]) if p.get("current_popularity") is not None else None)
            for p in (src.get("sparkline_24h") or [])
        ][-24:]

        shops.append({
            "name":      display_name,
            "busyness":  busyness,
            "is_open":   is_open,
            "status":    status,
            "baseline":  35,
            "spike":     bool(src.get("is_spike")),
            "spike_magnitude": src.get("spike_magnitude"),
            "percentage_of_usual": pct_usual,
            "sparkline": sparkline,
            "is_closed_now": bool(src.get("is_closed_now")),
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
    # gamma API 單頁上限 100 筆，抓 3 頁並按 24h 交易量排序，
    # 確保大交易量的戰爭市場（俄烏停火等）不會因分頁被漏掉
    war_markets = []
    markets = []
    seen_ids = set()
    try:
        for offset in (0, 100, 200):
            params = {
                "limit": 100, "offset": offset,
                "active": "true", "closed": "false",
                "tag_slug": "geopolitics",
                "order": "volume24hr", "ascending": "false",
            }
            async with session.get(
                POLYMARKET_API, params=params,
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": USER_AGENT},
            ) as resp:
                if resp.status != 200:
                    log.warning(f"Polymarket returned {resp.status} (offset={offset})")
                    break
                data = await resp.json()

            page = data if isinstance(data, list) else data.get("data", [])
            if not page:
                break
            for m in page:
                mid = m.get("conditionId") or m.get("id")
                if mid not in seen_ids:
                    seen_ids.add(mid)
                    markets.append(m)
            if len(page) < 100:
                break
        log.info(f"Fetched {len(markets)} Polymarket markets")

        for m in markets:
            text = ((m.get("question") or "") + " " + (m.get("description") or "")).lower()
            if any(ex in text for ex in EXCLUDE_KEYWORDS):
                continue
            if not _WAR_KW_RE.search(text):
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
# FIRMS - NASA satellite fire detections (24h global, no key)
# ─────────────────────────────────────────────────────────────
# Typical 24h global MODIS fire pixel count. Used as the divisor for
# the "vs baseline" delta. We can refine this once we accumulate history.
FIRMS_TYPICAL_24H = 6500


def _firms_region(lat: float, lon: float) -> str:
    if 24 <= lat <= 50 and -125 <= lon <= -66:  return "north_america"
    if 35 <= lat <= 72 and -10 <= lon <= 60:    return "europe_russia"
    if 30 <= lat <= 45 and 30 <= lon <= 60:     return "middle_east"
    if 5 <= lat <= 50 and 60 <= lon <= 145:     return "asia"
    if -10 <= lat <= 35 and -20 <= lon <= 55:   return "africa"
    if -55 <= lat <= 12 and -82 <= lon <= -34:  return "south_america"
    if -45 <= lat <= 5 and 110 <= lon <= 180:   return "oceania"
    return "other"


# Conflict regions of interest, for hotspot tagging
_CONFLICT_BBOX = {
    "ukraine":  (44, 53, 22, 41),    # lat_min, lat_max, lon_min, lon_max
    # 只框「與烏克蘭戰爭相關的俄羅斯西部」（含烏軍無人機常打的伏爾加加勒/薩馬拉/
    # 韃靼斯坦煉油廠），排除西伯利亞——否則夏季西伯利亞野火(FRP 上千 MW)會被誤標為衝突火點
    "russia":   (46, 56, 30, 52),
    "israel":   (29, 34, 33, 36),
    "lebanon":  (33, 35, 35, 37),
    "syria":    (32, 38, 35, 42),
    "iran":     (25, 40, 44, 64),
    "iraq":     (29, 38, 38, 49),
    "yemen":    (12, 19, 42, 54),
    "gaza":     (31.2, 31.7, 34, 35),
    "taiwan":   (21, 26, 119, 123),
    "korea":    (33, 43, 124, 131),
}


def _firms_conflict_label(lat: float, lon: float) -> str | None:
    for name, (lat0, lat1, lon0, lon1) in _CONFLICT_BBOX.items():
        if lat0 <= lat <= lat1 and lon0 <= lon <= lon1:
            return name
    return None


async def fetch_firms(session: aiohttp.ClientSession) -> dict:
    """
    從 NASA 公開 CSV 下載 24h MODIS 火點，回傳統計 + 衝突區熱點。
    """
    try:
        async with session.get(
            FIRMS_CSV_URL,
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"User-Agent": USER_AGENT},
        ) as resp:
            resp.raise_for_status()
            text = await resp.text()
    except Exception as e:
        log.error(f"FIRMS CSV fetch failed: {e}")
        return {"total_24h": 0, "delta_pct": "0%", "by_region": {},
                "conflict_hotspots": [], "high_conf_count": 0,
                "source": FIRMS_CSV_URL, "error": str(e)}

    import csv, io
    rows = list(csv.DictReader(io.StringIO(text)))
    total = len(rows)

    by_region: dict[str, int] = {}
    conflict_hits: dict[str, list[dict]] = {}
    high_conf = 0

    for r in rows:
        try:
            lat = float(r["latitude"])
            lon = float(r["longitude"])
            frp = float(r.get("frp") or 0)
            conf = int(r.get("confidence") or 0)
        except (ValueError, TypeError, KeyError):
            continue

        if conf >= 80:
            high_conf += 1

        reg = _firms_region(lat, lon)
        by_region[reg] = by_region.get(reg, 0) + 1

        cl = _firms_conflict_label(lat, lon)
        if cl is not None:
            conflict_hits.setdefault(cl, []).append({
                "lat": round(lat, 3), "lon": round(lon, 3),
                "frp": round(frp, 1), "conf": conf,
                "daynight": r.get("daynight", ""),
                "acq_date": r.get("acq_date", ""),
                "acq_time": r.get("acq_time", ""),
            })

    # Top hotspots: per conflict region, keep top-3 by FRP
    top_hotspots = []
    for region_name, hits in conflict_hits.items():
        hits.sort(key=lambda h: h["frp"], reverse=True)
        for h in hits[:3]:
            top_hotspots.append({**h, "region": region_name})
    top_hotspots.sort(key=lambda h: h["frp"], reverse=True)

    delta_ratio = (total - FIRMS_TYPICAL_24H) / FIRMS_TYPICAL_24H if FIRMS_TYPICAL_24H else 0
    delta_pct   = f"{'+' if delta_ratio >= 0 else ''}{int(delta_ratio*100)}%"

    log.info(f"FIRMS: {total} fire pixels (24h), high-conf={high_conf}, "
             f"vs baseline {delta_pct}, conflict hotspots={len(top_hotspots)}")

    return {
        "total_24h":         total,
        "high_conf_count":   high_conf,
        "delta_pct":         delta_pct,
        "delta_ratio":       round(delta_ratio, 4),
        "by_region":         by_region,
        "conflict_hotspots": top_hotspots[:15],
        "baseline_24h":      FIRMS_TYPICAL_24H,
        "source":            FIRMS_CSV_URL,
    }


async def fetch_eonet(session: aiohttp.ClientSession) -> list[dict]:
    """
    NASA EONET — 經人工策畫的全球自然事件（火災、火山、風暴等）。
    用作網站「即時事件 feed」。
    """
    try:
        async with session.get(
            EONET_API,
            timeout=aiohttp.ClientTimeout(total=15),
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        ) as resp:
            resp.raise_for_status()
            # EONET sometimes negotiates to RSS — force JSON parse
            text = await resp.text()
            data = json.loads(text)
    except Exception as e:
        log.warning(f"EONET fetch failed: {e}")
        return []

    out = []
    for ev in data.get("events", []) or []:
        cat = (ev.get("categories") or [{}])[0]
        geom = (ev.get("geometries") or [{}])[0]
        coords = geom.get("coordinates") or [None, None]
        out.append({
            "id":       ev.get("id"),
            "title":    ev.get("title"),
            "category": cat.get("title"),
            "date":     geom.get("date"),
            "lat":      coords[1] if len(coords) >= 2 else None,
            "lon":      coords[0] if len(coords) >= 2 else None,
            "link":     ev.get("link"),
        })
    log.info(f"EONET: {len(out)} active events")
    return out


# ─────────────────────────────────────────────────────────────
# GDELT — 全球新聞衝突報導強度（早期預警的領先指標）
# ─────────────────────────────────────────────────────────────
async def fetch_gdelt(session: aiohttp.ClientSession) -> dict:
    """
    對每個地區查詢 GDELT 48h 新聞量強度（佔全球報導百分比）。
    API 限速每 5 秒 1 請求（共享 IP 上更嚴）→ 逐區串行 + 重試遞增退避；
    仍失敗的地區沿用上一輪 data.json 的數值（標記 stale），確保
    地區風險分數不會因單次限流缺新聞因子。
    回傳 {region_key: {latest, avg48h, delta_pct[, stale]}}
    """
    # 上一輪的數值作為 fallback
    prev = {}
    try:
        prev = json.loads(DATA_FILE.read_text(encoding="utf-8")).get("gdelt") or {}
    except Exception:
        pass

    out = {}
    first = True
    for key, cfg in REGIONS.items():
        if not first:
            await asyncio.sleep(6)
        first = False
        params = {
            "query": cfg["gdelt_q"],
            "mode": "timelinevol", "timespan": "48h", "format": "json",
        }
        for attempt, backoff in ((1, 10), (2, 20), (3, 0)):
            try:
                async with session.get(
                    GDELT_API, params=params,
                    timeout=aiohttp.ClientTimeout(total=20),
                    headers={"User-Agent": USER_AGENT},
                ) as resp:
                    text = await resp.text()
                data = json.loads(text)  # 限速時會回純文字錯誤訊息 → 進 except
                points = data["timeline"][0]["data"]
                vals = [p["value"] for p in points if p.get("value") is not None]
                if not vals:
                    break
                # 用最後 6 個點當「目前強度」，對比 48h 平均 → 上升/下降
                latest = sum(vals[-6:]) / len(vals[-6:])
                avg48  = sum(vals) / len(vals)
                delta  = ((latest - avg48) / avg48 * 100) if avg48 else 0
                out[key] = {
                    "latest": round(latest, 3),
                    "avg48h": round(avg48, 3),
                    "delta_pct": round(delta, 1),
                }
                break
            except Exception as e:
                if backoff:
                    await asyncio.sleep(backoff)
                else:
                    log.warning(f"GDELT {key} failed after retries: {e}")

        if key not in out and key in prev:
            out[key] = {**prev[key], "stale": True}

    fresh = sum(1 for v in out.values() if not v.get("stale"))
    log.info(f"GDELT: {fresh}/{len(REGIONS)} fresh, {len(out) - fresh} carried over")
    return out



# ─────────────────────────────────────────────────────────────
# Google News RSS — 即時戰情快訊（早期預警：白宮/中國/戰爭升級相關頭條）
# 免金鑰、持續更新、不受 GDELT 對 GitHub runner IP 的限速影響
# ─────────────────────────────────────────────────────────────
# 需同時命中「升級動作」與「地緣主角」，過濾成與開戰預測相關的頭條
NEWS_QUERY = (
    "(war OR invasion OR airstrike OR missile OR mobilization OR ultimatum OR "
    "escalation OR nuclear OR ceasefire OR sanctions OR offensive OR troops OR strike) "
    '(Ukraine OR Russia OR China OR Taiwan OR Iran OR Israel OR "North Korea" OR '
    '"White House" OR Pentagon)'
)
GNEWS_RSS = "https://news.google.com/rss/search"
# 主題標記關鍵字（依序比對，先命中者為準）
NEWS_TOPICS = [
    ("俄烏",  ["ukrain", "russia", "russian", "kyiv", "kiev", "moscow", "putin", "zelensk", "crimea"]),
    ("中東",  ["iran", "israel", "gaza", "hezbollah", "hamas", "tehran", "netanyahu", "idf", "lebanon", "houthi"]),
    ("台海",  ["taiwan", "taipei", "taiwan strait", "cross-strait"]),
    ("朝鮮",  ["north korea", "pyongyang", "kim jong"]),
    ("南海",  ["south china sea", "scarborough", "philippine"]),
    ("白宮",  ["white house", "pentagon", "trump", "state department", "congress", "biden"]),
    ("中國",  ["china", "beijing", "xi jinping", "pla "]),
]

def _news_topic(title: str) -> str:
    t = (title or "").lower()
    for label, kws in NEWS_TOPICS:
        if any(k in t for k in kws):
            return label
    return "全球"

def _news_iso(pubdate: str) -> str:
    # RFC822 pubDate: "Mon, 13 Jul 2026 08:02:00 GMT" → ISO8601 (UTC)
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(pubdate)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return ""

async def _translate_titles(session, items, tl="zh-TW"):
    """把英文標題批次翻成繁中（Google Translate 免費端點）；保留原文於 title_en。
    失敗或段落數對不上時保留英文，不影響版面。"""
    import urllib.parse
    titles = [it.get("title", "") for it in items]
    if not any(titles):
        return
    try:
        joined = "\n".join(titles)
        url = ("https://translate.googleapis.com/translate_a/single"
               "?client=gtx&sl=auto&tl=" + tl + "&dt=t&q=" + urllib.parse.quote(joined))
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20),
                               headers={"User-Agent": "Mozilla/5.0"}) as resp:
            data = json.loads(await resp.text())
        merged = "".join(seg[0] for seg in data[0] if seg and seg[0])
        zh = merged.split("\n")
        if len(zh) == len(titles):
            for it, t in zip(items, zh):
                t = t.strip()
                if t:
                    it["title_en"] = it["title"]
                    it["title"] = t
            log.info("news titles translated → zh-TW")
        else:
            log.warning(f"translate segments {len(zh)} != {len(titles)}, keep EN")
    except Exception as e:
        log.warning(f"translate failed, keep EN titles: {e}")


async def fetch_gnews(session: aiohttp.ClientSession) -> list[dict]:
    """
    以 Google News RSS 取與戰爭升級相關的即時頭條（免金鑰、持續更新）。
    query 需同時命中「升級動作」與「地緣主角」→ 篩成開戰預測的領先訊號。
    標題以 Google Translate 翻成繁中（原文留在 title_en）。
    失敗時沿用上一輪 data.json 的 news，避免版面空白。
    """
    import urllib.parse, xml.etree.ElementTree as ET
    url = (GNEWS_RSS + "?q=" + urllib.parse.quote(NEWS_QUERY)
           + "&hl=en-US&gl=US&ceid=US:en")
    for attempt, backoff in ((1, 4), (2, 8), (3, 0)):
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=25),
                headers={"User-Agent": "Mozilla/5.0 (compatible; warhub/1.0)"},
            ) as resp:
                raw = await resp.read()
            root = ET.fromstring(raw)
            out, seen = [], set()
            for it in root.findall(".//item"):
                title = (it.findtext("title") or "").strip()
                link  = (it.findtext("link") or "").strip()
                pub   = (it.findtext("pubDate") or "").strip()
                src_el = it.find("source")
                source = (src_el.text or "").strip() if src_el is not None else ""
                if not title or not link:
                    continue
                # 標題常為「Headline - Source」→ 去掉結尾來源
                if source and title.endswith(" - " + source):
                    title = title[: -(len(source) + 3)].strip()
                key = title.lower()[:80]
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "title":  title,
                    "url":    link,
                    "domain": source,
                    "ts":     _news_iso(pub),
                    "topic":  _news_topic(title),
                })
                if len(out) >= 40:      # 先多收一些，稍後依時間挑最新 15 則
                    break
            # 依發布時間新→舊排序，取最新 15 則（ISO 字串可直接字典序排）
            out.sort(key=lambda a: a.get("ts") or "", reverse=True)
            out = out[:15]
            if out:
                await _translate_titles(session, out)   # 標題翻成繁中（_news_topic 已先用英文標好）
                log.info(f"GNews: {len(out)} headlines")
                return out
        except Exception as e:
            if backoff:
                await asyncio.sleep(backoff)
            else:
                log.warning(f"GNews failed after retries: {e}")
    # fallback：沿用上一輪
    try:
        prev = json.loads(DATA_FILE.read_text(encoding="utf-8")).get("news") or []
        if prev:
            log.warning("GNews unavailable, carried over previous headlines")
            for n in prev:
                n["stale"] = True
            return prev
    except Exception:
        pass
    return []


# ─────────────────────────────────────────────────────────────
# 🇹🇼 台海軍事動態新聞（共軍擾台/軍演/軍艦穿越/國防部戰報）
#   直接用中文查詢 + hl=zh-TW，標題已是繁中免翻譯；為「新聞訊號」非精確計數。
# ─────────────────────────────────────────────────────────────
TW_MIL_QUERY = ("共軍 OR 解放軍 OR 擾台 OR 繞台 OR 台海 OR 台灣海峽 OR 防空識別區 "
                "OR 共機 OR 共艦 OR 東部戰區 OR 穿越台灣海峽")
# 只保留「台海／共軍動態」相關；濾掉混進來的他戰區與國內雜訊
TW_KEEP = ("台海", "臺海", "台灣海峽", "臺灣海峽", "穿越台灣海峽", "共軍", "解放軍",
           "中共軍", "共機", "共艦", "擾台", "繞台", "中線", "防空識別", "ADIZ",
           "東部戰區", "圍台", "國機國艦")
TW_DROP = ("伊朗", "以色列", "加薩", "加沙", "烏克蘭", "俄羅斯", "俄烏", "葉門",
           "胡塞", "黎巴嫩", "敘利亞", "哈瑪斯", "毒油", "福利站", "站哨", "外包")

def _tw_relevant(title: str) -> bool:
    t = title or ""
    if any(k in t for k in TW_DROP):
        return False
    return any(k in t for k in TW_KEEP)

def _tw_topic(title: str) -> str:
    t = title or ""
    if any(k in t for k in ("擾台", "架次", "戰機", "軍機", "殲")): return "共軍機艦"
    if any(k in t for k in ("軍演", "演習", "演訓", "operation")):   return "軍演"
    if any(k in t for k in ("穿越", "台灣海峽", "航行", "軍艦", "驅逐艦", "航空母艦")): return "海峽航行"
    if "國防部" in t: return "國防部"
    return "台海"

async def fetch_tw_military_news(session: aiohttp.ClientSession) -> list[dict]:
    import urllib.parse, xml.etree.ElementTree as ET
    url = (GNEWS_RSS + "?q=" + urllib.parse.quote(TW_MIL_QUERY)
           + "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant")
    for attempt, backoff in ((1, 4), (2, 8), (3, 0)):
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=25),
                headers={"User-Agent": "Mozilla/5.0 (compatible; warhub/1.0)"},
            ) as resp:
                raw = await resp.read()
            root = ET.fromstring(raw)
            out, seen = [], set()
            for it in root.findall(".//item"):
                title = (it.findtext("title") or "").strip()
                link  = (it.findtext("link") or "").strip()
                pub   = (it.findtext("pubDate") or "").strip()
                src_el = it.find("source")
                source = (src_el.text or "").strip() if src_el is not None else ""
                if not title or not link:
                    continue
                if source and title.endswith(" - " + source):
                    title = title[: -(len(source) + 3)].strip()
                if not _tw_relevant(title):      # 濾掉他戰區（伊朗等）與國內雜訊
                    continue
                key = title[:40]
                if key in seen:
                    continue
                seen.add(key)
                out.append({"title": title, "url": link, "domain": source,
                            "ts": _news_iso(pub), "topic": _tw_topic(title)})
                if len(out) >= 30:
                    break
            out.sort(key=lambda a: a.get("ts") or "", reverse=True)
            out = out[:12]
            if out:
                log.info(f"TW military news: {len(out)} headlines")
                return out
        except Exception as e:
            if backoff:
                await asyncio.sleep(backoff)
            else:
                log.warning(f"TW news failed after retries: {e}")
    try:
        prev = json.loads(DATA_FILE.read_text(encoding="utf-8")).get("tw_news") or []
        if prev:
            for n in prev: n["stale"] = True
            return prev
    except Exception:
        pass
    return []


# ─────────────────────────────────────────────────────────────
# 📈 共軍每日擾台架次趨勢（過去 30 天）
#   granularity＝每日一筆（國防部每日戰報，非即時）。從台海新聞標題擷取「N架次」，
#   逐日累積到 pla_adiz.json（滾動 30 天）。無官方 API，故以新聞標題為代理來源。
# ─────────────────────────────────────────────────────────────
def _num_before(unit: str, title: str):
    import re
    nums = [int(m) for m in re.findall(r'(\d{1,3})\s*' + unit, title)]
    return max(nums) if nums else None

# 專用查詢：直接抓國防部每日戰報「N架次」標題（比一般台海新聞穩定，一次可涵蓋近幾天）
PLA_SORTIE_QUERY = "共機 架次 OR 擾台 架次 OR 逾越中線 共機 OR 國防部 共機"

# 累計／期間總計字眼：這類標題的「N架次」是一段期間的加總（非單日），
# 若被當單日代入會造成某天異常暴增（誤植／重複計算）。單日紀錄的「新高／破紀錄」
# 仍是有效單日值，不在此列。
PLA_CUMULATIVE_TOKENS = (
    "累計", "以來", "今年", "本週", "本周", "本月", "上半年", "下半年", "全年",
    "年度", "近一週", "近一周", "近一月", "近30", "近三十", "過去30", "過去三十",
    "統計", "總計", "共計", "第7次", "第七次", "圍台軍演",
)

async def fetch_pla_sorties(session: aiohttp.ClientSession) -> dict:
    from datetime import timedelta
    import urllib.parse, xml.etree.ElementTree as ET
    days = {}
    # 1) 先讀歷史檔
    try:
        days = json.loads(PLA_HISTORY_FILE.read_text(encoding="utf-8")).get("days") or {}
    except Exception:
        days = {}
    # 2) 防呆：從上一份 data.json 的 pla 還原，避免歷史檔一時為空造成圖表歸零
    try:
        prev_pla = json.loads(DATA_FILE.read_text(encoding="utf-8")).get("pla") or {}
        for d in (prev_pla.get("days") or []):
            k = d.get("date")
            if k and (k not in days or (d.get("aircraft") or 0) > (days[k].get("aircraft") or 0)):
                days[k] = {"aircraft": d.get("aircraft") or 0, "ships": d.get("ships") or 0}
    except Exception:
        pass

    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(PLA_SORTIE_QUERY)
           + "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant")
    parsed = 0
    for attempt, backoff in ((1, 4), (2, 8), (3, 0)):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=25),
                    headers={"User-Agent": "Mozilla/5.0 (compatible; warhub/1.0)"}) as resp:
                raw = await resp.read()
            root = ET.fromstring(raw)
            for it in root.findall(".//item")[:30]:
                title = (it.findtext("title") or "").strip()
                pub = (it.findtext("pubDate") or "").strip()
                if "架" not in title:
                    continue
                if not any(k in title for k in ("共機", "軍機", "共軍", "解放軍", "中線", "擾台", "殲")):
                    continue
                # 排除「累計／本週／今年以來」等期間總計標題，避免非單日數字被誤植為單日暴增
                if any(t in title for t in PLA_CUMULATIVE_TOKENS):
                    continue
                ac = _num_before("架", title)
                if ac is None or ac <= 0 or ac > 300:
                    continue
                sh = _num_before("艘", title) or 0
                ts = _news_iso(pub)
                try:
                    tp = (datetime.fromisoformat(ts) + timedelta(hours=8)).date().isoformat()
                except Exception:
                    continue
                cur = days.get(tp)
                if (not cur) or ac > (cur.get("aircraft") or 0):
                    days[tp] = {"aircraft": ac, "ships": max(sh, (cur or {}).get("ships", 0))}
                    parsed += 1
            break
        except Exception as e:
            if backoff:
                await asyncio.sleep(backoff)
            else:
                log.warning(f"PLA sorties fetch failed: {e}")
    # 滾動保留 30 天
    cutoff = (datetime.now(timezone.utc) + timedelta(hours=8) - timedelta(days=30)).date().isoformat()
    days = {d: v for d, v in days.items() if d >= cutoff}
    try:
        PLA_HISTORY_FILE.write_text(json.dumps({"days": days}, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log.warning(f"pla history write error: {e}")
    series = [{"date": d, **days[d]} for d in sorted(days)]
    acs = [x["aircraft"] for x in series]
    baseline = sorted(acs)[len(acs) // 2] if acs else 0     # 中位數
    latest = series[-1] if series else None
    log.info(f"PLA ADIZ: {len(series)} days total ({parsed} updated), latest={latest}")
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "days": series, "baseline": baseline, "latest": latest,
        "note": "每日共軍擾台架次（國防部戰報，自新聞標題擷取）· 每日一報、非即時 · 過去 30 天滾動累積",
    }



# ─────────────────────────────────────────────────────────────
# 🌾 中國糧食進口監測（鏡像數據：主要出口國對中國出口合計）
# 中國自報 Comtrade 落後 ~18 個月 → 改用出口國「對中出口」當即時代理值
# 免金鑰 public preview 端點；限速嚴 → 逐一請求＋退避，且每日只更新一次
# ─────────────────────────────────────────────────────────────
COMTRADE_URL = "https://comtradeapi.un.org/public/v1/preview/C/M/HS"
FOOD_EXPORTERS = [("76","巴西"),("842","美國"),("32","阿根廷"),
                  ("36","澳洲"),("124","加拿大"),("804","烏克蘭"),("251","法國")]
FOOD_CMDS = [("1201","大豆"),("1001","小麥"),("1005","玉米")]

def _ym_add(ym: int, d: int) -> int:
    y, m = ym // 100, ym % 100
    i = y * 12 + (m - 1) + d
    return (i // 12) * 100 + (i % 12) + 1

async def _comtrade_month(session, reporter: str, period: int):
    """某出口國該月對中國(156)出口的 {cmd: 淨重kg}；失敗回 None。"""
    params = {"reporterCode": reporter, "flowCode": "X", "partnerCode": "156",
              "cmdCode": "1201,1001,1005", "period": str(period),
              "partner2Code": "0", "motCode": "0"}
    for attempt, bk in ((1, 8), (2, 15), (3, 0)):
        try:
            async with session.get(COMTRADE_URL, params=params,
                    headers={"User-Agent": USER_AGENT},
                    timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status == 429:
                    if bk: await asyncio.sleep(bk); continue
                    return None
                txt = await r.text()
            data = json.loads(txt)
            out = {}
            for row in (data.get("data") or []):
                cmd = str(row.get("cmdCode"))
                out[cmd] = out.get(cmd, 0) + (row.get("netWgt") or 0)
            return out
        except Exception:
            if bk: await asyncio.sleep(bk)
            else: return None
    return None

async def fetch_food_imports(session: aiohttp.ClientSession) -> dict:
    """
    中國三大主糧（大豆/小麥/玉米）進口的鏡像代理值＋年增率（結構性背景指標）。
    每日只更新一次（Comtrade 限速嚴、月資料變動慢）；其餘時間沿用 data.json 的 food。
    """
    from datetime import timedelta
    prev = {}
    try:
        prev = json.loads(DATA_FILE.read_text(encoding="utf-8")).get("food") or {}
    except Exception:
        pass
    if prev.get("updated_at"):
        try:
            age = (datetime.now(timezone.utc) -
                   datetime.fromisoformat(prev["updated_at"])).total_seconds()
            if age < 22 * 3600:
                log.info("food: fresh (<22h), carried over")
                return prev
        except Exception:
            pass

    now = datetime.now(timezone.utc)
    cur = now.year * 100 + now.month
    # 找最新有資料的參考月（用美國大豆探路）
    L = None
    for k in range(2, 9):
        p = _ym_add(cur, -k)
        r = await _comtrade_month(session, "842", p)
        await asyncio.sleep(5)
        if r and r.get("1201", 0) > 0:
            L = p; break
    if not L:
        log.warning("food: no reference month found")
        return {**prev, "stale": True} if prev else {}
    L12 = _ym_add(L, -12)

    async def collect(month):
        tot = {c: 0 for c, _ in FOOD_CMDS}; ok = 0
        for rep, _ in FOOD_EXPORTERS:
            r = await _comtrade_month(session, rep, month)
            await asyncio.sleep(5)
            if r:
                ok += 1
                for c, _ in FOOD_CMDS:
                    tot[c] += r.get(c, 0)
        return tot, ok
    cur_t, ok1 = await collect(L)
    prev_t, ok2 = await collect(L12)
    if ok1 == 0:
        return {**prev, "stale": True} if prev else {}

    items, breadth = [], 0
    for c, name in FOOD_CMDS:
        a = cur_t[c] / 1e7           # 萬噸
        b = prev_t[c] / 1e7
        yoy = round((a - b) / b * 100, 1) if b > 0 else None
        if yoy is not None and yoy >= 15:
            breadth += 1
        items.append({"cmd": c, "name": name,
                      "wan_ton": round(a, 1), "prev_wan_ton": round(b, 1),
                      "yoy_pct": yoy})
    log.info(f"food: ref={L} soy={items[0]['wan_ton']}萬噸 yoy={items[0]['yoy_pct']} breadth={breadth}")
    return {
        "updated_at": now.isoformat(),
        "ref_month": f"{L//100}-{L%100:02d}",
        "prev_year_month": f"{L12//100}-{L12%100:02d}",
        "exporters": [n for _, n in FOOD_EXPORTERS],
        "items": items,
        "breadth_up": breadth,
        "note": "鏡像代理值（主要出口國對中出口合計）· 月資料約 3–4 月落差 · 結構性背景指標",
    }


# ─────────────────────────────────────────────────────────────
# 🌾 糧食進口「月度歷史」— 近 5 年逐月序列（1/3/5 年趨勢）
#   ≤2024-12：中國海關直報（reporter=中國, partner=全世界，1 呼叫/月，永久快取）
#   ≥2025-01：中國停報 Comtrade → 改用鏡像（主要出口國對中出口合計，7 呼叫/月）
#   每次執行只回填有限筆數，尊重 Comtrade 限速與 12 分鐘工時上限，逐步補齊。
# ─────────────────────────────────────────────────────────────
FOOD_HIST_MONTHS    = 60        # 視窗：近 5 年
CHINA_REPORT_CUTOFF = 202412    # 中國自 2025 起停報 Comtrade
HIST_MIRROR_BUDGET  = 3         # 每次最多回填幾個「鏡像」月（每月 7 呼叫）
HIST_CHINA_BUDGET   = 15        # 每次最多回填幾個「中國直報」月（每月 1 呼叫）

async def _comtrade_china_import(session, period: int):
    """中國該月自全世界進口三主糧 {cmd: netWgt kg}；失敗回 None。"""
    params = {"reporterCode": "156", "flowCode": "M", "partnerCode": "0",
              "cmdCode": "1201,1001,1005", "period": str(period),
              "partner2Code": "0", "motCode": "0"}
    for attempt, bk in ((1, 8), (2, 15), (3, 0)):
        try:
            async with session.get(COMTRADE_URL, params=params,
                    headers={"User-Agent": USER_AGENT},
                    timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status == 429:
                    if bk: await asyncio.sleep(bk); continue
                    return None
                txt = await r.text()
            data = json.loads(txt)
            out = {}
            for row in (data.get("data") or []):
                cmd = str(row.get("cmdCode"))
                out[cmd] = out.get(cmd, 0) + (row.get("netWgt") or 0)
            return out
        except Exception:
            if bk: await asyncio.sleep(bk)
            else: return None
    return None

async def _food_mirror_total(session, month: int):
    """主要出口國該月對中出口三主糧合計 {cmd: netWgt kg}, ok=成功國數。"""
    tot = {c: 0 for c, _ in FOOD_CMDS}; ok = 0
    for rep, _ in FOOD_EXPORTERS:
        r = await _comtrade_month(session, rep, month)
        await asyncio.sleep(3)
        if r:
            ok += 1
            for c, _ in FOOD_CMDS:
                tot[c] += r.get(c, 0)
    return tot, ok

async def fetch_food_history(session: aiohttp.ClientSession) -> list:
    store = {}
    try:
        raw = json.loads(FOOD_HISTORY_FILE.read_text(encoding="utf-8"))
        store = (raw.get("months") if isinstance(raw, dict) else {}) or {}
    except Exception:
        store = {}

    now = datetime.now(timezone.utc)
    cur = now.year * 100 + now.month
    targets = [_ym_add(cur, -k) for k in range(1, FOOD_HIST_MONTHS + 1)]
    def key(ym): return f"{ym // 100}-{ym % 100:02d}"

    missing_mirror = [ym for ym in targets if ym > CHINA_REPORT_CUTOFF and key(ym) not in store]
    missing_china  = [ym for ym in targets if ym <= CHINA_REPORT_CUTOFF and key(ym) not in store]
    # 最近一個已存鏡像月也重抓一次（月資料會回修）
    stored_mirror = sorted([ym for ym in targets
                            if ym > CHINA_REPORT_CUTOFF and key(ym) in store], reverse=True)
    refresh = stored_mirror[:1]

    try:
        # 先補最近的鏡像月（使用者最先想看「近一年」），再補中國直報深歷史
        for ym in sorted(set(missing_mirror + refresh), reverse=True)[:HIST_MIRROR_BUDGET]:
            tot, ok = await _food_mirror_total(session, ym)
            if ok:
                store[key(ym)] = {"soy": round(tot["1201"] / 1e7, 1),
                                  "wheat": round(tot["1001"] / 1e7, 1),
                                  "corn": round(tot["1005"] / 1e7, 1), "src": "mirror"}
        for ym in sorted(missing_china, reverse=True)[:HIST_CHINA_BUDGET]:
            r = await _comtrade_china_import(session, ym)
            await asyncio.sleep(3)
            if r:
                store[key(ym)] = {"soy": round(r.get("1201", 0) / 1e7, 1),
                                  "wheat": round(r.get("1001", 0) / 1e7, 1),
                                  "corn": round(r.get("1005", 0) / 1e7, 1), "src": "china"}
    except Exception as e:
        log.warning(f"food history backfill error: {e}")

    keep = {key(ym) for ym in targets}
    store = {k: v for k, v in store.items() if k in keep}
    try:
        FOOD_HISTORY_FILE.write_text(json.dumps({"months": store}, ensure_ascii=False),
                                     encoding="utf-8")
    except Exception as e:
        log.warning(f"food history write error: {e}")

    series = [{"ym": k, **store[k]} for k in sorted(store.keys())]
    remaining = len([ym for ym in targets if key(ym) not in store])
    log.info(f"food history: {len(store)}/{len(targets)} months filled, {remaining} remaining")
    return series


# ─────────────────────────────────────────────────────────────
# ⚙️ 戰略物資進口監測（軍工必需、中國高度依賴進口的原物料）
#   方法同糧食：中國自 2025 起停報 Comtrade → 用「主要出口國對中出口」鏡像加總。
#   觀察「異常高」（突然囤積＝可能備戰）或「異常低」（可能改用儲備、降低國際牽制）。
#   石油刻意不納入：中國最大油源（俄、沙、伊拉克）皆不報 Comtrade，鏡像抓不到。
# ─────────────────────────────────────────────────────────────
STRAT_MATERIALS = [
    {"cmd": "4001", "name": "天然橡膠", "use": "輪胎・密封件",
     "exp": [("764", "泰國"), ("360", "印尼"), ("458", "馬來西亞"), ("704", "越南")],
     "hi": "輪胎、履帶、密封件等軍需橡膠需求突增，可能擴大車輛與裝備生產",
     "lo": "轉用戰備儲備或民用需求萎縮，須留意產線與經濟訊號"},
    {"cmd": "2604", "name": "鎳礦砂", "use": "特殊鋼・超合金",
     "exp": [("608", "菲律賓"), ("360", "印尼"), ("36", "澳洲")],
     "hi": "不鏽鋼、噴射引擎超合金、電池用鎳需求升高，指向軍工/國防產能擴張",
     "lo": "改用庫存或冶煉調整，也可能反映製造業放緩"},
    {"cmd": "2610", "name": "鉻礦砂", "use": "裝甲鋼・不鏽鋼",
     "exp": [("710", "南非"), ("792", "土耳其"), ("398", "哈薩克")],
     "hi": "裝甲鋼、槍砲耐蝕鋼需求升高，是典型的軍備擴張訊號",
     "lo": "改用儲備或不鏽鋼需求下滑"},
    {"cmd": "2601", "name": "鐵礦砂", "use": "鋼鐵（戰爭核心）",
     "exp": [("36", "澳洲"), ("76", "巴西"), ("710", "南非"), ("699", "印度")],
     "hi": "鋼鐵產能全開（造艦、彈藥、基建），強烈的備戰/擴產訊號",
     "lo": "經濟走弱，或改用國內礦與儲備、降低海運遭封鎖的曝險（戰前也可能出現）"},
]

async def _comtrade_one(session, reporter: str, cmd: str, period: int):
    """某出口國該月對中國(156)出口某 HS 商品的淨重(kg)；失敗回 None。"""
    params = {"reporterCode": reporter, "flowCode": "X", "partnerCode": "156",
              "cmdCode": cmd, "period": str(period), "partner2Code": "0", "motCode": "0"}
    for attempt, bk in ((1, 8), (2, 15), (3, 0)):
        try:
            async with session.get(COMTRADE_URL, params=params,
                    headers={"User-Agent": USER_AGENT},
                    timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status == 429:
                    if bk: await asyncio.sleep(bk); continue
                    return None
                txt = await r.text()
            data = json.loads(txt)
            return sum((row.get("netWgt") or 0) for row in (data.get("data") or []))
        except Exception:
            if bk: await asyncio.sleep(bk)
            else: return None
    return None

async def fetch_strategic_imports(session: aiohttp.ClientSession) -> dict:
    """中國戰略物資（橡膠/鎳/鉻/鐵礦）鏡像進口量＋年增率＋異常旗標。每日更新一次。"""
    prev = {}
    try:
        prev = json.loads(DATA_FILE.read_text(encoding="utf-8")).get("strat") or {}
    except Exception:
        pass
    if prev.get("updated_at"):
        try:
            age = (datetime.now(timezone.utc) -
                   datetime.fromisoformat(prev["updated_at"])).total_seconds()
            if age < 22 * 3600:
                log.info("strat: fresh (<22h), carried over")
                return prev
        except Exception:
            pass

    now = datetime.now(timezone.utc)
    cur = now.year * 100 + now.month
    # 用鐵礦砂（澳洲，量大且穩定回報）探最新有資料的參考月
    L = None
    for k in range(2, 9):
        p = _ym_add(cur, -k)
        v = await _comtrade_one(session, "36", "2601", p)
        await asyncio.sleep(3)
        if v and v > 0:
            L = p; break
    if not L:
        log.warning("strat: no reference month found")
        return {**prev, "stale": True} if prev else {}
    L12 = _ym_add(L, -12)

    async def collect(cmd, exps, month):
        tot, ok = 0, 0
        for rep, _ in exps:
            v = await _comtrade_one(session, rep, cmd, month)
            await asyncio.sleep(3)
            if v is not None:
                if v > 0: ok += 1
                tot += v
        return tot, ok

    items = []
    for m in STRAT_MATERIALS:
        cur_t, ok1 = await collect(m["cmd"], m["exp"], L)
        prev_t, _ = await collect(m["cmd"], m["exp"], L12)
        if ok1 == 0:
            continue
        a, b = cur_t / 1e7, prev_t / 1e7          # 萬噸
        yoy = round((a - b) / b * 100, 1) if b > 0 else None
        anomaly = ""
        if yoy is not None:
            if yoy >= 25: anomaly = "high"
            elif yoy <= -25: anomaly = "low"
        items.append({"cmd": m["cmd"], "name": m["name"], "use": m["use"],
                      "wan_ton": round(a, 1), "prev_wan_ton": round(b, 1),
                      "yoy_pct": yoy, "anomaly": anomaly,
                      "hi": m["hi"], "lo": m["lo"]})
    if not items:
        return {**prev, "stale": True} if prev else {}
    log.info(f"strat: ref={L} materials={len(items)}")
    return {
        "updated_at": now.isoformat(),
        "ref_month": f"{L // 100}-{L % 100:02d}",
        "prev_year_month": f"{L12 // 100}-{L12 % 100:02d}",
        "items": items,
        "note": "鏡像代理值（主要出口國對中出口合計）· 月資料約 3–4 月落差 · 異常高＝突然囤積、異常低＝改用儲備，皆須交叉印證",
    }


# 戰略物資「月度」歷史（近 3 年逐月，供前端畫趨勢、觀察變動）
STRAT_HISTORY_FILE = DATA_DIR / "strat_history.json"
STRAT_HIST_MONTHS  = 36
STRAT_CHINA_CUTOFF = 202412
STRAT_HIST_MIRROR_BUDGET = 2      # 每次回填幾個「鏡像」月（每月約 14 呼叫）
STRAT_HIST_CHINA_BUDGET  = 12     # 每次回填幾個「中國直報」月（每月 1 呼叫，批次 4 個 HS）

async def _comtrade_china_strat(session, period: int):
    """中國該月自全世界進口 4 項戰略物資 {cmd: netWgt kg}；失敗回 None。"""
    cmds = ",".join(m["cmd"] for m in STRAT_MATERIALS)
    params = {"reporterCode": "156", "flowCode": "M", "partnerCode": "0",
              "cmdCode": cmds, "period": str(period), "partner2Code": "0", "motCode": "0"}
    for attempt, bk in ((1, 8), (2, 15), (3, 0)):
        try:
            async with session.get(COMTRADE_URL, params=params,
                    headers={"User-Agent": USER_AGENT},
                    timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status == 429:
                    if bk: await asyncio.sleep(bk); continue
                    return None
                txt = await r.text()
            data = json.loads(txt)
            out = {}
            for row in (data.get("data") or []):
                c = str(row.get("cmdCode"))
                out[c] = out.get(c, 0) + (row.get("netWgt") or 0)
            return out
        except Exception:
            if bk: await asyncio.sleep(bk)
            else: return None
    return None

async def fetch_strategic_history(session: aiohttp.ClientSession) -> list:
    """近 3 年逐月戰略物資進口（萬噸）。≤2024-12 中國直報（批次、便宜），≥2025 鏡像。逐步回填。"""
    store = {}
    try:
        raw = json.loads(STRAT_HISTORY_FILE.read_text(encoding="utf-8"))
        store = (raw.get("months") if isinstance(raw, dict) else {}) or {}
    except Exception:
        store = {}
    now = datetime.now(timezone.utc)
    cur = now.year * 100 + now.month
    targets = [_ym_add(cur, -k) for k in range(1, STRAT_HIST_MONTHS + 1)]
    def key(ym): return f"{ym // 100}-{ym % 100:02d}"
    cmds = [m["cmd"] for m in STRAT_MATERIALS]

    missing_mirror = [ym for ym in targets if ym > STRAT_CHINA_CUTOFF and key(ym) not in store]
    missing_china  = [ym for ym in targets if ym <= STRAT_CHINA_CUTOFF and key(ym) not in store]
    stored_mirror  = sorted([ym for ym in targets if ym > STRAT_CHINA_CUTOFF and key(ym) in store], reverse=True)
    refresh = stored_mirror[:1]

    try:
        for ym in sorted(set(missing_mirror + refresh), reverse=True)[:STRAT_HIST_MIRROR_BUDGET]:
            rec = {"src": "mirror"}
            any_ok = False
            for m in STRAT_MATERIALS:
                tot = 0
                for rep, _ in m["exp"]:
                    v = await _comtrade_one(session, rep, m["cmd"], ym)
                    await asyncio.sleep(3)
                    if v: tot += v; any_ok = True
                rec[m["cmd"]] = round(tot / 1e7, 1)
            if any_ok:
                store[key(ym)] = rec
        for ym in sorted(missing_china, reverse=True)[:STRAT_HIST_CHINA_BUDGET]:
            d = await _comtrade_china_strat(session, ym)
            await asyncio.sleep(3)
            if d:
                rec = {"src": "china"}
                for c in cmds:
                    rec[c] = round(d.get(c, 0) / 1e7, 1)
                store[key(ym)] = rec
    except Exception as e:
        log.warning(f"strat history backfill error: {e}")

    keep = {key(ym) for ym in targets}
    store = {k: v for k, v in store.items() if k in keep}
    try:
        STRAT_HISTORY_FILE.write_text(json.dumps({"months": store}, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log.warning(f"strat history write error: {e}")
    series = [{"ym": k, **store[k]} for k in sorted(store.keys())]
    remaining = len([ym for ym in targets if key(ym) not in store])
    log.info(f"strat history: {len(store)}/{len(targets)} months, {remaining} remaining")
    return series


# ─────────────────────────────────────────────────────────────
# 🇺🇸→🇨🇳 USDA FAS ESR — 美國對中國每週穀物出口銷售（最即時，需 API key）
# 需 GitHub Secret USDA_FAS_API_KEY；未設定則自動略過
# ─────────────────────────────────────────────────────────────
USDA_ESR = "https://api.fas.usda.gov/api/esr"
USDA_WANT = {"Soybeans": "大豆", "Wheat": "小麥", "Corn": "玉米"}

async def _usda_get(session, path, key):
    try:
        async with session.get(USDA_ESR + path,
                headers={"X-Api-Key": key, "Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=25)) as r:
            if r.status != 200:
                log.warning(f"USDA {path} -> HTTP {r.status}")
                return None
            return json.loads(await r.text())
    except Exception as e:
        log.warning(f"USDA {path} failed: {e}")
        return None

async def fetch_usda_esr(session: aiohttp.ClientSession) -> dict | None:
    import os
    key = (os.environ.get("USDA_FAS_API_KEY") or "").strip()
    if not key:
        return None
    prev = {}
    try:
        prev = json.loads(DATA_FILE.read_text(encoding="utf-8")).get("usda") or {}
    except Exception:
        pass
    if prev.get("updated_at"):
        try:
            age = (datetime.now(timezone.utc) -
                   datetime.fromisoformat(prev["updated_at"])).total_seconds()
            if age < 6 * 3600:
                log.info("USDA ESR: fresh (<6h), carried over")
                return prev
        except Exception:
            pass

    commodities = await _usda_get(session, "/commodities", key)
    countries = await _usda_get(session, "/countries", key)
    if not commodities or not countries:
        log.warning(f"USDA ESR: commodities={commodities is not None} countries={countries is not None}")
        return {**prev, "stale": True} if prev else None
    log.info(f"USDA ESR: {len(commodities)} commodities, {len(countries)} countries")

    # 找中國國家代碼（排除香港/台灣/澳門）— 不分大小寫，容忍 "CHINA, PEOPLES REPUBLIC OF"
    china = None
    for c in countries:
        nm = (c.get("countryName") or "").strip().lower()
        if "china" in nm and "hong" not in nm and "taiwan" not in nm and "macau" not in nm:
            china = c.get("countryCode")
            log.info(f"USDA ESR: matched China -> code={china} name={c.get('countryName')!r}")
            break
    if china is None:
        sample = [ (c.get("countryName") or "") for c in countries if "china" in (c.get("countryName") or "").lower() ]
        log.warning(f"USDA ESR: no China country matched; china-like={sample[:5]}")
        return {**prev, "stale": True} if prev else None

    # 對映想要的商品代碼 — 以關鍵字比對（ESR 小麥可能拆成 "All Wheat" 或分級），不分大小寫
    # USDA_WANT: {"Soybeans":..,"Wheat":..,"Corn":..}
    cmap = {}
    for want in USDA_WANT:  # Soybeans / Wheat / Corn
        kw = want.lower()
        best = None
        for c in commodities:
            nm = (c.get("commodityName") or "").strip()
            low = nm.lower()
            if kw in low:
                # 小麥優先取彙總 "All Wheat"，避免只抓到單一分級
                if want == "Wheat":
                    if low.startswith("all wheat") or "all wheat" in low:
                        best = c.get("commodityCode"); break
                    if best is None:
                        best = c.get("commodityCode")
                else:
                    best = c.get("commodityCode"); break
        if best is not None:
            cmap[want] = best
    log.info(f"USDA ESR: commodity codes -> {cmap}")

    yr = datetime.now(timezone.utc).year
    items, latest_week = [], ""
    for nm, zh in USDA_WANT.items():
        cc = cmap.get(nm)
        if cc is None:
            log.warning(f"USDA ESR: no commodity code for {nm}")
            continue
        recs = []
        for my in (yr, yr - 1, yr + 1):
            d = await _usda_get(session, f"/exports/commodityCode/{cc}/countryCode/{china}/marketYear/{my}", key)
            if d:
                recs.extend(d)
        if not recs:
            log.warning(f"USDA ESR: {nm} (code={cc}) no records for MY {yr-1}/{yr}/{yr+1}")
            continue
        recs = [r for r in recs if r.get("weekEndingDate")]
        if not recs:
            log.warning(f"USDA ESR: {nm} records missing weekEndingDate")
            continue
        r = max(recs, key=lambda x: x.get("weekEndingDate", ""))
        wk = (r.get("weekEndingDate") or "")[:10]
        if wk > latest_week:
            latest_week = wk
        items.append({
            "name": zh,
            "week_net_kt": round((r.get("currentMYNetSales") or 0) / 1000, 1),
            "outstanding_kt": round((r.get("outstandingSales") or 0) / 1000, 1),
            "commit_kt": round((r.get("currentMYTotalCommitment") or 0) / 1000, 1),
            "week": wk,
        })
    if not items:
        log.warning("USDA ESR: matched China+commodities but assembled 0 items")
        return {**prev, "stale": True} if prev else None
    log.info(f"USDA ESR: week {latest_week}, {len(items)} commodities")
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "week_ending": latest_week,
        "items": items,
        "note": "美國對中國每週出口銷售（USDA FAS ESR）· 週更 · 淨銷售=本週新訂單、未裝運=已訂未運",
    }


# ─────────────────────────────────────────────────────────────
# USGS — 核試驗場周邊地震監測（核試驗 = 淺層人工地震特徵）
# ─────────────────────────────────────────────────────────────
async def fetch_nuclear_seismic(session: aiohttp.ClientSession) -> dict:
    """查詢過去 72h 各核試驗場 150km 內 M2.5+ 地震。正常應為 0。"""
    from datetime import timedelta
    start = (datetime.now(timezone.utc) - timedelta(hours=72)).strftime("%Y-%m-%dT%H:%M:%S")
    sites_out = []
    total = 0
    for site in NUCLEAR_TEST_SITES:
        params = {
            "format": "geojson", "starttime": start, "minmagnitude": "2.5",
            "latitude": str(site["lat"]), "longitude": str(site["lon"]),
            "maxradiuskm": "150",
        }
        try:
            async with session.get(
                USGS_API, params=params,
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": USER_AGENT},
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
            events = []
            for f in (data.get("features") or [])[:5]:
                p = f.get("properties") or {}
                g = (f.get("geometry") or {}).get("coordinates") or [None, None, None]
                events.append({
                    "mag": p.get("mag"), "place": p.get("place"),
                    "time": p.get("time"), "depth_km": g[2],
                })
            count = data.get("metadata", {}).get("count", len(events))
            total += count
            sites_out.append({**{k: site[k] for k in ("key", "name")},
                              "count": count, "events": events})
        except Exception as e:
            log.warning(f"USGS {site['key']} failed: {e}")
            sites_out.append({**{k: site[k] for k in ("key", "name")},
                              "count": None, "events": []})
    log.info(f"USGS nuclear seismic: {total} events near test sites (72h)")
    return {"sites": sites_out, "total_72h": total, "window_hours": 72}


# ─────────────────────────────────────────────────────────────
# Wikipedia — 公眾焦慮指數（戰爭條目瀏覽量 vs 30 日基準）
# ─────────────────────────────────────────────────────────────
async def fetch_wikipedia_anxiety(session: aiohttp.ClientSession) -> dict:
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    end   = (now - timedelta(days=1)).strftime("%Y%m%d") + "00"   # 資料延遲 ~1 天
    start = (now - timedelta(days=31)).strftime("%Y%m%d") + "00"

    async def one(title: str):
        url = f"{WIKI_PV_API}/{title}/daily/{start}/{end}"
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
            views = [it["views"] for it in data.get("items", [])]
            if len(views) < 10:
                return None
            latest = sum(views[-2:]) / 2                     # 最近 2 天平均
            base_v = sorted(views[:-2])
            baseline = base_v[len(base_v) // 2] or 1        # 前 28 天中位數
            return {"title": title, "latest": round(latest),
                    "baseline": baseline,
                    "ratio": round(latest / baseline, 2)}
        except Exception as e:
            log.warning(f"Wiki pageviews {title} failed: {e}")
            return None

    pages = [p for p in await asyncio.gather(*(one(t) for t in WIKI_ANXIETY_PAGES)) if p]
    if not pages:
        return {}
    mean_ratio = sum(p["ratio"] for p in pages) / len(pages)
    # ratio 1.0（正常）≈ 25 分；2 倍 ≈ 50；4 倍以上 → 100
    score = round(min(100.0, mean_ratio * 25), 1)
    top = max(pages, key=lambda p: p["ratio"])
    log.info(f"Wiki anxiety: score={score} mean_ratio={mean_ratio:.2f} top={top['title']} x{top['ratio']}")
    return {"score": score, "mean_ratio": round(mean_ratio, 2), "pages": pages}


# ─────────────────────────────────────────────────────────────
# FAA NOTAM — 衝突區 FIR 領空限制/關閉監測
# ─────────────────────────────────────────────────────────────
async def fetch_notams(session: aiohttp.ClientSession) -> dict:
    """
    查詢各地區 FIR 的有效 NOTAM，統計警戒類（限制/危險/關閉）數量。
    回傳 {region_key: {firs, total, danger, closure, score}}
    """
    # 上一輪數值作為 fallback（非官方端點偶發 503）
    prev = {}
    try:
        prev = json.loads(DATA_FILE.read_text(encoding="utf-8")).get("notams") or {}
    except Exception:
        pass

    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://notams.aim.faa.gov",
        "Referer": "https://notams.aim.faa.gov/notamSearch/nsapp.html",
    }

    out = {}
    for key, firs in REGION_FIRS.items():
        total = danger = 0
        closure = False
        ok = False
        for fir in firs:
            for attempt in (1, 2):
                try:
                    async with session.post(
                        NOTAM_API,
                        data={"searchType": "0", "designatorsForLocation": fir},
                        timeout=aiohttp.ClientTimeout(total=20),
                        headers=headers,
                    ) as resp:
                        resp.raise_for_status()
                        data = await resp.json(content_type=None)
                    notams = data.get("notamList") or []
                    ok = True
                    total += len(notams)
                    for n in notams:
                        msg = (n.get("icaoMessage") or "") + " " + (n.get("traditionalMessage") or "")
                        if NOTAM_DANGER_RE.search(msg):
                            danger += 1
                        if NOTAM_CLOSURE_RE.search(msg):
                            closure = True
                    break
                except Exception as e:
                    if attempt == 2:
                        log.warning(f"NOTAM {fir} failed: {e}")
                    else:
                        await asyncio.sleep(5)
            await asyncio.sleep(1.5)
        if ok:
            score = min(100.0, danger * 8 + (40 if closure else 0))
            out[key] = {"firs": firs, "total": total, "danger": danger,
                        "closure": closure, "score": round(score, 1)}
        elif key in prev:
            out[key] = {**prev[key], "stale": True}

    fresh = sum(1 for v in out.values() if not v.get("stale"))
    dangers = {k: v["danger"] for k, v in out.items()}
    log.info(f"NOTAM: {fresh}/{len(REGION_FIRS)} fresh ({len(out) - fresh} carried), danger={dangers}")
    return out


# ─────────────────────────────────────────────────────────────
# BestTime — Pentagon 周邊酒吧即時人流（反向披薩指數）
# 酒吧下班後「該忙卻異常冷清」= 幕僚沒去喝酒、留守加班
# ─────────────────────────────────────────────────────────────
async def fetch_bars(session: aiohttp.ClientSession) -> dict:
    key = os.environ.get("BESTTIME_API_KEY", "").strip()
    if not key:
        return {"available": False, "reason": "未設定 BESTTIME_API_KEY", "bars": []}

    # 只在美東傍晚下班時段查詢（省 credit）
    et_hour = None
    if ZoneInfo is not None:
        try:
            et_hour = datetime.now(ZoneInfo("America/New_York")).hour
        except Exception:
            et_hour = None
    if et_hour is not None and et_hour not in BAR_QUERY_ET_HOURS:
        return {"available": False, "reason": "非下班時段（僅美東 16–24 時查詢）",
                "et_hour": et_hour, "bars": []}

    async def one(bar):
        params = {"api_key_private": key, "venue_name": bar["name"],
                  "venue_address": bar["address"]}
        try:
            async with session.post(
                BESTTIME_API, params=params,
                timeout=aiohttp.ClientTimeout(total=25),
                headers={"User-Agent": USER_AGENT},
            ) as resp:
                data = await resp.json(content_type=None)
            an = data.get("analysis") or {}
            live_ok = bool(an.get("venue_live_busyness_available"))
            return {
                "name": bar["name"],
                "live_available": live_ok,
                "live_busyness": an.get("venue_live_busyness") if live_ok else None,
                "forecasted": an.get("venue_forecasted_busyness"),
                "delta": an.get("venue_live_forecasted_delta") if live_ok else None,
                "open": (data.get("venue_info") or {}).get("venue_open"),
            }
        except Exception as e:
            log.warning(f"BestTime {bar['name']} failed: {e}")
            return {"name": bar["name"], "live_available": False, "live_busyness": None,
                    "forecasted": None, "delta": None, "open": None, "error": True}

    bars = await asyncio.gather(*(one(b) for b in PENTAGON_BARS))
    live_bars = [b for b in bars if b["live_available"] and b["live_busyness"] is not None]

    result = {"available": bool(live_bars), "bars": bars,
              "open_count": len(live_bars), "total": len(bars)}
    if live_bars:
        avg_live = sum(b["live_busyness"] for b in live_bars) / len(live_bars)
        deltas = [b["delta"] for b in live_bars if b["delta"] is not None]
        avg_delta = sum(deltas) / len(deltas) if deltas else 0
        # 冷清度：每間酒吧「比平時安靜多少」，正值＝異常冷清＝加班訊號。
        # 先逐間 clamp（熱鬧的店只貢獻 0，不抵銷別家的冷清），再把整體平均與
        # 「最冷清的單店」混合，讓「任一關鍵酒吧變鬼城」也能觸發，同時保留廣度。
        per_empt = [max(0.0, -d) for d in deltas]
        avg_empt = sum(per_empt) / len(per_empt) if per_empt else 0.0
        max_empt = max(per_empt) if per_empt else 0.0
        emptiness = 0.6 * avg_empt + 0.4 * max_empt
        # 加班分數 0–100：冷清度映射（比平時安靜 40% 即封頂），供前端統一分級／重用
        overtime_score = round(min(100.0, emptiness / 40.0 * 100), 1)
        result.update({
            "avg_live_busyness": round(avg_live, 1),
            "avg_delta": round(avg_delta, 1),
            "max_emptiness": round(max_empt, 1),
            "emptiness": round(emptiness, 1),
            "overtime_score": overtime_score,
        })
        log.info(f"Bars: {len(live_bars)}/{len(bars)} open, avg_live={avg_live:.0f}% "
                 f"avg_delta={avg_delta:+.0f}% emptiness={emptiness:.0f} score={overtime_score:.0f}")
    else:
        result["reason"] = "目前無酒吧即時資料（可能皆未營業）"
        log.info(f"Bars: no live data ({result.get('reason')})")
    return result


# ─────────────────────────────────────────────────────────────
# 地區風險引擎 — 「哪些地區快打起來」
# ─────────────────────────────────────────────────────────────
def _region_poly_score(cfg: dict, polymarket: list[dict]) -> tuple[float | None, str | None]:
    """
    該地區相關盤口的交易量加權戰爭機率（0-100）。
    和平方向的盤（停火/協議）反向計分：停火機率低 = 戰爭持續。
    回傳 (score, 最具代表性的盤口問題)
    """
    weighted = 0.0
    vol_sum = 0.0
    top_q, top_vol = None, 0.0
    for m in polymarket:
        if m.get("yes_price") is None:
            continue
        q = (m.get("question") or "").lower()
        if not any(kw in q for kw in cfg["poly_kw"]):
            continue
        yes = float(m["yes_price"])
        vol = float(m.get("volume") or 1)
        risk = (1 - yes) if any(p in q for p in PEACE_MARKERS) else yes
        weighted += risk * vol
        vol_sum += vol
        if vol > top_vol:
            top_vol, top_q = vol, m.get("question")
    if vol_sum <= 0:
        return None, None
    return min(100.0, weighted / vol_sum * 100), top_q


def build_region_risks(polymarket: list[dict], gdelt: dict,
                       firms: dict, aviation: dict,
                       notams: dict | None = None) -> list[dict]:
    notams = notams or {}
    by_region_hits = {}
    for h in (firms.get("conflict_hotspots") or []):
        by_region_hits[h["region"]] = by_region_hits.get(h["region"], 0) + 1

    avi_by_region = {}
    for a in (aviation.get("aircraft") or []):
        avi_by_region[a.get("region")] = avi_by_region.get(a.get("region"), 0) + 1

    regions_out = []
    for key, cfg in REGIONS.items():
        factors = {}
        weights = {}

        poly_score, top_q = _region_poly_score(cfg, polymarket)
        if poly_score is not None:
            factors["poly"] = round(poly_score, 1)
            weights["poly"] = 0.35

        g = gdelt.get(key)
        if g:
            # 新聞量佔全球 % → 0-100（1% ≈ 25 分；重大戰事平時 2-3%，激增 4%+ 滿分）
            factors["gdelt"] = round(min(100.0, g["latest"] * 25), 1)
            factors["gdelt_delta"] = g["delta_pct"]
            weights["gdelt"] = 0.25

        nt = notams.get(key)
        if nt:
            factors["notam"] = nt["score"]
            factors["notam_danger"] = nt["danger"]
            factors["notam_closure"] = nt["closure"]
            weights["notam"] = 0.15

        fire_n = sum(by_region_hits.get(r, 0) for r in cfg["firms"])
        factors["firms"] = round(min(100.0, fire_n * 12), 1)
        factors["firms_hotspots"] = fire_n
        weights["firms"] = 0.12

        avi_n = sum(avi_by_region.get(r, 0) for r in cfg["avi_regions"])
        factors["avi"] = round(min(100.0, avi_n * 10), 1)
        factors["avi_count"] = avi_n
        weights["avi"] = 0.13

        # 只用可用因子並重新正規化權重
        usable = {k: w for k, w in weights.items() if k in factors}
        wsum = sum(usable.values()) or 1
        score = sum(factors[k] * w for k, w in usable.items()) / wsum

        if score >= 65:  level = "CRITICAL"
        elif score >= 45: level = "HIGH"
        elif score >= 25: level = "ELEVATED"
        else:             level = "WATCH"

        regions_out.append({
            "key": key, "name": cfg["name"], "flag": cfg["flag"],
            "score": round(score, 1), "level": level,
            "factors": factors, "top_market": top_q,
        })

    regions_out.sort(key=lambda r: -r["score"])
    return regions_out


# ─────────────────────────────────────────────────────────────
# 歷史趨勢 — 供前端顯示「風險上升中/下降中」（提前預警的關鍵）
# ─────────────────────────────────────────────────────────────
def update_history(score: dict, pizza_index, regions: list[dict], wiki_score=None,
                   aviation: dict | None = None) -> list[dict]:
    from datetime import timedelta
    history = []
    try:
        history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        if not isinstance(history, list):
            history = []
    except Exception:
        pass

    now = datetime.now(timezone.utc)
    rec = {
        "ts": now.isoformat(timespec="minutes"),
        "combined": score["combined_score"],
        "poly": score["polymarket_score"],
        "pizza": pizza_index,
        "wiki": wiki_score,
        "regions": {r["key"]: r["score"] for r in regions},
    }
    # 記錄軍機各機型架數（供 AVI 卡片 24h/7d/30d 歷史變化；短鍵省空間）
    s = (aviation or {}).get("summary") or {}
    rec["avi"] = {"t": s.get("tankers", 0), "a": s.get("awacs", 0),
                  "u": s.get("uav", 0), "c": s.get("c4isr", 0), "tot": s.get("total", 0)}
    history.append(rec)
    # 保留 31 天（30 天變化需要）
    cutoff = (now - timedelta(days=31)).isoformat()
    history = [h for h in history if h.get("ts", "") >= cutoff]
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
    return history


# ─────────────────────────────────────────────────────────────
# 💰 經濟避險指標（伺服器端抓 Yahoo，供長期封存；前端另有即時版本）
#   與前端 FIN 卡片相同標的：金/布油/瑞郎/VIX/小麥 + 四檔國防股
# ─────────────────────────────────────────────────────────────
FIN_TICKERS = ["GC=F", "BZ=F", "USDCHF=X", "^VIX", "ZW=F", "LMT", "RTX", "NOC", "GD",
               "^TNX", "^FVX", "^TYX"]   # 美 10/5/30 年公債殖利率（資金逃向安全資產）

# FRED 免費 API（信用利差代理；需設定 FRED_API_KEY 環境變數才啟用）
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
FRED_SERIES = {"em_oas": "BAMLEMCBPIOAS",   # ICE BofA 新興市場公司債利差（廣義 EM 風險）
               "hy_oas": "BAMLH0A0HYM2"}    # ICE BofA 美國高收益債利差（信用壓力）

async def fetch_fred(session: aiohttp.ClientSession) -> dict:
    """抓 FRED 信用利差（最新一筆）。未設定 FRED_API_KEY 時回傳空 dict（優雅略過）。"""
    if not FRED_API_KEY:
        return {}
    out = {}
    for name, sid in FRED_SERIES.items():
        url = ("https://api.stlouisfed.org/fred/series/observations?series_id=" + sid
               + "&api_key=" + FRED_API_KEY + "&file_type=json&sort_order=desc&limit=1")
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                j = await resp.json(content_type=None)
            obs = (j or {}).get("observations") or []
            v = obs[0].get("value") if obs else None
            out[name] = float(v) if v not in (None, "", ".") else None
        except Exception as e:
            log.warning(f"FRED {sid} fetch failed: {e}")
    log.info(f"FRED: fetched {len(out)}/{len(FRED_SERIES)} series")
    return out

async def fetch_finance(session: aiohttp.ClientSession) -> dict:
    import urllib.parse
    out = {}
    for sym in FIN_TICKERS:
        url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
               + urllib.parse.quote(sym) + "?interval=1d&range=1mo")
        for attempt, backoff in ((1, 2), (2, 0)):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15),
                        headers={"User-Agent": "Mozilla/5.0 (compatible; warhub/1.0)"}) as resp:
                    j = await resp.json(content_type=None)
                r = (((j or {}).get("chart") or {}).get("result") or [None])[0]
                if not r:
                    raise ValueError("no result")
                meta = r.get("meta") or {}
                price = meta.get("regularMarketPrice")
                closes = [c for c in ((((r.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or [])
                          if c is not None]
                prev = closes[-2] if len(closes) >= 2 else meta.get("chartPreviousClose")
                chg = round((price - prev) / prev * 100, 2) if (price and prev) else None
                ma30 = round(sum(closes) / len(closes), 4) if closes else None
                dev = round((price - ma30) / ma30 * 100, 1) if (price and ma30) else None
                out[sym] = {"price": price, "chg": chg, "ma30": ma30, "dev": dev}
                break
            except Exception as e:
                if backoff:
                    await asyncio.sleep(backoff)
                else:
                    log.warning(f"finance {sym} fetch failed: {e}")
        await asyncio.sleep(0.3)
    log.info(f"FINANCE: fetched {len(out)}/{len(FIN_TICKERS)} tickers")
    return out


def update_daily_metrics(score: dict, pizza_index, defcon_level, firms: dict,
                         aviation: dict | None, wiki_score, nuclear_seismic: dict | None,
                         regions: list[dict], finance: dict | None = None,
                         fred: dict | None = None) -> None:
    """把所有伺服器端指標每日封存一筆到 metrics_daily.json（台北日期為 key、
    當日最後一次執行覆蓋、保留 ~2 年）。供未來繪製各指標長期趨勢圖。
    含經濟避險指標（金/油/瑞郎/VIX/小麥＋國防股，伺服器端抓 Yahoo）；
    末日時鐘為靜態值故不封存。"""
    from datetime import timedelta
    store = {}
    try:
        store = json.loads(METRICS_DAILY_FILE.read_text(encoding="utf-8")).get("days") or {}
    except Exception:
        store = {}
    # 防呆：若歷史檔一時讀不到，至少沿用上一份 data.json 內嵌的封存
    if not store:
        try:
            store = (json.loads(DATA_FILE.read_text(encoding="utf-8"))
                     .get("metrics_daily") or {}).get("days") or {}
        except Exception:
            store = {}

    tp = (datetime.now(timezone.utc) + timedelta(hours=8)).date().isoformat()
    s = (aviation or {}).get("summary") or {}
    rec = {
        "combined": score.get("combined_score"),
        "poly":     score.get("polymarket_score"),
        "level":    score.get("alert_level"),
        "pizza":    pizza_index,
        "defcon":   defcon_level,
        "wiki":     wiki_score,
        "firms":    (firms or {}).get("total_24h"),
        "avi_total": s.get("total"),
        "avi_tank":  s.get("tankers"),
        "avi_awacs": s.get("awacs"),
        "avi_uav":   s.get("uav"),
        "avi_c4isr": s.get("c4isr"),
        "seismic":  (nuclear_seismic or {}).get("total"),
        "regions":  {r["key"]: round(r.get("score", 0)) for r in (regions or [])},
    }
    # 經濟避險指標（僅存價格，供長期趨勢；油價戰爭溢價＝布油現價−30日均）
    f = finance or {}
    def _px(sym): return (f.get(sym) or {}).get("price")
    def _dev(sym): return (f.get(sym) or {}).get("dev")   # 相對 30MA 偏離%
    oil = _px("BZ=F"); oil_ma = (f.get("BZ=F") or {}).get("ma30")
    fin_rec = {
        "gold":   _px("GC=F"),
        "oil":    oil,
        "usdchf": _px("USDCHF=X"),
        "vix":    _px("^VIX"),
        "wheat":  _px("ZW=F"),
        "oil_premium": (round(oil - oil_ma, 2) if (oil and oil_ma) else None),
        "lmt": _px("LMT"), "rtx": _px("RTX"), "noc": _px("NOC"), "gd": _px("GD"),
        "ust10": _px("^TNX"), "ust5": _px("^FVX"), "ust30": _px("^TYX"),
    }
    # 信用利差（FRED；未設 key 時為 None）
    fr = fred or {}
    fin_rec["em_oas"] = fr.get("em_oas")
    fin_rec["hy_oas"] = fr.get("hy_oas")
    # 「避險群聚」訊號：同時往避險方向明顯偏離 30MA 的指標數（單一指標沒意義、群聚才有）
    THRESH = 5.0   # 偏離 30MA 逾 5% 才算明顯
    cluster = 0
    if (_dev("GC=F") or 0) >= THRESH:  cluster += 1   # 金 ↑
    if (_dev("BZ=F") or 0) >= THRESH:  cluster += 1   # 油 ↑
    if (_dev("^VIX") or 0) >= THRESH:  cluster += 1   # VIX ↑
    if (_dev("USDCHF=X") or 0) >= THRESH: cluster += 1  # 瑞郎走強（USDCHF ↑ 代表美元強；避險時瑞郎/美元皆可能強）
    for stk in ("LMT", "RTX", "NOC", "GD"):
        if (_dev(stk) or 0) >= THRESH: cluster += 1; break   # 國防股整體 ↑（四檔任一達標算一票）
    if (_dev("^TNX") or 0) <= -THRESH: cluster += 1   # 殖利率 ↓（資金逃向安全資產）
    fin_rec["risk_off_cluster"] = cluster              # 0–6，越高代表避險訊號越群聚
    rec["fin"] = fin_rec
    store[tp] = rec  # 當日最後一次執行覆蓋
    # 保留約 2 年
    cutoff = (datetime.now(timezone.utc) + timedelta(hours=8) - timedelta(days=730)).date().isoformat()
    store = {d: v for d, v in store.items() if d >= cutoff}
    try:
        METRICS_DAILY_FILE.write_text(json.dumps({"days": store}, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log.warning(f"metrics_daily write error: {e}")
    return store


def compute_avi_trends(history: list[dict]) -> dict | None:
    """
    由 history 計算軍機三機型（加油機/預警機/偵察無人機）相對過去 24h/7d/30d
    平均的變化%。資料不足時回傳 None（前端顯示「累積中」）。
    """
    from datetime import timedelta
    pts = []
    for h in history:
        avi = h.get("avi")
        if not avi:
            continue
        try:
            pts.append((datetime.fromisoformat(h["ts"]), avi))
        except Exception:
            continue
    if not pts:
        return None
    now, cur = pts[-1][0], pts[-1][1]
    past = pts[:-1]  # 排除當前點

    def pct(days, key, min_pts):
        cutoff = now - timedelta(days=days)
        vals = [a.get(key, 0) for (t, a) in past if t >= cutoff]
        if len(vals) < min_pts:
            return None
        avg = sum(vals) / len(vals)
        if avg <= 0:
            return None
        return round((cur.get(key, 0) - avg) / avg * 100)

    out = {}
    for name, key in (("tankers", "t"), ("awacs", "a"), ("uav", "u"), ("c4isr", "c")):
        out[name] = {
            "d1":  pct(1,  key, 3),    # 24h：至少 3 點
            "d7":  pct(7,  key, 12),   # 7天：至少 12 點
            "d30": pct(30, key, 24),   # 30天：至少 24 點
        }
    return out


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
        firms_task    = asyncio.create_task(fetch_firms(session))
        eonet_task    = asyncio.create_task(fetch_eonet(session))
        gdelt_task    = asyncio.create_task(fetch_gdelt(session))
        news_task     = asyncio.create_task(fetch_gnews(session))
        food_task     = asyncio.create_task(fetch_food_imports(session))
        usda_task     = asyncio.create_task(fetch_usda_esr(session))
        seismic_task  = asyncio.create_task(fetch_nuclear_seismic(session))
        wiki_task     = asyncio.create_task(fetch_wikipedia_anxiety(session))
        notam_task    = asyncio.create_task(fetch_notams(session))
        bars_task     = asyncio.create_task(fetch_bars(session))
        (pizzint_data, polymarket, aviation, firms, eonet,
         gdelt, news, nuclear_seismic, wikipedia, notams, bars) = await asyncio.gather(
            pizzint_task, poly_task, aviation_task, firms_task, eonet_task,
            gdelt_task, news_task, seismic_task, wiki_task, notam_task, bars_task
        )
        food = await food_task
        usda = await usda_task
        try:
            food_hist = await fetch_food_history(session)
        except Exception as e:
            log.warning(f"food history skipped: {e}")
            food_hist = []
        try:
            strat = await fetch_strategic_imports(session)
        except Exception as e:
            log.warning(f"strategic imports skipped: {e}")
            strat = {}
        try:
            strat_hist = await fetch_strategic_history(session)
        except Exception as e:
            log.warning(f"strategic history skipped: {e}")
            strat_hist = []
        try:
            tw_news = await fetch_tw_military_news(session)
        except Exception as e:
            log.warning(f"tw military news skipped: {e}")
            tw_news = []
        try:
            pla = await fetch_pla_sorties(session)
        except Exception as e:
            log.warning(f"pla history skipped: {e}")
            pla = {}
        try:
            finance = await fetch_finance(session)
        except Exception as e:
            log.warning(f"finance skipped: {e}")
            finance = {}
        try:
            fred = await fetch_fred(session)
        except Exception as e:
            log.warning(f"fred skipped: {e}")
            fred = {}

    pizza_shops  = transform_pizza_shops(pizzint_data)
    pizza_index  = pizzint_data.get("overall_index", 0)
    defcon_level = pizzint_data.get("defcon_level")
    score        = calculate_score(pizza_index, polymarket)

    # 前一份 data.json 的警戒等級 + 推播狀態（供 alerts.py 判斷升級/去重）
    prev_level = "NORMAL"
    prev_notify = {}
    try:
        _prev = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        prev_level = _prev["score"]["alert_level"]
        prev_notify = _prev.get("_notify") or {}
    except Exception:
        pass

    # FIRMS 抓取失敗時沿用上一輪（全球 24h 火點數不可能真的為 0）
    if not firms.get("total_24h"):
        try:
            prev_firms = json.loads(DATA_FILE.read_text(encoding="utf-8")).get("firms") or {}
            if prev_firms.get("total_24h"):
                firms = {**prev_firms, "stale": True}
                log.warning("FIRMS unavailable, carried over previous data")
        except Exception:
            pass

    regions = build_region_risks(polymarket, gdelt, firms, aviation, notams)
    history = update_history(score, pizza_index, regions,
                             (wikipedia or {}).get("score"), aviation)
    # 軍機機型 24h/7d/30d 歷史變化（資料累積後自動填入）
    if isinstance(aviation, dict):
        aviation["trends"] = compute_avi_trends(history)
    # 全指標每日長期封存（每日一筆、保留 ~2 年）
    metrics_daily = update_daily_metrics(
        score, pizza_index, defcon_level, firms, aviation,
        (wikipedia or {}).get("score"), nuclear_seismic, regions, finance, fred)

    output = {
        "updated_at":    datetime.now(timezone.utc).isoformat(),
        "score":         score,
        "pizza":         pizza_shops,
        "pizza_index":   pizza_index,
        "pizza_events":  pizzint_data.get("events") or [],
        "defcon_level":  defcon_level,
        "defcon_details": pizzint_data.get("defcon_details"),
        "polymarket":    polymarket[:20],
        "aviation":      aviation,
        "firms":         firms,
        "eonet":         eonet[:20],
        "gdelt":         gdelt,
        "news":          news,
        "food":          food,
        "food_hist":     food_hist,
        "strat":         strat,
        "strat_hist":    strat_hist,
        "tw_news":       tw_news,
        "pla":           pla,
        "usda":          usda,
        "wikipedia":     wikipedia,
        "notams":        notams,
        "nuclear_seismic": nuclear_seismic,
        "bars":          bars,
        "regions":       regions,
        "sources": {
            "pizza":      "https://www.pizzint.watch/",
            "polymarket": "https://gamma-api.polymarket.com/",
            "aviation":   "https://api.adsb.lol/v2/mil",
            "firms":      "https://firms.modaps.eosdis.nasa.gov/",
            "eonet":      "https://eonet.gsfc.nasa.gov/",
            "gdelt":      "https://www.gdeltproject.org/",
            "food":       "https://comtradeapi.un.org/",
            "usgs":       "https://earthquake.usgs.gov/",
            "bars":       "https://besttime.app/",
            "wikipedia":  "https://wikimedia.org/api/rest_v1/",
            "notam":      "https://notams.aim.faa.gov/",
        },
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 推播：每小時定時回報 + 即時異常（未設定 Secrets 則自動跳過）；狀態寫回 _notify
    try:
        from alerts import run_notifications
        import os as _os
        force_test = (_os.environ.get("TEST_PUSH", "").strip().lower()
                      in ("1", "true", "yes", "on"))
        output["_notify"] = await run_notifications(
            output, prev_notify, prev_level, force_test=force_test)
    except Exception as e:
        log.warning(f"notify skipped: {e}")

    DATA_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    open_count = sum(1 for s in pizza_shops if s["is_open"])
    log.info(f"Wrote {DATA_FILE.name} - "
             f"pizza_index={pizza_index}, defcon={defcon_level}, "
             f"open_shops={open_count}/{len(pizza_shops)}, "
             f"combined={score['combined_score']} [{score['alert_level']}]")


if __name__ == "__main__":
    asyncio.run(main())
