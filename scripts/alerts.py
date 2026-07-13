"""
WARHUBS - 推播通知系統
透過 Telegram Bot（與 Discord Webhook）推送：
  1) 每小時定時戰情回報（可用 DIGEST_EVERY_HOURS 調整間隔）
  2) 即時異常警報（等級升高／五角大廈披薩爆量／衝突火點激增）
由 fetch_data.py 在每次資料更新後呼叫。跨 run 的狀態（上次回報時段、
上次異常旗標）存在 data.json 的 "_notify" 欄位，由呼叫端讀出上一份傳入、
再把新狀態寫回，因為 GitHub Actions 每次都是全新 process。
"""

import asyncio
import aiohttp
import os
from datetime import datetime, timezone


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
DISCORD_WEBHOOK    = os.environ.get("DISCORD_WEBHOOK_URL", "")

# ── 可由 GitHub Variables 覆寫的設定（未設定則用預設）────────────
def _int(name, default):
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default

def _on(name, default=True):
    v = os.environ.get(name, "")
    if v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")

DIGEST_EVERY_HOURS  = max(1, _int("DIGEST_EVERY_HOURS", 1))   # 定時回報間隔（小時）
ALERT_ESCALATION    = _on("ALERT_ESCALATION", True)          # 等級升高
ALERT_PIZZA         = _on("ALERT_PIZZA", True)               # 披薩爆量
ALERT_HOTSPOT       = _on("ALERT_HOTSPOT", True)             # 火點激增
HOTSPOT_SURGE_RATIO = float(os.environ.get("HOTSPOT_SURGE_RATIO", "") or 1.4)
HOTSPOT_SURGE_MIN   = _int("HOTSPOT_SURGE_MIN", 12)          # 至少幾處才視為激增

LEVEL_EMOJI = {"NORMAL": "🟢", "ELEVATED": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}
LEVEL_ORDER = ["NORMAL", "ELEVATED", "HIGH", "CRITICAL"]
SITE = "https://warhubs.com"


# ─── 訊息組裝 ──────────────────────────────────────────────
def _fmt_regions(regions):
    lines = []
    for r in sorted(regions or [], key=lambda x: x.get("score", 0), reverse=True)[:5]:
        e = LEVEL_EMOJI.get(r.get("level"), "⚪")
        lines.append(f"  {e} {r.get('name','?')}  {round(r.get('score',0))}  ({r.get('level','')})")
    return "\n".join(lines) or "  （無資料）"

def _fmt_news(news, n=3):
    lines = []
    for a in (news or [])[:n]:
        lines.append(f"  • [{a.get('topic','')}] {a.get('title','')[:60]}")
    return "\n".join(lines) or "  （無即時頭條）"


def build_digest(data: dict) -> str:
    score = data.get("score", {})
    emoji = LEVEL_EMOJI.get(score.get("alert_level"), "⚠️")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    firms = data.get("firms", {})
    hs = len((firms.get("conflict_hotspots") or []))
    return (
        f"🛰️ *WARHUBS 每小時戰情回報*\n"
        f"{now}\n\n"
        f"{emoji} *綜合威脅指數：{score.get('combined_score',0):.1f} / 100*　等級：*{score.get('alert_level','?')}*\n\n"
        f"🗺️ 地區風險：\n{_fmt_regions(data.get('regions'))}\n\n"
        f"🍕 五角大廈披薩指數：{score.get('pizza_score',0):.1f}　·　DEFCON {data.get('defcon_level','—')}\n"
        f"🔥 衝突火點：{hs} 處（NASA FIRMS 24h）\n\n"
        f"📡 最新戰情頭條：\n{_fmt_news(data.get('news'))}\n\n"
        f"🔗 {SITE}"
    ).strip()


def build_escalation(data: dict, old_level: str) -> str:
    score = data.get("score", {})
    new_level = score.get("alert_level")
    e = LEVEL_EMOJI.get(new_level, "⚠️")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"{e} *WARHUBS 戰情警報：等級升高* {e}\n"
        f"{now}\n\n"
        f"⚠️ 等級 *{old_level} → {new_level}*\n"
        f"🎯 綜合威脅指數：*{score.get('combined_score',0):.1f} / 100*\n\n"
        f"🗺️ 地區風險：\n{_fmt_regions(data.get('regions'))}\n\n"
        f"📡 最新頭條：\n{_fmt_news(data.get('news'))}\n\n"
        f"🔗 {SITE}"
    ).strip()


def build_pizza_alert(data: dict, shops: list) -> str:
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    names = "、".join(s.get("name", "?") for s in shops[:4]) or "多家"
    top = max(shops, key=lambda s: s.get("percentage_of_usual") or 0)
    pct = round(top.get("percentage_of_usual") or 0)
    return (
        f"🍕 *WARHUBS 異常：五角大廈披薩爆量*\n"
        f"{now}\n\n"
        f"Pentagon 周邊披薩店下班後仍爆滿（EXTREME）：{names}\n"
        f"最高達平時 *{pct}%*　·　DEFCON {data.get('defcon_level','—')}\n\n"
        f"（歷史上美軍重大夜間行動前常見的領先指標）\n"
        f"🔗 {SITE}"
    ).strip()


def build_hotspot_alert(data: dict, now_cnt: int, prev_cnt: int) -> str:
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    return (
        f"🔥 *WARHUBS 異常：衝突火點激增*\n"
        f"{now}\n\n"
        f"NASA FIRMS 監測區衝突火點：*{prev_cnt} → {now_cnt} 處*\n\n"
        f"🗺️ 地區風險：\n{_fmt_regions(data.get('regions'))}\n\n"
        f"🔗 {SITE}"
    ).strip()


# ─── 發送 ──────────────────────────────────────────────────
async def send_telegram(session, text):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text,
               "parse_mode": "Markdown", "disable_web_page_preview": True}
    async with session.post(url, json=payload) as resp:
        if resp.status == 200:
            print("✅ Telegram 推播成功")
        else:
            print(f"❌ Telegram 失敗: {await resp.text()}")


async def send_discord(session, text, level="NORMAL"):
    if not DISCORD_WEBHOOK:
        return
    color = {"NORMAL": 0x00ff88, "ELEVATED": 0xffaa00,
             "HIGH": 0xff6600, "CRITICAL": 0xff0000}.get(level, 0x00cfe8)
    payload = {"embeds": [{
        "description": text, "color": color,
        "footer": {"text": "WARHUBS 戰爭預測情報中心"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }]}
    async with session.post(DISCORD_WEBHOOK, json=payload) as resp:
        if resp.status in (200, 204):
            print("✅ Discord 推播成功")
        else:
            print(f"❌ Discord 失敗: {await resp.text()}")


async def _send_all(messages, level="NORMAL"):
    if not messages:
        return
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID) and not DISCORD_WEBHOOK:
        print("ℹ️ 未設定推播 Secrets，跳過推播")
        return
    async with aiohttp.ClientSession() as session:
        for msg in messages:
            print(f"\n{'='*40}\n{msg}\n{'='*40}")
            await asyncio.gather(
                send_telegram(session, msg),
                send_discord(session, msg, level),
            )


# ─── 主流程：定時回報 + 即時異常 ─────────────────────────────
async def run_notifications(data: dict, prev_notify: dict | None = None,
                            prev_level: str = "NORMAL", force_test: bool = False):
    """
    回傳新的 _notify 狀態（供呼叫端寫回 data.json）。
    force_test=True 時無視所有條件，直接送一則測試 digest 驗證連線。
    """
    prev_notify = prev_notify or {}
    score = data.get("score", {})
    new_level = score.get("alert_level", "NORMAL")

    now = datetime.now(timezone.utc)
    bucket = int(now.timestamp() // 3600) // DIGEST_EVERY_HOURS

    firms = data.get("firms", {})
    hs_cnt = len(firms.get("conflict_hotspots") or [])
    extreme_shops = [s for s in (data.get("pizza") or [])
                     if (s.get("spike_magnitude") or "").upper() == "EXTREME"]
    has_extreme = len(extreme_shops) > 0

    new_notify = {"bucket": bucket, "level": new_level,
                  "pizza_extreme": has_extreme, "hotspots": hs_cnt}

    # 測試：直接送一則，確認連線
    if force_test:
        await _send_all(["🔔 *WARHUBS 推播測試*\nTelegram／Discord 連線正常，"
                         "之後定時回報與異常警報都會送到這裡。\n\n" + build_digest(data)],
                        new_level)
        return new_notify

    msgs, alert_msgs = [], []

    # 1) 定時回報：時段跳動才送（抗排程抖動、不重複）
    if prev_notify.get("bucket") != bucket:
        msgs.append(build_digest(data))

    # 2) 即時異常（邊緣觸發：條件「新成立」才推，避免洗版）
    if ALERT_ESCALATION and new_level in LEVEL_ORDER and prev_level in LEVEL_ORDER \
            and LEVEL_ORDER.index(new_level) > LEVEL_ORDER.index(prev_level):
        alert_msgs.append(build_escalation(data, prev_level))

    if ALERT_PIZZA and has_extreme and not prev_notify.get("pizza_extreme"):
        alert_msgs.append(build_pizza_alert(data, extreme_shops))

    prev_hs = prev_notify.get("hotspots", 0) or 0
    if ALERT_HOTSPOT and hs_cnt >= HOTSPOT_SURGE_MIN and prev_hs > 0 \
            and hs_cnt >= prev_hs * HOTSPOT_SURGE_RATIO:
        alert_msgs.append(build_hotspot_alert(data, hs_cnt, prev_hs))

    await _send_all(alert_msgs + msgs, new_level)
    return new_notify
