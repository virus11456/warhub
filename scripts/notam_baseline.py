"""Airspace notices relative to each region's own recent level.

The absolute score (danger keyword count x 8, capped at 100) saturated: busy
FIRs such as Taipei, the Middle East and the South China Sea always scored
100 and quiet ones always 0. This module keeps a 7-day series of complete,
fresh observations and scores the current count against that baseline:
the usual level is 50, more danger notices than usual push the score up.
"""
import gzip
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

WINDOW_DAYS = 7
MIN_SAMPLES = 12
MIN_SPAN_HOURS = 24
SEED_MAX_FILES = 800  # analysis snapshots are mixed with source archives; one-time ~5s


def _time(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return stamp if stamp.tzinfo else None
    except (TypeError, ValueError):
        return None


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def observation(record):
    """A usable sample: complete query, not stale, valid count and time."""
    if not isinstance(record, dict) or record.get('stale') or record.get('complete') is not True:
        return None
    at, danger = _time(record.get('observed_at')), _count(record.get('danger'))
    if at is None or danger is None:
        return None
    return {'at': at.isoformat(), 'danger': danger, 'closure': record.get('closure') is True}


def update(previous, notams, now):
    """Merge this round into the per-region 7-day series (deduplicated by observation time)."""
    out = {}
    regions = set(previous or {}) | set(notams or {})
    for key in regions:
        rows = {}
        for row in list((previous or {}).get(key) or []) + [observation((notams or {}).get(key))]:
            if not isinstance(row, dict):
                continue
            at, danger = _time(row.get('at')), _count(row.get('danger'))
            if at and danger is not None and now - timedelta(days=WINDOW_DAYS) <= at <= now + timedelta(minutes=15):
                rows[at] = {'at': at.isoformat(), 'danger': danger, 'closure': row.get('closure') is True}
        out[key] = [rows[k] for k in sorted(rows)]
    return out


def relative(series, record):
    """Score the current record against earlier samples; None while the baseline is short."""
    current = observation(record)
    result = {'score': None, 'baseline_danger': None, 'baseline_samples': 0}
    if current is None:
        result['reason'] = 'no_fresh_complete_observation'
        return result
    at = _time(current['at'])
    earlier = [r for r in series or [] if _time(r['at']) < at]
    result['baseline_samples'] = len(earlier)
    span = (at - _time(earlier[0]['at'])).total_seconds() / 3600 if earlier else 0
    if len(earlier) < MIN_SAMPLES or span < MIN_SPAN_HOURS:
        result['reason'] = 'baseline_accumulating'
        return result
    avg = sum(r['danger'] for r in earlier) / len(earlier)
    # +1 smoothing keeps quiet regions defined: 0 now vs 0 usual = 50; 3 vs 0 = 100.
    score = min(100.0, 50 * (current['danger'] + 1) / (avg + 1))
    result.update(score=round(score, 1) if math.isfinite(score) else None,
                  baseline_danger=round(avg, 1))
    return result


def seed_from_archives(archive_root, now, max_files=SEED_MAX_FILES):
    """One-time baseline from already saved analysis snapshots (real past observations only)."""
    cutoff = (now - timedelta(days=WINDOW_DAYS)).strftime('%Y%m%d')
    paths = sorted(p for p in Path(archive_root).glob('20*/*/*.json.gz') if p.name[:8] >= cutoff)[-max_files:]
    series = {}
    for path in paths:
        try:
            with gzip.open(path, 'rb') as stream:
                payload = json.load(stream)
        except (OSError, ValueError):
            continue
        if payload.get('kind') or not isinstance(payload.get('files'), dict):
            continue
        notams = (payload['files'].get('data.json') or {}).get('notams') or {}
        series = update(series, notams, now)
    return series
