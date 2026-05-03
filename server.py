"""
ConflictWatch - FastAPI 後端伺服器
提供 REST API 給前端讀取即時數據
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import sqlite3
import json
import asyncio
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path

from fetcher import run as fetch_all
from alerts import maybe_alert

# ─── 週期性任務 ───────────────────────────────
async def scheduled_fetch():
    """每 15 分鐘自動抓取一次"""
    while True:
        try:
            result = await fetch_all()
            await maybe_alert(result["score"], result["pizza"], result["polymarket"])
        except Exception as e:
            print(f"排程抓取錯誤: {e}")
        await asyncio.sleep(15 * 60)  # 15 分鐘


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 啟動時立即抓一次 + 啟動排程
    asyncio.create_task(fetch_all())
    asyncio.create_task(scheduled_fetch())
    yield


# ─── App ──────────────────────────────────────
app = FastAPI(title="ConflictWatch API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

DB_PATH = "conflictwatch.db"


def get_conn():
    return sqlite3.connect(DB_PATH)


# ─── Endpoints ────────────────────────────────

@app.get("/api/latest")
def get_latest():
    """最新一筆綜合指數 + 數據"""
    conn = get_conn()
    c = conn.cursor()

    # 最新綜合分數
    c.execute("SELECT * FROM combined_score ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    if not row:
        raise HTTPException(404, "尚無數據")

    score = {
        "calculated_at":   row[1],
        "pizza_score":     row[2],
        "polymarket_score": row[3],
        "combined_score":  row[4],
        "alert_level":     row[5],
    }

    # 最新披薩數據
    c.execute("SELECT shop_name, busyness_pct, is_anomaly FROM pizza_snapshots ORDER BY id DESC LIMIT 10")
    pizza = [{"shop": r[0], "busyness": r[1], "anomaly": bool(r[2])} for r in c.fetchall()]

    # 最新 Polymarket Top 10（按 volume）
    c.execute("""
        SELECT question, yes_price, volume, category
        FROM polymarket_snapshots
        ORDER BY volume DESC
        LIMIT 10
    """)
    poly = [
        {"question": r[0], "yes_pct": round((r[1] or 0) * 100, 1), "volume": r[2], "category": r[3]}
        for r in c.fetchall()
    ]

    conn.close()
    return {"score": score, "pizza": pizza, "polymarket": poly}


@app.get("/api/history")
def get_history(days: int = 7):
    """歷史趨勢（最近 N 天的綜合指數）"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT calculated_at, combined_score, alert_level
        FROM combined_score
        ORDER BY id DESC
        LIMIT ?
    """, (days * 96,))  # 每15分鐘一筆，96筆/天
    rows = c.fetchall()
    conn.close()
    return [{"time": r[0], "score": r[1], "level": r[2]} for r in reversed(rows)]


@app.get("/api/polymarket/top")
def get_top_markets(limit: int = 20):
    """Polymarket 前 N 個戰爭相關市場（按成交量）"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT DISTINCT question, yes_price, volume, category
        FROM polymarket_snapshots
        GROUP BY question
        ORDER BY MAX(volume) DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return [
        {"question": r[0], "yes_pct": round((r[1] or 0)*100, 1), "volume": r[2], "category": r[3]}
        for r in rows
    ]


@app.get("/api/pizza/history")
def get_pizza_history(shop_name: str = "", limit: int = 100):
    """指定披薩店的歷史繁忙度趨勢"""
    conn = get_conn()
    c = conn.cursor()
    if shop_name:
        c.execute("""
            SELECT fetched_at, shop_name, busyness_pct, is_anomaly
            FROM pizza_snapshots WHERE shop_name LIKE ? ORDER BY id DESC LIMIT ?
        """, (f"%{shop_name}%", limit))
    else:
        c.execute("""
            SELECT fetched_at, shop_name, busyness_pct, is_anomaly
            FROM pizza_snapshots ORDER BY id DESC LIMIT ?
        """, (limit,))
    rows = c.fetchall()
    conn.close()
    return [{"time": r[0], "shop": r[1], "busyness": r[2], "anomaly": bool(r[3])} for r in rows]


@app.post("/api/refresh")
async def manual_refresh():
    """手動觸發數據刷新（可加 API Key 保護）"""
    result = await fetch_all()
    return {"status": "ok", "score": result["score"]}


# 靜態前端
if Path("public").exists():
    app.mount("/", StaticFiles(directory="public", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
