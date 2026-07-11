"""
WarHub - 推播警報系統
當綜合指數等級升高時，自動推送到 Telegram Bot 和 Discord Webhook。
由 fetch_data.py 在每次資料更新後呼叫；上次等級由呼叫端從前一份
data.json 讀出傳入（GitHub Actions 每次都是全新 process，不能存記憶體）。
"""

import asyncio
import aiohttp
import os
from datetime import datetime, timezone


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
DISCORD_WEBHOOK    = os.environ.get("DISCORD_WEBHOOK_URL", "")


LEVEL_EMOJI = {
    "NORMAL":   "🟢",
    "ELEVATED": "🟡",
    "HIGH":     "🟠",
    "CRITICAL": "🔴",
}


def should_alert(new_level: str, old_level: str) -> bool:
    """只在等級「升高」時推播，避免垃圾訊息"""
    order = ["NORMAL", "ELEVATED", "HIGH", "CRITICAL"]
    return order.index(new_level) > order.index(old_level)


def build_message(score: dict, pizza: list, polymarket: list) -> str:
    """組裝推播訊息"""
    emoji = LEVEL_EMOJI.get(score["alert_level"], "⚠️")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # 前 3 個 Polymarket 市場
    top_markets = sorted(
        [m for m in polymarket if m.get("yes_price") is not None],
        key=lambda x: x.get("volume", 0),
        reverse=True
    )[:3]

    poly_lines = "\n".join(
        f"  • {m['question'][:55]}... → {m['yes_price']*100:.0f}%"
        for m in top_markets
    ) or "  （無資料）"

    # 披薩異常店家（spike 或繁忙度 >= 70 視為異常）
    anomaly_shops = [s for s in pizza if s.get("spike") or (s.get("busyness") or 0) >= 70]
    pizza_line = ", ".join(s["name"] for s in anomaly_shops) if anomaly_shops else "無異常"

    msg = f"""
{emoji} *ConflictWatch 警報* {emoji}
時間：{now}

🎯 *綜合威脅指數：{score['combined_score']:.1f} / 100*
等級：*{score['alert_level']}*

🍕 Pizza 指數：{score['pizza_score']:.1f}
  異常店家：{pizza_line}

📊 Polymarket 指數：{score['polymarket_score']:.1f}
{poly_lines}

🔗 https://warhubs.com
    """.strip()

    return msg


async def send_telegram(session: aiohttp.ClientSession, text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       text,
        "parse_mode": "Markdown",
    }
    async with session.post(url, json=payload) as resp:
        if resp.status == 200:
            print("✅ Telegram 推播成功")
        else:
            print(f"❌ Telegram 失敗: {await resp.text()}")


async def send_discord(session: aiohttp.ClientSession, text: str, score: dict):
    if not DISCORD_WEBHOOK:
        return

    level = score["alert_level"]
    color_map = {"NORMAL": 0x00ff88, "ELEVATED": 0xffaa00, "HIGH": 0xff6600, "CRITICAL": 0xff0000}

    payload = {
        "embeds": [{
            "title":       f"{LEVEL_EMOJI.get(level,'⚠️')} ConflictWatch Alert — {level}",
            "description": text,
            "color":       color_map.get(level, 0xffffff),
            "footer":      {"text": "ConflictWatch 戰爭預測情報中心"},
            "timestamp":   datetime.now(timezone.utc).isoformat(),
        }]
    }
    async with session.post(DISCORD_WEBHOOK, json=payload) as resp:
        if resp.status in (200, 204):
            print("✅ Discord 推播成功")
        else:
            print(f"❌ Discord 失敗: {await resp.text()}")


async def maybe_alert(score: dict, pizza: list, polymarket: list, prev_level: str = "NORMAL"):
    """如果等級較上一次資料更新時升高，觸發推播"""
    new_level = score["alert_level"]

    if new_level not in LEVEL_EMOJI or prev_level not in LEVEL_EMOJI:
        print(f"ℹ️ 未知等級（{prev_level} → {new_level}），跳過推播")
        return

    if not should_alert(new_level, prev_level):
        print(f"ℹ️ 等級未升高（{prev_level} → {new_level}），跳過推播")
        return

    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID) and not DISCORD_WEBHOOK:
        print("ℹ️ 未設定推播 Secrets，跳過推播")
        return

    msg = build_message(score, pizza, polymarket)
    print(f"\n{'='*40}\n{msg}\n{'='*40}\n")

    async with aiohttp.ClientSession() as session:
        await asyncio.gather(
            send_telegram(session, msg),
            send_discord(session, msg, score),
        )
