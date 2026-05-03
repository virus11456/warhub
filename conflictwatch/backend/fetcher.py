"""
ConflictWatch - 核心數據抓取器
整合 Polymarket Gamma API + Google Maps Pizza 指數
"""

import asyncio
import aiohttp
import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger("conflictwatch")

# ─────────────────────────────────────────────
# 設定
# ─────────────────────────────────────────────
POLYMARKET_API = "https://gamma-api.polymarket.com"

# 五角大廈附近披薩店的 Google Place IDs
# 用 Google Places API 或 maps.googleapis.com/maps/api/place/search 查出
PIZZA_SHOPS = [
    {"name": "Domino's Pizza - Arlington",   "place_id": "ChIJ2Q6XXXXX"},  # 換成真實 ID
    {"name": "Papa John's - Pentagon City",  "place_id": "ChIJ3R7YYYYY"},
    {"name": "Pizza Hut - Crystal City",     "place_id": "ChIJ4S8ZZZZZ"},
    {"name": "Domino's - Alexandria",        "place_id": "ChIJ5T9AAAAA"},
]

# Polymarket 關鍵字篩選（戰爭 / 衝突相關）
WAR_KEYWORDS = [
    "war", "strike", "attack", "invasion", "conflict",
    "ceasefire", "nuclear", "missile", "troops", "military",
    "Iran", "Taiwan", "Ukraine", "Korea", "China",
    "Israel", "NATO", "NATO Article 5",
]

DB_PATH = "conflictwatch.db"


# ─────────────────────────────────────────────
# 資料庫初始化
# ─────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS polymarket_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_at  TEXT NOT NULL,
            condition_id TEXT,
            question    TEXT,
            yes_price   REAL,
            no_price    REAL,
            volume      REAL,
            category    TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS pizza_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_at  TEXT NOT NULL,
            shop_name   TEXT,
            place_id    TEXT,
            busyness_pct INTEGER,   -- 0-100，Google 的「Popular Times」百分比
            is_anomaly  INTEGER DEFAULT 0  -- 1=異常
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS combined_score (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            calculated_at   TEXT NOT NULL,
            pizza_score     REAL,   -- 0~100
            polymarket_score REAL,  -- 0~100（加權平均機率）
            combined_score  REAL,   -- 綜合威脅指數
            alert_level     TEXT    -- NORMAL / ELEVATED / HIGH / CRITICAL
        )
    """)

    conn.commit()
    conn.close()
    log.info("✅ 資料庫初始化完成")


# ─────────────────────────────────────────────
# Polymarket Gamma API
# ─────────────────────────────────────────────
async def fetch_polymarket_markets(session: aiohttp.ClientSession) -> list[dict]:
    """
    從 Polymarket Gamma API 抓取所有開放市場，
    篩選出戰爭/衝突相關的合約。
    """
    url = f"{POLYMARKET_API}/markets"
    params = {
        "limit": 200,
        "active": "true",
        "closed": "false",
        "tag_slug": "geopolitics",  # 也可以試 "politics", "global-affairs"
    }

    war_markets = []
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                log.warning(f"Polymarket API 回傳 {resp.status}")
                return []
            data = await resp.json()

        markets = data if isinstance(data, list) else data.get("data", [])
        log.info(f"抓取 {len(markets)} 個 Polymarket 市場")

        for m in markets:
            question = (m.get("question") or "").lower()
            description = (m.get("description") or "").lower()

            # 關鍵字篩選
            if any(kw.lower() in question or kw.lower() in description for kw in WAR_KEYWORDS):
                # 取得 Yes outcome 的最新價格
                outcomes = m.get("outcomes", [])
                yes_price = None
                no_price = None

                for o in outcomes:
                    name = (o.get("name") or "").lower()
                    price = float(o.get("price", 0))
                    if name == "yes":
                        yes_price = price
                    elif name == "no":
                        no_price = price

                war_markets.append({
                    "condition_id": m.get("conditionId") or m.get("id"),
                    "question":     m.get("question"),
                    "yes_price":    yes_price,
                    "no_price":     no_price,
                    "volume":       float(m.get("volume", 0) or 0),
                    "category":     m.get("category") or "geopolitics",
                    "slug":         m.get("slug"),
                    "end_date":     m.get("endDate"),
                })

        log.info(f"篩選出 {len(war_markets)} 個戰爭相關市場")

    except Exception as e:
        log.error(f"Polymarket API 錯誤: {e}")

    return war_markets


# ─────────────────────────────────────────────
# Google Maps 披薩指數
# ─────────────────────────────────────────────
async def fetch_pizza_busyness(session: aiohttp.ClientSession, google_api_key: str) -> list[dict]:
    """
    使用 Google Places API 抓取披薩店當前「live busy percentage」。
    需要 Places API (New) 的 fieldMask: currentOpeningHours.periods
    或是 Place Details (舊版) 的 current_popularity (需要非官方方式)。

    ── 官方方式 ──
    Google 的 Popular Times 並未完全開放 API。
    最可靠的做法是用 populartimes Python 套件（非官方逆向）
    或是定期截圖 Google Maps 嵌入頁面。

    以下示範兩種方法：
    1. populartimes 套件（推薦）
    2. Google Place Details（official，但無 live data）
    """
    results = []

    try:
        # ── 方法 1：populartimes 套件（pip install populartimes）──
        import populartimes  # type: ignore
        for shop in PIZZA_SHOPS:
            try:
                data = populartimes.get_id(google_api_key, shop["place_id"])
                live = data.get("current_popularity", None)  # 0-100
                name = data.get("name", shop["name"])

                if live is None:
                    live = _estimate_from_typical(data)

                is_anomaly = live is not None and live > 70  # 超過 70% 視為異常

                results.append({
                    "shop_name":    name,
                    "place_id":     shop["place_id"],
                    "busyness_pct": live or 0,
                    "is_anomaly":   int(is_anomaly),
                })
                log.info(f"🍕 {name}: {live}% {'⚠️ 異常！' if is_anomaly else ''}")

            except Exception as e:
                log.warning(f"取得 {shop['name']} 資料失敗: {e}")

    except ImportError:
        log.warning("populartimes 未安裝，使用模擬數據（開發模式）")
        results = _mock_pizza_data()

    return results


def _estimate_from_typical(data: dict) -> Optional[int]:
    """從歷史熱門時段推算當前時刻的預估值"""
    now = datetime.now()
    day = now.weekday()  # 0=週一
    hour = now.hour
    popular_times = data.get("populartimes", [])
    if len(popular_times) > day:
        day_data = popular_times[day].get("data", [])
        if len(day_data) > hour:
            return day_data[hour]
    return None


def _mock_pizza_data() -> list[dict]:
    """開發模式：模擬披薩數據"""
    import random
    base_busy = [45, 38, 72, 55]  # 模擬當前各店繁忙度
    return [
        {
            "shop_name":    shop["name"],
            "place_id":     shop["place_id"],
            "busyness_pct": base_busy[i] + random.randint(-5, 5),
            "is_anomaly":   int(base_busy[i] > 65),
        }
        for i, shop in enumerate(PIZZA_SHOPS)
    ]


# ─────────────────────────────────────────────
# 計算綜合威脅指數
# ─────────────────────────────────────────────
def calculate_combined_score(
    pizza_data: list[dict],
    poly_markets: list[dict],
) -> dict:
    """
    綜合指數公式：
    - Pizza Score (40%): 各店繁忙度的加權平均，正規化到 0-100
    - Polymarket Score (60%): 高成交量市場的 YES 機率加權平均

    分級：
    < 30   = NORMAL
    30-50  = ELEVATED
    50-70  = HIGH
    > 70   = CRITICAL
    """
    # Pizza score
    if pizza_data:
        avg_busyness = sum(s["busyness_pct"] for s in pizza_data) / len(pizza_data)
        pizza_score = min(100, avg_busyness)  # 已是 0-100
    else:
        pizza_score = 0.0

    # Polymarket score（用交易量加權）
    total_volume = sum(m["volume"] for m in poly_markets if m["yes_price"] is not None)
    if total_volume > 0 and poly_markets:
        weighted = sum(
            m["yes_price"] * m["volume"]
            for m in poly_markets
            if m["yes_price"] is not None
        )
        poly_score = (weighted / total_volume) * 100
    else:
        poly_score = 30.0  # 預設基準值

    combined = (pizza_score * 0.40) + (poly_score * 0.60)

    if combined >= 70:
        level = "CRITICAL"
    elif combined >= 50:
        level = "HIGH"
    elif combined >= 30:
        level = "ELEVATED"
    else:
        level = "NORMAL"

    return {
        "pizza_score":       round(pizza_score, 2),
        "polymarket_score":  round(poly_score, 2),
        "combined_score":    round(combined, 2),
        "alert_level":       level,
    }


# ─────────────────────────────────────────────
# 儲存到 SQLite
# ─────────────────────────────────────────────
def save_to_db(pizza_data: list, poly_markets: list, score: dict):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    for s in pizza_data:
        c.execute("""
            INSERT INTO pizza_snapshots (fetched_at, shop_name, place_id, busyness_pct, is_anomaly)
            VALUES (?, ?, ?, ?, ?)
        """, (now, s["shop_name"], s["place_id"], s["busyness_pct"], s["is_anomaly"]))

    for m in poly_markets:
        c.execute("""
            INSERT INTO polymarket_snapshots
            (fetched_at, condition_id, question, yes_price, no_price, volume, category)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (now, m["condition_id"], m["question"], m["yes_price"], m["no_price"], m["volume"], m["category"]))

    c.execute("""
        INSERT INTO combined_score
        (calculated_at, pizza_score, polymarket_score, combined_score, alert_level)
        VALUES (?, ?, ?, ?, ?)
    """, (now, score["pizza_score"], score["polymarket_score"], score["combined_score"], score["alert_level"]))

    conn.commit()
    conn.close()
    log.info(f"💾 數據已存入 DB — 綜合指數: {score['combined_score']} [{score['alert_level']}]")


# ─────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────
async def run(google_api_key: str = ""):
    init_db()
    async with aiohttp.ClientSession() as session:
        poly_task  = asyncio.create_task(fetch_polymarket_markets(session))
        pizza_task = asyncio.create_task(fetch_pizza_busyness(session, google_api_key))
        poly_markets, pizza_data = await asyncio.gather(poly_task, pizza_task)

    score = calculate_combined_score(pizza_data, poly_markets)
    save_to_db(pizza_data, poly_markets, score)

    # 輸出 JSON 供前端讀取
    output = {
        "updated_at":    datetime.now(timezone.utc).isoformat(),
        "score":         score,
        "pizza":         pizza_data,
        "polymarket":    poly_markets[:20],  # 只輸出前 20 個最相關市場
    }
    with open("public/data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    log.info(f"✅ 完成 — 數據已輸出到 public/data.json")
    return output


if __name__ == "__main__":
    import os
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    asyncio.run(run(key))
