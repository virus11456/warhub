"""Regional conflict-coverage share from GDELT 2.0 Events export files.

Fallback for the DOC timelinevol factor when that API is rate limited. It is a
different measurement (event articles, not DOC full-text matches), so it is
stored separately, labelled as such, and only scored against its own baseline.
"""
import math
import re
from datetime import datetime, timedelta, timezone

BATCHES = 8                 # 2 hours of 15-minute export files per collection
BASELINE_HOURS = 48
MIN_BASELINE_SAMPLES = 12
MIN_BASELINE_SPAN_HOURS = 24
MIN_BASELINE_REGION_ARTICLES = 30
STALE_HOURS = 6
CONFLICT_QUAD_CLASSES = {'3', '4'}   # verbal / material conflict

# Columns from the GDELT 2.0 Event codebook (61 columns).
ID, ACTOR1_COUNTRY, ACTOR2_COUNTRY, QUAD_CLASS, NUM_ARTICLES = 0, 7, 17, 29, 33
ACTION_GEO_NAME, ACTION_GEO_COUNTRY = 52, 53

# Actors use CAMEO country codes; ActionGeo uses FIPS 10-4 country codes.
REGION_RULES = {
    'ukraine': {'actors': {'UKR', 'RUS'}, 'geo': {'UP', 'RS'}},
    'mideast': {'actors': {'IRN', 'ISR'}, 'geo': {'IR', 'IS'}},
    'taiwan': {'actors': {'TWN'}, 'geo': {'TW'}},
    'korea': {'actors': {'PRK'}, 'geo': {'KN'}},
    'southsea': {'actors': set(), 'geo': set(),
                 'place': re.compile(r'south china sea|spratly|scarborough|paracel|second thomas shoal', re.I),
                 'pairs': ({'CHN', 'PHL'}, {'CHN', 'VNM'})},
}


def batch_stamps(latest, count=BATCHES):
    end = datetime.strptime(latest, '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
    if end.minute % 15 or end.second:
        raise ValueError('invalid_batch_stamp')
    return [(end - timedelta(minutes=15 * i)).strftime('%Y%m%d%H%M%S') for i in range(count)][::-1]


def _in_region(row, rule):
    actors = {row[ACTOR1_COUNTRY], row[ACTOR2_COUNTRY]}
    if actors & rule['actors'] or row[ACTION_GEO_COUNTRY] in rule['geo']:
        return True
    if rule.get('place') and rule['place'].search(row[ACTION_GEO_NAME]):
        return True
    return any(pair <= actors for pair in rule.get('pairs', ()))


def count_articles(batches):
    """Article totals for one window; each GlobalEventID counts once."""
    seen, total = set(), 0
    regions = dict.fromkeys(REGION_RULES, 0)
    for rows in batches:
        for row in rows:
            if row[ID] in seen:
                continue
            seen.add(row[ID])
            try:
                articles = int(row[NUM_ARTICLES])
            except ValueError:
                raise ValueError('invalid_article_count') from None
            if articles < 0:
                raise ValueError('invalid_article_count')
            total += articles
            if row[QUAD_CLASS] in CONFLICT_QUAD_CLASSES:
                for key, rule in REGION_RULES.items():
                    if _in_region(row, rule):
                        regions[key] += articles
    if total <= 0:
        raise ValueError('empty_window')
    return {'total_articles': total, 'event_count': len(seen), 'region_articles': regions}


def sample(counts, window_start, window_end):
    return {'window_start': window_start.isoformat(), 'window_end': window_end.isoformat(),
            'total_articles': counts['total_articles'],
            'region_articles': dict(counts['region_articles'])}


def _valid_sample(row):
    try:
        end = datetime.fromisoformat(row['window_end'])
        total = row['total_articles']
        regions = row['region_articles']
        ok = (end.tzinfo is not None and isinstance(total, int) and not isinstance(total, bool) and total > 0
              and isinstance(regions, dict)
              and all(isinstance(regions.get(k), int) and not isinstance(regions.get(k), bool)
                      and 0 <= regions[k] <= total for k in REGION_RULES))
        return end if ok else None
    except (KeyError, TypeError, ValueError):
        return None


def update_series(previous, new, now):
    """Keep valid samples from the last 48h; a repeated window end is replaced, not duplicated."""
    rows = {}
    for row in list(previous or []) + ([new] if new else []):
        end = _valid_sample(row)
        if end and now - timedelta(hours=BASELINE_HOURS + 2) <= end <= now + timedelta(minutes=15):
            rows[end] = row
    return [rows[k] for k in sorted(rows)]


def regional_metrics(series, now, fresh):
    """Per-region share and baseline. Missing or sparse baselines stay unscored, never zero."""
    valid = [(e, r) for r in series for e in [_valid_sample(r)] if e]
    out = {}
    if not valid:
        return {key: {'provider': 'gdelt_events', 'stale': True, 'score': None, 'reason': 'no_observation'}
                for key in REGION_RULES}
    latest_end, latest = valid[-1]
    stale = not fresh or now - latest_end > timedelta(hours=STALE_HOURS)
    baseline = [(e, r) for e, r in valid[:-1] if latest_end - e <= timedelta(hours=BASELINE_HOURS)]
    span = (latest_end - baseline[0][0]).total_seconds() / 3600 if baseline else 0
    for key in REGION_RULES:
        share = latest['region_articles'][key] / latest['total_articles'] * 100
        row = {'provider': 'gdelt_events', 'metric': 'conflict_event_article_share',
               'observed_at': latest['window_end'], 'window_start': latest['window_start'],
               'latest': round(share, 3), 'region_articles': latest['region_articles'][key],
               'total_articles': latest['total_articles'], 'baseline_samples': len(baseline),
               'stale': stale, 'score': None, 'avg48h': None, 'delta_pct': None}
        region_sum = sum(r['region_articles'][key] for _, r in baseline)
        if len(baseline) < MIN_BASELINE_SAMPLES or span < MIN_BASELINE_SPAN_HOURS:
            row['reason'] = 'baseline_accumulating'
        elif region_sum < MIN_BASELINE_REGION_ARTICLES:
            row['reason'] = 'baseline_too_sparse'
        else:
            avg = sum(r['region_articles'][key] / r['total_articles'] * 100 for _, r in baseline) / len(baseline)
            row['avg48h'] = round(avg, 3)
            if avg > 0:
                row['delta_pct'] = round((share - avg) / avg * 100, 1)
                # Baseline level = 50, double the usual share = 100; a measured zero stays 0.
                score = min(100.0, 50 * share / avg)
                row['score'] = round(score, 1) if math.isfinite(score) else None
            else:
                row['reason'] = 'baseline_too_sparse'
        if stale:
            row['reason'] = row.get('reason') or 'stale_observation'
        out[key] = row
    return out
