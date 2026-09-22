"""Offline PizzINT threshold study. Observed crossings are not military DEFCON.

No network, notifications, history rewrites, or automatic negative labels.
"""
import gzip
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'pizza-48h-v1'
MAX_GAP = timedelta(hours=6)


def instant(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (ValueError, AttributeError, TypeError):
        return None


def observation(snapshot, provenance):
    return {'at': snapshot.get('updated_at'), 'level': snapshot.get('defcon_level'),
            'source_at': (snapshot.get('defcon_details') or {}).get('at_time'),
            'archive': provenance}


def calculate(rows, reviews, as_of):
    now = instant(as_of)
    if now is None:
        raise ValueError('Analysis cutoff requires a timezone')
    # Preserve collection-time observations. Repeated upstream timestamps do not
    # become new measurements; invalid/stale points break transition continuity.
    unique = {}
    conflicts = set()
    for row in rows:
        at = instant(row.get('at'))
        if at and at <= now:
            if at in unique and (unique[at].get('level'), unique[at].get('source_at')) != (row.get('level'), row.get('source_at')):
                conflicts.add(at)
            unique[at] = row
    ordered = sorted(unique.items())
    groups = {}
    for threshold in (3, 2):
        previous = None
        events = []
        gaps = invalid = repeated = 0
        for at, row in ordered:
            level, source = row.get('level'), instant(row.get('source_at'))
            valid = (at not in conflicts and type(level) is int and 1 <= level <= 5
                     and source is not None and timedelta(0) <= at-source <= MAX_GAP)
            if not valid:
                invalid += 1
                previous = None
                continue
            if previous and source == previous[2]:
                repeated += 1
                if level != previous[1]:
                    previous = None  # Conflicting same-time revision: no inferred crossing.
                continue
            gap = previous is None or at-previous[0] > MAX_GAP or source <= previous[2]
            if gap:
                gaps += 1
            crossing = level <= threshold and (gap or previous[1] > threshold)
            if crossing:
                end = at + timedelta(hours=48)
                event_id = f'{VERSION}:{threshold}:{at.isoformat()}'
                status = 'uncertain_start' if gap else ('pending' if end > now else 'unreviewed')
                review = reviews.get(event_id, {})
                # Explicit review, sources, scope and time precision are required.
                if status == 'unreviewed' and review.get('scope') == 'major-us-direct-action-v1' and review.get('sources') and instant(review.get('reviewed_at')) and end <= instant(review['reviewed_at']) <= now:
                    if review.get('outcome') == 'no_qualifying_action' and review.get('complete_window') is True:
                        status = 'reviewed_no'
                    elif review.get('outcome') == 'qualifying_action':
                        lo, hi = instant(review.get('action_start')), instant(review.get('action_end'))
                        if lo and hi and at <= lo <= hi <= end:
                            status = 'reviewed_yes'
                events.append({'id': event_id, 'at': at.isoformat(), 'source_at': source.isoformat(),
                               'previous_at': previous[0].isoformat() if previous else None,
                               'ends_at': end.isoformat(), 'level': level, 'status': status,
                               'archive': row.get('archive'), 'sources': review.get('sources', [])})
            previous = (at, level, source)
        counts = {key: sum(e['status'] == key for e in events) for key in
                  ('pending', 'unreviewed', 'uncertain_start', 'reviewed_yes', 'reviewed_no')}
        n = counts['reviewed_yes'] + counts['reviewed_no']
        rate = counts['reviewed_yes']/n if n else None
        interval = None
        if n:
            z = 1.96
            center = (rate+z*z/(2*n))/(1+z*z/n)
            half = z*((rate*(1-rate)/n+z*z/(4*n*n))**.5)/(1+z*z/n)
            interval = [max(0, center-half), min(1, center+half)]
        unresolved = counts['unreviewed']
        # Do not present a selected subset of reviewed positives as the cohort rate.
        groups[str(threshold)] = {'threshold': threshold, 'events': events, 'counts': counts,
            'detected_crossings': len(events)-counts['uncertain_start'], 'reviewed': n,
            'reviewed_fraction': rate, 'rate': rate if not unresolved else None,
            'confidence_interval': interval if not unresolved else None,
            'mature_bounds': [counts['reviewed_yes']/(n+unresolved), (counts['reviewed_yes']+unresolved)/(n+unresolved)] if n+unresolved else None,
            'gaps': gaps, 'invalid': invalid, 'repeated': repeated}
    return {'version': VERSION, 'as_of': now.isoformat(), 'observations': len(ordered),
            'first_at': ordered[0][0].isoformat() if ordered else None,
            'last_at': ordered[-1][0].isoformat() if ordered else None,
            'groups': groups, 'baseline_rate': None, 'predictive_lift': None}


def build(snapshot, root=ROOT):
    seed = json.loads((root/'research/pizza-observations.json').read_text())
    registry = json.loads((root/'research/pizza-reviews.json').read_text())
    rows = list(seed['observations'])
    failed = 0
    # Existing immutable archives supply history even after publication retries.
    # Source-only archives are not analysis snapshots.
    for path in sorted((root/'archives').glob('[0-9][0-9][0-9][0-9]/*/*.json.gz')):
        try:
            archived = json.loads(gzip.decompress(path.read_bytes()))
            value = archived.get('files', {}).get('data.json')
            if isinstance(value, dict):
                rows.append(observation(value, str(path.relative_to(root))))
        except (OSError, ValueError, EOFError):
            failed += 1
    rows.append(observation(snapshot, 'current_snapshot'))
    result = calculate(rows, registry['reviews'], snapshot['updated_at'])
    result['unreadable_archives'] = failed
    result['candidate_actions'] = registry['candidates']
    if failed:
        for group in result['groups'].values():
            group['rate'] = group['confidence_interval'] = None
    return result
