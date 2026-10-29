"""Pentagon-area pizza foot traffic from our own BestTime account.

Pure helpers only: the network calls live in fetch_data.fetch_pizza (live readings)
and besttime_setup.py (one-off forecasts). Nothing here spends credits.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

VENUES_FILE = Path(__file__).resolve().parent.parent / "data" / "besttime_venues.json"
ET = ZoneInfo("America/New_York")

# Display name → the venue BestTime forecasts. The address picks the branch; a forecast
# made by besttime_setup.py stores its venue_id and usual week under the display name.
PIZZA_VENUES = {
    "We, The Pizza":                     {"name": "We, The Pizza",         "address": "2100 Crystal Dr, Arlington, VA 22202"},
    "Pizzato Pizza":                     {"name": "Pizzato Pizza",         "address": "2632 N Pershing Dr, Arlington, VA 22201"},
    "Papa Johns Pizza":                  {"name": "Papa Johns Pizza",      "address": "1014 S Glebe Rd, Arlington, VA 22204"},
    "Domino's Pizza (Pentagon Closest)": {"name": "Domino's Pizza",        "address": "2602 Columbia Pike, Arlington, VA 22204"},
    "Extreme Pizza":                     {"name": "Extreme Pizza",         "address": "1419 S Fern St, Arlington, VA 22202"},
    "District Pizza Palace":             {"name": "District Pizza Palace", "address": "2325 S Eads St, Arlington, VA 22202"},
}

# A shop is "busy" or a "spike" only when it is both relatively and absolutely above its usual hour,
# so a quiet shop going from 5 to 10 does not read as a 200% surge.
BUSY_RATIO, BUSY_GAP = 150, 20
SPIKE_RATIO, SPIKE_GAP = 200, 30
EXTREME_RATIO, EXTREME_GAP = 250, 40
QUIET_RATIO = 60  # below 60% of the usual hour reads as quieter than usual


def popularity(value):
    """0-100 integer; None for missing, non-numeric or out of range (0 is a valid empty shop)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(round(value)) if 0 <= value <= 100 else None


def load_venues(path=None) -> dict:
    try:
        data = json.loads(Path(path or VENUES_FILE).read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def usual_week_from_besttime(week_raw) -> dict | None:
    """
    BestTime week_raw2 → {'0'(Sunday)…'6': 24 slots indexed by local clock hour}.
    BestTime days are Monday=0 and run 6 AM–5 AM, so slots 18–23 belong to the next calendar day.
    """
    usual = {}
    for day in week_raw or []:
        d, raw = (day.get("day_int"), day.get("day_raw")) if isinstance(day, dict) else (None, None)
        if not isinstance(d, int) or isinstance(d, bool) or not 0 <= d <= 6 or not isinstance(raw, list) or len(raw) != 24:
            continue
        sunday_based = (d + 1) % 7
        for i, value in enumerate(raw):
            key = str(sunday_based if i < 18 else (sunday_based + 1) % 7)
            usual.setdefault(key, [None] * 24)[(6 + i) % 24] = popularity(value)
    usual = {k: v for k, v in usual.items() if any(x is not None for x in v)}
    return usual or None


def usual_at(usual_week, when: datetime):
    local = when.astimezone(ET)
    day = (usual_week or {}).get(str((local.weekday() + 1) % 7))
    return day[local.hour] if isinstance(day, list) and len(day) == 24 else None


def shop_status(live, usual):
    """(status, percentage_of_usual, spike_magnitude) for an open shop with a live reading."""
    pct = round(live / usual * 100) if usual else None
    gap = live - usual if usual is not None else None
    if pct is not None and pct >= SPIKE_RATIO and gap >= SPIKE_GAP:
        return "spike", pct, ("EXTREME" if pct >= EXTREME_RATIO and gap >= EXTREME_GAP else "HIGH")
    if pct is not None and pct >= BUSY_RATIO and gap >= BUSY_GAP:
        return "busy", pct, None
    return ("quiet" if pct is not None and pct < QUIET_RATIO else "normal"), pct, None


BACKUP_MAX_AGE = timedelta(minutes=90)  # a backup live reading older than this is not "now"


def backup_shops(payload) -> dict:
    """Backup public popular-times feed → {display name: {usual_week, live, recorded_at}}.

    Used only where our own BestTime data is missing; the page never names the provider.
    Its baseline_popular_times keys are '0'(Sunday)…'6' with {hour, popularity} rows (local hour).
    """
    out = {}
    for src in (payload or {}).get("data") or []:
        if not isinstance(src, dict) or src.get("name") not in PIZZA_VENUES:
            continue
        usual = {}
        for day, rows in (src.get("baseline_popular_times") or {}).items():
            if str(day) not in {"0", "1", "2", "3", "4", "5", "6"} or not isinstance(rows, list):
                continue
            hours = [None] * 24
            for row in rows:
                hour = row.get("hour") if isinstance(row, dict) else None
                if isinstance(hour, int) and not isinstance(hour, bool) and 0 <= hour <= 23:
                    hours[hour] = popularity(row.get("popularity"))
            if any(v is not None for v in hours):
                usual[str(day)] = hours
        out[src["name"]] = {"usual_week": usual or None, "live": popularity(src.get("current_popularity")),
                            "recorded_at": src.get("recorded_at")}
    return out


def _backup_live(entry, now):
    """The backup's live value only when it is present and recent; (value, observed_at)."""
    value = (entry or {}).get("live")
    try:
        at = datetime.fromisoformat(str(entry.get("recorded_at")).replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None, None
    if value is None or not at.tzinfo or not (timedelta(0) <= now - at <= BACKUP_MAX_AGE):
        return None, None
    return value, at.isoformat()


def _recent(points, now, hours=24):
    out = []
    for p in points or []:
        try:
            at = datetime.fromisoformat(str(p.get("at")).replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            continue
        if at.tzinfo and now - timedelta(hours=hours) < at <= now:
            out.append({"at": p["at"], "v": popularity(p.get("v"))})
    return out


def build_shops(live: dict, venues: dict, previous_shops, now: datetime, queried: bool,
                backup: dict | None = None) -> list[dict]:
    """
    live: {display name: besttime_live result} for this run ({} when not queried).
    previous_shops: last data.json pizza list, for the 24-hour history of our own readings.
    queried: False outside the US Eastern 16–24 window, so missing readings are "waiting", not failures.
    backup: backup_shops() output; fills the usual week and a recent live value only where ours is missing.
    """
    prev = {s.get("name"): s for s in previous_shops or [] if isinstance(s, dict)}
    shops = []
    for name, venue in PIZZA_VENUES.items():
        stored = (venues.get("venues") or {}).get(name) or {}
        spare = (backup or {}).get(name) or {}
        usual_week = stored.get("usual_week") or spare.get("usual_week")
        result = live.get(name) or {}
        value = popularity(result.get("live_busyness")) if result.get("live_available") else None
        source, observed = ("besttime", now.isoformat()) if value is not None else ("none", None)
        if value is None:
            value, observed = _backup_live(spare, now)
            source = "backup" if value is not None else "none"
        hourly = _recent((prev.get(name) or {}).get("hourly_24h"), now)
        if value is not None and not any(p.get("at") == observed for p in hourly):
            hourly = (hourly + [{"at": observed, "v": value}])[-24:]
        usual = usual_at(usual_week, now)
        if usual is None:
            usual = popularity(result.get("forecasted"))
        if value is not None:
            status, pct, magnitude = shop_status(value, usual)
            is_open = True
        else:
            pct = magnitude = None
            closed = result.get("open") in (False, "Closed", "closed")
            is_open = False if closed else None
            status = ("closed" if closed else "baseline_only" if not stored.get("venue_id") and usual_week
                      else "setup_needed" if not stored.get("venue_id")
                      else "waiting" if not queried else "unavailable")
        shops.append({
            "name": name,
            "busyness": value,
            "is_open": is_open,
            "status": status,
            "usual_now": usual,
            "percentage_of_usual": pct,
            "spike": status == "spike",
            "spike_magnitude": magnitude,
            "hourly_24h": hourly,
            "usual_week": usual_week,
            "address": venue["address"],
            "data_source": source,
            "recorded_at": observed,
            **({"error_message": result["error_message"]} if result.get("error_message") else {}),
        })
    return shops


def summarize(shops: list[dict], venues: dict, queried: bool, now: datetime) -> dict:
    """Block-level reading and the WPI pizza factor (None unless at least two shops can be compared)."""
    live = [s for s in shops if s.get("busyness") is not None]
    compared = [s for s in live if s.get("percentage_of_usual") is not None]
    busy = [s for s in live if s["status"] == "busy"]
    spikes = [s for s in live if s["status"] == "spike"]
    ready = sum(1 for v in (venues.get("venues") or {}).values() if isinstance(v, dict) and v.get("venue_id"))
    if live:
        state = "ok"
    elif not ready:
        state = "baseline_only" if any(s.get("usual_week") for s in shops) else "setup_needed"
    elif not queried:
        state = "off_hours"
    else:
        state = "no_live"
    level = None
    if live:
        level = "spike" if spikes or len(busy) >= 2 else "busy" if busy else "normal"
    index = None
    if len(compared) >= 2:
        index = round(min(100.0, sum(max(0, s["percentage_of_usual"] - 100) for s in compared) / len(compared)), 1)
    return {
        "state": state, "level": level, "index": index,
        "live_count": len(live), "total": len(shops), "ready_venues": ready,
        "busy": [s["name"] for s in busy], "spikes": [s["name"] for s in spikes],
        "queried_at": max((s["recorded_at"] for s in live if s.get("recorded_at")), default=None) if live
                      else now.isoformat() if queried else None,
    }


def spike_events(shops: list[dict]) -> list[dict]:
    return [{"place_name": s["name"], "spike_magnitude": s["spike_magnitude"],
             "percentage_of_usual": s["percentage_of_usual"], "at": s["recorded_at"], "minutes_ago": 0}
            for s in shops if s.get("status") == "spike"]
