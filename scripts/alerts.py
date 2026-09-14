"""
WARHUBS - 推播通知系統
透過 Telegram Bot（與 Discord Webhook）推送：
  1) 資料更新後觀測回報（DIGEST_EVERY_HOURS 為去重時段，非獨立定時器）
  2) 監測區熱異常像元激增；實驗 WPI 與披薩不觸發戰情警報
由 fetch_data.py 在每次資料更新後呼叫。跨 run 的狀態（上次回報時段、
上次異常旗標）存在 data.json 的 "_notify" 欄位，由呼叫端讀出上一份傳入、
再把新狀態寫回，因為 GitHub Actions 每次都是全新 process。
"""

import asyncio
import math
import time
import hashlib
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

DIGEST_EVERY_HOURS  = max(1, _int("DIGEST_EVERY_HOURS", 1))   # 摘要去重時段（小時）
ALERT_ESCALATION    = _on("ALERT_ESCALATION", True)          # 等級升高
ALERT_PIZZA         = _on("ALERT_PIZZA", True)               # 披薩爆量
ALERT_HOTSPOT       = _on("ALERT_HOTSPOT", True)             # 火點激增
HOTSPOT_SURGE_RATIO = float(os.environ.get("HOTSPOT_SURGE_RATIO", "") or 1.4)
HOTSPOT_SURGE_MIN   = _int("HOTSPOT_SURGE_MIN", 12)          # 至少幾處才視為激增

LEVEL_EMOJI = {"NORMAL": "🟢", "ELEVATED": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}
LEVEL_ORDER = ["LOW", "MODERATE", "ELEVATED", "HIGH", "CRITICAL"]
SITE = "https://warhubs.com"


# ─── 訊息組裝 ──────────────────────────────────────────────
def _valid_number(value, maximum=None):
    return (type(value) in (int, float) and math.isfinite(value) and value >= 0
            and (maximum is None or value <= maximum))


def _fmt_score(value):
    return f"{value:.1f}" if _valid_number(value, 100) else "資料不足"


def _fmt_coverage(value):
    return f"{value * 100:.0f}%" if _valid_number(value, 1) else "資料不足"


def _source_problem(source, health=None):
    health = health or {}
    if source.get("error") or source.get("available") is False or health.get("status") == "unavailable":
        return "資料不可用"
    if source.get("stale") or health.get("status") == "stale":
        return "資料過期（沿用舊觀測）"
    return None


def _fmt_count(value):
    return str(int(value)) if _valid_number(value) and float(value).is_integer() else "缺資料"


def _fmt_regions(regions):
    lines = []
    for r in sorted(regions or [], key=lambda x: x.get("score") if _valid_number(x.get("score"), 100) else -1, reverse=True)[:5]:
        e = LEVEL_EMOJI.get(r.get("level"), "⚪")
        lines.append(f"  {e} {r.get('name','?')}  {_fmt_score(r.get('score'))}  ({r.get('level','')})")
    return "\n".join(lines) or "  （無資料）"

def _fmt_news(news, n=3):
    lines = []
    for a in (news or [])[:n]:
        lines.append(f"  • [{a.get('topic','')}] {a.get('title','')[:60]}")
    return "\n".join(lines) or "  （無即時頭條）"


def _fmt_aviation(aviation, health=None):
    aviation = aviation or {}
    prefix = "✈️ 目前可見軍機（ADS-B 覆蓋不完整）："
    problem = _source_problem(aviation, health)
    if problem:
        return prefix + problem
    summary = aviation.get("summary") or {}
    counts = [_fmt_count(summary.get(k)) for k in ("uav", "tankers", "awacs", "c4isr", "total")]
    partial = "；部分資料" if "缺資料" in counts or aviation.get("partial") or (health or {}).get("status") == "partial" else ""
    return (prefix + f"無人機 {counts[0]}・加油機 {counts[1]}・預警機 {counts[2]}"
            f"・偵察機 {counts[3]}（可見總數 {counts[4]} 架{partial}）")


def _fmt_pizza_shops(shops, health=None):
    shops = [shop for shop in (shops or []) if isinstance(shop, dict)]
    problem = _source_problem({}, health)
    if problem:
        return "   店家人流：" + problem
    if not shops:
        return "   店家人流：資料不足，無法判定是否異常"
    fresh = [shop for shop in shops if not _source_problem(shop)]
    live = [shop for shop in fresh if shop.get("is_open") is True
            and _valid_number(shop.get("busyness"), 100)
            and shop.get("status") in ("quiet", "normal", "busy", "spike")]
    closed = sum(shop.get("is_open") is False for shop in fresh)
    missing = len(shops) - len(live) - closed
    hot = [shop for shop in live if shop.get("status") in ("spike", "busy")]
    summary = f"   有效即時人流 {len(live)}/{len(shops)} 家；已知未營業 {closed} 家；缺值或過期 {missing} 家"
    if not hot:
        return summary + ("；有效樣本未見偏忙／爆量" if live else "；無即時人流可供判斷")
    hot.sort(key=lambda shop: shop["busyness"], reverse=True)
    lines = [summary]
    for shop in hot[:6]:
        pct = shop.get("percentage_of_usual")
        tag = "🔴爆量" if shop.get("status") == "spike" else "🟠偏忙"
        extra = f"（達平時 {round(pct)}%）" if _valid_number(pct) else "（缺平時比較值）"
        lines.append(f"   {tag} {shop.get('name','?')}　忙碌度 {shop['busyness']:g}%{extra}")
    return "\n".join(lines)


def _fmt_firms(firms, health=None):
    firms = firms or {}
    problem = _source_problem(firms, health)
    count = _fmt_count(firms.get("conflict_total"))
    value = problem or (count + " 處" if count != "缺資料" else "資料不足")
    if not problem and (firms.get("partial") or (health or {}).get("status") == "partial"):
        value += "（部分資料）"
    return "🔥 監測區熱異常像元：" + value + "（NASA FIRMS 24h；不等於戰火）"


def build_digest(data: dict) -> str:
    score = data.get("score", {})
    emoji = "🧪" if score.get("experimental", True) else LEVEL_EMOJI.get(score.get("alert_level"), "⚠️")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    health = data.get("source_health") or {}
    return (
        f"🛰️ *WARHUBS 更新觀測回報*\n"
        f"{now}\n資料時間：{data.get('updated_at') or '未提供'}\n\n"
        f"{emoji} *WPI 實驗指數：{_fmt_score(score.get('combined_score'))} / 100*（不作戰情警戒）\n\n"
        f"🗺️ 地區風險：\n{_fmt_regions(data.get('regions'))}\n\n"
        f"🍕 人流實驗觀察：{_fmt_score(score.get('pizza_score'))}\n"
        f"{_fmt_pizza_shops(data.get('pizza'), health.get('pizza'))}\n"
        f"{_fmt_aviation(data.get('aviation'), health.get('aviation'))}\n"
        f"{_fmt_firms(data.get('firms'), health.get('firms'))}\n\n"
        f"📡 最新戰情頭條：\n{_fmt_news(data.get('news'))}\n\n"
        f"資料覆蓋率：{_fmt_coverage((data.get('score') or {}).get('coverage'))} · 未校準為開戰機率\n"
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
        f"資料覆蓋率：{_fmt_coverage((data.get('score') or {}).get('coverage'))} · 未校準為開戰機率\n"
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
        f"最高達平時 *{pct}%*\n\n"
        f"（人流異常並非軍事行動證據）\n"
        f"資料覆蓋率：{_fmt_coverage((data.get('score') or {}).get('coverage'))} · 未校準為開戰機率\n"
        f"🔗 {SITE}"
    ).strip()


def build_hotspot_alert(data: dict, now_cnt: int, prev_cnt: int) -> str:
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    return (
        f"🔥 *WARHUBS 異常：監測區熱異常像元激增*\n"
        f"{now}\n\n"
        f"NASA FIRMS 監測區熱異常像元：*{prev_cnt} → {now_cnt} 處*\n\n"
        f"🗺️ 地區風險：\n{_fmt_regions(data.get('regions'))}\n\n"
        f"資料覆蓋率：{_fmt_coverage((data.get('score') or {}).get('coverage'))} · 未校準為開戰機率\n"
        f"🔗 {SITE}"
    ).strip()


# ─── 發送 ──────────────────────────────────────────────────
class TelegramPacer:
    """Shared by alerts and digest; 429 cooldown survives the next scheduled run."""
    def __init__(self, retry_at=None):
        self.retry_at = (retry_at if isinstance(retry_at, (int, float))
                         and not isinstance(retry_at, bool) and math.isfinite(retry_at)
                         and retry_at > 0 else 0)
        self.next_send = 0
        self.blocked = False

    async def acquire(self):
        if self.blocked or time.time() < self.retry_at:
            print("ℹ️ Telegram 限流等待中，本輪略過")
            return False
        # Serialize all destinations conservatively, including group chats.
        delay = self.next_send - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        self.next_send = time.monotonic() + 3.1
        return True

    def defer(self, body):
        params = body.get("parameters") if isinstance(body, dict) else None
        seconds = params.get("retry_after") if isinstance(params, dict) else None
        # A malformed 429 must also stop this batch; never retry immediately.
        if type(seconds) is not int or seconds <= 0:
            seconds = 60
        self.retry_at = max(self.retry_at, time.time() + seconds)
        self.blocked = True
        print("ℹ️ Telegram 已限流，保存等待期限供正常排程使用")


async def send_telegram(session, text, chat_id, pacer=None):
    if not (TELEGRAM_BOT_TOKEN and chat_id):
        return False
    pacer = pacer or TelegramPacer()
    if not await pacer.acquire():
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # Plain text: source titles and INSUFFICIENT_DATA must never become markup.
    payload = {"chat_id": chat_id, "text": text,
               "disable_web_page_preview": True}
    async with session.post(url, json=payload) as resp:
        try:
            body = await resp.json()
        except (ValueError, aiohttp.ClientError, TimeoutError):
            if resp.status == 429:
                pacer.defer(None)
            return False
        if resp.status == 429 or (isinstance(body, dict) and body.get("error_code") == 429):
            pacer.defer(body)
            return False
        ok = resp.status == 200 and isinstance(body, dict) and body.get("ok") is True
        print("✅ Telegram 推播成功" if ok else f"❌ Telegram 推播失敗 HTTP {resp.status}")
        return ok


async def send_discord(session, text, level="NORMAL"):
    if not DISCORD_WEBHOOK:
        return False
    color = {"NORMAL": 0x00ff88, "ELEVATED": 0xffaa00,
             "HIGH": 0xff6600, "CRITICAL": 0xff0000}.get(level, 0x00cfe8)
    payload = {"embeds": [{
        "description": text, "color": color,
        "footer": {"text": "WARHUBS 戰爭預測情報中心"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }]}
    async with session.post(DISCORD_WEBHOOK, json=payload) as resp:
        ok = resp.status in (200, 204)
        print("✅ Discord 推播成功" if ok else f"❌ Discord 推播失敗 HTTP {resp.status}")
        return ok


def _target_key(kind, target):
    # Public data must not disclose private chat IDs or webhook credentials.
    return hashlib.sha256(f"{kind}:{target}".encode()).hexdigest()


async def _send_all(messages, level="NORMAL", tg_chats=None, completed=None, pacer=None):
    """Return acknowledged results per destination; skip previously acknowledged targets."""
    if not messages:
        return {}
    pacer = pacer or TelegramPacer()
    completed = completed or {}
    chats = list(dict.fromkeys(c for c in (
        tg_chats if tg_chats is not None else [TELEGRAM_CHAT_ID]) if c))
    targets = [(_target_key("telegram", c), "telegram", c)
               for c in chats if TELEGRAM_BOT_TOKEN]
    if DISCORD_WEBHOOK:
        targets.append((_target_key("discord", DISCORD_WEBHOOK), "discord", DISCORD_WEBHOOK))
    results = {key: True for key, _, _ in targets if completed.get(key)}
    pending = [t for t in targets if not completed.get(t[0])]
    if not targets:
        print("ℹ️ 未設定推播 Secrets，跳過推播")
        return {}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        for key, kind, target in pending:
            results[key] = True
            for msg in messages:
                try:
                    ok = (await send_telegram(session, msg, target, pacer=pacer) if kind == "telegram"
                          else await send_discord(session, msg, level))
                except Exception as exc:
                    # Exception strings may contain bot tokens or webhook URLs.
                    print(f"❌ {kind} 推播例外：{type(exc).__name__}")
                    ok = False
                results[key] = results[key] and ok
    return results


# ─── 主流程：定時回報 + 即時異常 ─────────────────────────────
async def run_notifications(data: dict, prev_notify: dict | None = None,
                            prev_level: str = "NORMAL", force_test: bool = False,
                            digest_only: bool = False):
    """
    回傳新的 _notify 狀態（供呼叫端寫回 data.json）。
    force_test=True 時略過事件條件，但仍遵守 Telegram 限流。
    """
    prev_notify = prev_notify or {}
    pacer = TelegramPacer(prev_notify.get("telegram_retry_at"))
    score = data.get("score", {})
    new_level = score.get("alert_level", "NORMAL")

    now = datetime.now(timezone.utc)
    bucket = int(now.timestamp() // 3600) // DIGEST_EVERY_HOURS

    firms = data.get("firms", {})
    hs_cnt = firms.get("conflict_total") if not firms.get("stale") and not firms.get("error") else None
    extreme_shops = [s for s in (data.get("pizza") or [])
                     if (s.get("spike_magnitude") or "").upper() == "EXTREME"]
    has_extreme = len(extreme_shops) > 0

    new_notify = {"bucket": prev_notify.get("bucket"), "level": new_level,
                  "pizza_extreme": has_extreme, "hotspots": hs_cnt, "hotspot_counter_version": 2}

    new_notify["digest_snapshot_at"] = prev_notify.get("digest_snapshot_at")
    # Retain a verified success independently of later checks or failed attempts.
    from notification_status import last_success
    new_notify["digest_success_at"] = last_success(prev_notify, now)

    if digest_only:
        # A saved-snapshot digest must not consume or replay event edges.
        for key in ("level", "pizza_extreme", "hotspots", "hotspot_counter_version"):
            if key in prev_notify:
                new_notify[key] = prev_notify[key]
            else:
                new_notify.pop(key, None)

    # 收件對象：個人 chat 永遠收；公開頻道依 scope 決定
    personal = [TELEGRAM_CHAT_ID]
    both = [TELEGRAM_CHAT_ID, TELEGRAM_CHANNEL_ID]
    digest_targets = both if TELEGRAM_CHANNEL_SCOPE == "all" else personal

    # 測試：直接送一則到個人＋頻道，確認連線
    if force_test:
        result = await _send_all(["🔔 *WARHUBS 推播測試*\nTelegram／Discord 連線正常，"
                         "之後定時回報與異常警報都會送到這裡。\n\n" + build_digest(data)],
                        new_level, tg_chats=both, pacer=pacer)
        new_notify["telegram_retry_at"] = pacer.retry_at
        new_notify["delivery"] = {"test": result}
        return new_notify

    msgs, alert_msgs = [], []

    # 1) 定時回報：時段跳動才送（抗排程抖動、不重複）
    if prev_notify.get("bucket") != bucket or prev_notify.get("delivery_version") != 1:
        msgs.append(build_digest(data))

    # 2) 即時異常（邊緣觸發：條件「新成立」才推，避免洗版）
    if not digest_only and score.get("experimental") is False and ALERT_ESCALATION and new_level in LEVEL_ORDER and prev_level in LEVEL_ORDER \
            and LEVEL_ORDER.index(new_level) > LEVEL_ORDER.index(prev_level):
        alert_msgs.append(build_escalation(data, prev_level))

    if not digest_only and score.get("experimental") is False and ALERT_PIZZA and has_extreme and not prev_notify.get("pizza_extreme"):
        alert_msgs.append(build_pizza_alert(data, extreme_shops))

    prev_hs = prev_notify.get("hotspots", 0) or 0
    if not digest_only and ALERT_HOTSPOT and prev_notify.get("hotspot_counter_version") == 2 and hs_cnt is not None and hs_cnt >= HOTSPOT_SURGE_MIN and prev_hs > 0 \
            and hs_cnt >= prev_hs * HOTSPOT_SURGE_RATIO:
        alert_msgs.append(build_hotspot_alert(data, hs_cnt, prev_hs))

    # 異常警報：個人＋公開頻道都推；定時摘要：依頻道 scope
    alerts = await _send_all(alert_msgs, new_level, tg_chats=both, pacer=pacer)
    receipts = (prev_notify.get("digest_receipts", {})
                if prev_notify.get("digest_attempt_bucket") == bucket else {})
    digest = await _send_all(msgs, new_level, tg_chats=digest_targets, completed=receipts, pacer=pacer)
    if msgs:
        new_notify["digest_receipts"] = {k: True for k, ok in digest.items() if ok}
        new_notify["digest_attempt_bucket"] = bucket
        if digest and all(digest.values()):
            new_notify["bucket"] = bucket
            new_notify["digest_snapshot_at"] = data.get("updated_at")
            new_notify["digest_success_at"] = now.isoformat()
    else:
        new_notify["digest_receipts"] = receipts
        new_notify["digest_attempt_bucket"] = bucket
    new_notify["telegram_retry_at"] = pacer.retry_at
    new_notify["delivery_version"] = 1
    new_notify["delivery"] = {"checked_at": now.isoformat(), "alerts": alerts, "digest": digest}
    return new_notify
