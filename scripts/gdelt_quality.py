"""Validate DOC timeline observations independently from retrieval time."""
import math
from datetime import datetime, timezone, timedelta


def timeline_metrics(payload, now=None):
    now = now or datetime.now(timezone.utc)
    points = payload['timeline'][0]['data']
    parsed = {}
    for point in points:
        value = point.get('value')
        if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError('invalid_news_share')
        stamp = datetime.strptime(point['date'], '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
        if stamp > now + timedelta(minutes=15) or stamp < now - timedelta(hours=49) or stamp in parsed:
            raise ValueError('invalid_timeline_time')
        parsed[stamp] = value
    if len(parsed) < 6:
        raise ValueError('insufficient_timeline')
    ordered = sorted(parsed)
    vals = [parsed[d] for d in ordered]
    latest = sum(vals[-6:]) / 6
    avg = sum(vals) / len(vals)
    return {'observed_at': ordered[-1].isoformat(), 'fetched_at': now.isoformat(),
            'window_start': ordered[0].isoformat(), 'point_count': len(vals),
            'latest': round(latest,3), 'avg48h': round(avg,3),
            'delta_pct': round((latest-avg)/avg*100,1) if avg else 0,
            'stale': now - ordered[-1] > timedelta(hours=6)}


def cooldown_active(rows, now=None):
    now = now or datetime.now(timezone.utc)
    for row in rows.values():
        try:
            if datetime.fromisoformat(row.get('cooldown_until')) > now: return True
        except (TypeError, ValueError): pass
    return False


def cooldown_deadline(headers, now=None):
    now = now or datetime.now(timezone.utc)
    try: seconds = max(3600, min(86400, int(headers.get('Retry-After','21600'))))
    except (TypeError, ValueError): seconds = 21600
    return (now + timedelta(seconds=seconds)).isoformat()
