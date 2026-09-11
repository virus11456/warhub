"""
WARHUBS - 推播通知系統
透過 Telegram Bot（與 Discord Webhook）推送：
  1) 每小時定時戰情回報（可用 DIGEST_EVERY_HOURS 調整間隔）
  2) 即時異常警報（等級升高／五角大廈披薩爆量／監測區熱異常像元激增）
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
# 公開頻道（任何人可免費加入收通知）；bot 須為該頻道管理員
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID") or "@warhubss"
# 公開頻道推播範圍：all＝定時摘要＋異常警報（頻道有規律內容不會像死掉）；alerts＝只推異常
TELEGRAM_CHANNEL_SCOPE = (os.environ.get("TELEGRAM_CHANNEL_SCOPE") or "all").strip().lower()

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
LEVEL_ORDER = ["LOW", "MODERATE", "ELEVATED", "HIGH", "CRITICAL"]
SITE = "https://warhubs.com"


# ─── 訊息組裝 ──────────────────────────────────────────────
def _fmt_score(value):
    return "資料不足" if value is None else f"{value:.1f}"

def _fmt_regions(regions):
    lines = []
    for r in sorted(regions or [], key=lambda x: x.get("score") if x.get("score") is not None else -1, reverse=True)[:5]:
        e = LEVEL_EMOJI.get(r.get("level"), "⚪")
        lines.append(f"  {e} {r.get('name','?')}  {_fmt_score(r.get('score'))}  ({r.get('level','')})")
    return "\n".join(lines) or "  （無資料）"

def _fmt_news(news, n=3):
    lines = []
    for a in (news or [])[:n]:
        lines.append(f"  • [{a.get('topic','')}] {a.get('title','')[:60]}")
    return "\n".join(lines) or "  （無即時頭條）"


def _fmt_aviation(aviation):
    """全球軍機動態摘要（無人機優先，附加油機/預警機/偵察機）。"""
    if not aviation or aviation.get("error"):
        return "✈️ 全球軍機：資料不可用"
    s = aviation.get("summary") or {}
    return (f"✈️ 全球軍機：無人機 {s.get('uav',0)}・加油機 {s.get('tankers',0)}"
            f"・預警機 {s.get('awacs',0)}・偵察機 {s.get('c4isr',0)}（共 {s.get('total',0)} 架）")


def _fmt_pizza_shops(shops):
    """目前『超標』的披薩店（status=spike 爆量 / busy 偏忙），列出店名與忙碌度。"""
    hot = [s for s in (shops or []) if s.get("status") in ("spike", "busy")]
    if not hot:
        opn = sum(1 for s in (shops or []) if s.get("is_open"))
        return f"   （目前無店家爆量／異常忙碌；{opn}/{len(shops or [])} 家營業中）"
    hot.sort(key=lambda s: (s.get("busyness") or 0), reverse=True)
    lines = []
    for s in hot[:6]:
        p = s.get("percentage_of_usual")
        tag = "🔴爆量" if s.get("status") == "spike" else "🟠偏忙"
        extra = f"（達平時 {round(p)}%）" if p is not None else ""
        lines.append(f"   {tag} {s.get('name','?')}　忙碌度 {s.get('busyness',0)}%{extra}")
    return "\n".join(lines)


def build_digest(data: dict) -> str:
    score = data.get("score", {})
    emoji = LEVEL_EMOJI.get(score.get("alert_level"), "⚠️")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    firms = data.get("firms", {})
    hs = firms.get("conflict_total")
    hs = "資料不足" if hs is None or firms.get("stale") else hs
    return (
        f"🛰️ *WARHUBS 定時觀測回報*\n"
        f"{now}\n\n"
        f"{emoji} *WPI 觀察指數：{_fmt_score(score.get('combined_score'))} / 100*　等級：*{score.get('alert_level','?')}*\n\n"
        f"🗺️ 地區風險：\n{_fmt_regions(data.get('regions'))}\n\n"
        f"🍕 五角大廈披薩指數：{_fmt_score(score.get('pizza_score'))}　·　DEFCON {data.get('defcon_level','—')}\n"
        f"{_fmt_pizza_shops(data.get('pizza'))}\n"
        f"{_fmt_aviation(data.get('aviation'))}\n"
        f"🔥 監測區熱異常像元：{hs} 處（NASA FIRMS 24h）\n\n"
        f"📡 最新戰情頭條：\n{_fmt_news(data.get('news'))}\n\n"
        f"資料覆盖率：{(data.get('score',{}).get('coverage',0)*100):.0f}% · 未校準為開戰機率\n"
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
        f"🎯 WPI 觀察指數：*{_fmt_score(score.get('combined_score'))} / 100*\n\n"
        f"🗺️ 地區風險：\n{_fmt_regions(data.get('regions'))}\n\n"
        f"📡 最新頭條：\n{_fmt_news(data.get('news'))}\n\n"
        f"資料覆盖率：{(data.get('score',{}).get('coverage',0)*100):.0f}% · 未校準為開戰機率\n"
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
        f"（人流異常並非軍事行動證據）\n"
        f"資料覆盖率：{(data.get('score',{}).get('coverage',0)*100):.0f}% · 未校準為開戰機率\n"
        f"🔗 {SITE}"
    ).strip()


def build_hotspot_alert(data: dict, now_cnt: int, prev_cnt: int) -> str:
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    return (
        f"🔥 *WARHUBS 異常：監測區熱異常像元激增*\n"
        f"{now}\n\n"
        f"NASA FIRMS 監測區監測區熱異常像元：*{prev_cnt} → {now_cnt} 處*\n\n"
        f"🗺️ 地區風險：\n{_fmt_regions(data.get('regions'))}\n\n"
        f"資料覆盖率：{(data.get('score',{}).get('coverage',0)*100):.0f}% · 未校準為開戰機率\n"
        f"🔗 {SITE}"
    ).strip()


# ─── 發送 ──────────────────────────────────────────────────
async def send_telegram(session, text, chat_id):
    if not (TELEGRAM_BOT_TOKEN and chat_id):
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text,
               "parse_mode": "Markdown", "disable_web_page_preview": True}
    async with session.post(url, json=payload) as resp:
        if resp.status == 200:
            print(f"✅ Telegram 推播成功 → {chat_id}")
        else:
            print(f"❌ Telegram 失敗 ({chat_id}): {await resp.text()}")


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


async def _send_all(messages, level="NORMAL", tg_chats=None):
    """把每則訊息送到指定的 Telegram 對象（可多個）＋ Discord。
    tg_chats 未給時預設只送個人 chat。"""
    if not messages:
        return
    tg_chats = [c for c in (tg_chats if tg_chats is not None else [TELEGRAM_CHAT_ID]) if c]
    # 去重（避免個人 chat 與頻道設成同一個時重複發）
    seen, uniq = set(), []
    for c in tg_chats:
        if c not in seen:
            seen.add(c); uniq.append(c)
    tg_chats = uniq
    if not (TELEGRAM_BOT_TOKEN and tg_chats) and not DISCORD_WEBHOOK:
        print("ℹ️ 未設定推播 Secrets，跳過推播")
        return
    async with aiohttp.ClientSession() as session:
        for msg in messages:
            print(f"\n{'='*40}\n{msg}\n{'='*40}")
            tasks = [send_telegram(session, msg, c) for c in tg_chats]
            tasks.append(send_discord(session, msg, level))
            await asyncio.gather(*tasks)


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
    hs_cnt = firms.get("conflict_total") if not firms.get("stale") and not firms.get("error") else None
    extreme_shops = [s for s in (data.get("pizza") or [])
                     if (s.get("spike_magnitude") or "").upper() == "EXTREME"]
    has_extreme = len(extreme_shops) > 0

    new_notify = {"bucket": bucket, "level": new_level,
                  "pizza_extreme": has_extreme, "hotspots": hs_cnt, "hotspot_counter_version": 2}

    # 收件對象：個人 chat 永遠收；公開頻道依 scope 決定
    personal = [TELEGRAM_CHAT_ID]
    both = [TELEGRAM_CHAT_ID, TELEGRAM_CHANNEL_ID]
    digest_targets = both if TELEGRAM_CHANNEL_SCOPE == "all" else personal

    # 測試：直接送一則到個人＋頻道，確認連線
    if force_test:
        await _send_all(["🔔 *WARHUBS 推播測試*\nTelegram／Discord 連線正常，"
                         "之後定時回報與異常警報都會送到這裡。\n\n" + build_digest(data)],
                        new_level, tg_chats=both)
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
    if ALERT_HOTSPOT and prev_notify.get("hotspot_counter_version") == 2 and hs_cnt is not None and hs_cnt >= HOTSPOT_SURGE_MIN and prev_hs > 0 \
            and hs_cnt >= prev_hs * HOTSPOT_SURGE_RATIO:
        alert_msgs.append(build_hotspot_alert(data, hs_cnt, prev_hs))

    # 異常警報：個人＋公開頻道都推；定時摘要：依頻道 scope
    await _send_all(alert_msgs, new_level, tg_chats=both)
    await _send_all(msgs, new_level, tg_chats=digest_targets)
    return new_notify
