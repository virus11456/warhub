"""
ConflictWatch - 推播警報系統
當指數異常時，自動推送到 Telegram Bot 和 Discord Webhook
"""

import asyncio
import aiohttp
import json
import os
from datetime import datetime, timezone


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
DISCORD_WEBHOOK    = os.environ.get("DISCORD_WEBHOOK_URL", "")

# 上次發送的等級（避免重複推播）
_last_alert_level = "NORMAL"


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

    # 披薩異常店家
    anomaly_shops = [s for s in pizza if s.get("is_anomaly")]
    pizza_line = ", ".join(s["shop_name"] for s in anomaly_shops) if anomaly_shops else "無異常"

    msg = f"""
{emoji} *ConflictWatch 警報* {emoji}
時間：{now}

🎯 *綜合威脅指數：{score['combined_score']:.1f} / 100*
等級：*{score['alert_level']}*

🍕 Pizza 指數：{score['pizza_score']:.1f}
  異常店家：{pizza_line}

📊 Polymarket 指數：{score['polymarket_score']:.1f}
{poly_lines}

🔗 https://your-conflictwatch-domain.com
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


async def maybe_alert(score: dict, pizza: list, polymarket: list):
    """如果等級升高，觸發推播"""
    global _last_alert_level
    new_level = score["alert_level"]

    if not should_alert(new_level, _last_alert_level):
        print(f"ℹ️ 等級未升高（{_last_alert_level} → {new_level}），跳過推播")
        return

    msg = build_message(score, pizza, polymarket)
    print(f"\n{'='*40}\n{msg}\n{'='*40}\n")

    async with aiohttp.ClientSession() as session:
        await asyncio.gather(
            send_telegram(session, msg),
            send_discord(session, msg, score),
        )

    _last_alert_level = new_level
