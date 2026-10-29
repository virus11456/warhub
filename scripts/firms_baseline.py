"""Satellite fire detections relative to each region's own recent level.

The raw 24h count says little on its own: farmland burning keeps Russia and
Ukraine in the hundreds in autumn, while a quiet strait sits near zero. This
module keeps a 7-day series of NASA FIRMS conflict-area counts (one sample per
FIRMS acquisition time) and scores the current count against that series the
same way airspace notices are scored: the usual level is 50, more detections
than usual push the score up. Missing, failed or carried-over snapshots are
never samples, and a label absent from a valid snapshot means zero detections.
"""
import gzip
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

WINDOW_DAYS = 7
MIN_SAMPLES = 8
MIN_SPAN_HOURS = 24
SEED_MAX_FILES = 800


def _time(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return stamp if stamp.tzinfo else None
    except (TypeError, ValueError):
        return None


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def observation(firms):
    """A usable sample: fresh, no error, complete conflict counts and a valid acquisition time."""
    if not isinstance(firms, dict) or firms.get('stale') or firms.get('error'):
        return None
    counts, at = firms.get('conflict_counts'), _time(firms.get('observed_at'))
    if not isinstance(counts, dict) or at is None:
        return None
    clean = {k: _count(v) for k, v in counts.items() if isinstance(k, str)}
    if any(v is None for v in clean.values()):
        return None
    return {'at': at.isoformat(), 'counts': clean}


def update(previous, firms, now):
    """Merge this round into the 7-day series, one row per acquisition time."""
    rows = {}
    for row in list(previous or []) + [observation(firms)]:
        if not isinstance(row, dict) or not isinstance(row.get('counts'), dict):
            continue
        at = _time(row.get('at'))
        if at and now - timedelta(days=WINDOW_DAYS) <= at <= now + timedelta(minutes=15):
            rows[at] = {'at': at.isoformat(), 'counts': row['counts']}
    return [rows[k] for k in sorted(rows)]


def relative(series, firms, labels):
    """Score the current count for these conflict labels; None while the baseline is short."""
    result = {'score': None, 'count': None, 'baseline': None, 'baseline_samples': 0}
    current = observation(firms)
    if current is None or not labels:
        result['reason'] = 'no_fresh_observation' if labels else 'no_fire_area'
        return result
    total = lambda row: sum(_count(row['counts'].get(label)) or 0 for label in labels)
    at = _time(current['at'])
    earlier = [r for r in series or [] if _time(r['at']) < at]
    result.update(count=total(current), baseline_samples=len(earlier))
    span = (at - _time(earlier[0]['at'])).total_seconds() / 3600 if earlier else 0
    if len(earlier) < MIN_SAMPLES or span < MIN_SPAN_HOURS:
        result['reason'] = 'baseline_accumulating'
        return result
    avg = sum(total(r) for r in earlier) / len(earlier)
    # +1 smoothing keeps quiet areas defined: 0 now vs 0 usual = 50.
    score = min(100.0, 50 * (result['count'] + 1) / (avg + 1))
    result.update(score=round(score, 1) if math.isfinite(score) else None, baseline=round(avg, 1))
    return result


def seed_from_archives(archive_root, now, max_files=SEED_MAX_FILES):
    """One-time baseline from already saved analysis snapshots (real past observations only)."""
    cutoff = (now - timedelta(days=WINDOW_DAYS)).strftime('%Y%m%d')
    paths = sorted(p for p in Path(archive_root).glob('20*/*/*.json.gz') if p.name[:8] >= cutoff)[-max_files:]
    series = []
    for path in paths:
        try:
            with gzip.open(path, 'rb') as stream:
                payload = json.load(stream)
        except (OSError, ValueError):
            continue
        if payload.get('kind') or not isinstance(payload.get('files'), dict):
            continue
        series = update(series, (payload['files'].get('data.json') or {}).get('firms'), now)
    return series
