"""Bounded NOTAC adapter used by the existing fetch_notams entry point.

No environment lookup, CLI, notification, or writes. Caller supplies credentials.
The returned rows are for validation/archiving, not automatic public display.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit, parse_qs

BASE = 'https://notac.aero/api/v1/notam/'
MAX_PAGES = 2
MAX_BYTES = 2 * 1024 * 1024


def integer(value):
    return type(value) is int and value >= 0


def safe_next(url, firs):
    if not isinstance(url, str):
        return False
    parts = urlsplit(url)
    if (parts.scheme != 'https' or parts.netloc != 'notac.aero'
            or parts.path != '/api/v1/notam/' or parts.fragment):
        return False
    params = parse_qs(parts.query, keep_blank_values=True)
    allowed = {'fir', 'status', 'sort', 'page'}
    selected = [code for group in params.get('fir', []) for code in group.split(',')]
    return (set(params) <= allowed and sorted(selected) == sorted(firs)
            and params.get('status') == ['active'] and params.get('sort') == ['newest']
            and len(params.get('page', [])) == 1 and params['page'][0].isdigit()
            and int(params['page'][0]) >= 2)


def cooldown(status, headers, now):
    if status == 402:
        return datetime(now.year + (now.month == 12), now.month % 12 + 1, 1,
                        tzinfo=timezone.utc).isoformat()
    if status == 429:
        value = headers.get('Retry-After', '')
        seconds = int(value) if str(value).isdigit() else 3600
        return (now + timedelta(seconds=max(1, seconds))).isoformat()
    if status in (401, 403):
        return (now + timedelta(hours=24)).isoformat()
    return None


async def collect_region(session, token, firs, now=None):
    """At most two sequential pages; no retries or cross-host redirects.

    Complete means the returned active-query list passed local checks, not that
    the upstream captures every real-world notice. HTTP errors contain no body.
    """
    import json
    import aiohttp
    now = now or datetime.now(timezone.utc)
    if not token:
        return {'available': False, 'reason': 'missing_key', 'complete': False, 'total': None}
    if not firs or any(not isinstance(f, str) or len(f) != 4 or not f.isascii()
                       or not f.isalpha() or not f.isupper() for f in firs):
        raise ValueError('invalid FIR selection')
    url = BASE + '?' + urlencode({'fir': ','.join(firs), 'status': 'active', 'sort': 'newest'})
    rows, seen, visited = [], set(), set()
    count = None
    result = {'provider': 'NOTAC', 'firs': list(firs), 'fetched_at': now.isoformat(),
              'complete': False, 'available': False, 'total': None, 'reported_count': None,
              'rows': rows, 'pages': 0, 'credits_remaining': None}
    try:
        for page in range(MAX_PAGES):
            if url in visited:
                raise ValueError('pagination_cycle')
            visited.add(url)
            if page:
                await asyncio.sleep(0.6)
            async with session.get(url, headers={'Authorization': 'Bearer ' + token},
                                   allow_redirects=False, timeout=aiohttp.ClientTimeout(total=20)) as response:
                result['pages'] += 1
                remaining = response.headers.get('X-Credits-Remaining')
                if isinstance(remaining, str) and remaining.isdigit():
                    result['credits_remaining'] = int(remaining)
                if response.status != 200:
                    result.update(reason='http_' + str(response.status),
                                  cooldown_until=cooldown(response.status, response.headers, now))
                    break
                body = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        raise ValueError('response_too_large')
                payload = json.loads(body)
            if not isinstance(payload, dict) or not integer(payload.get('count')) or not isinstance(payload.get('results'), list):
                raise ValueError('invalid_page')
            if count is not None and count != payload['count']:
                raise ValueError('count_changed_during_paging')
            count = payload['count']
            result['reported_count'] = count
            for row in payload['results']:
                if (not isinstance(row, dict) or not isinstance(row.get('id'), str)
                        or not row['id'] or row['id'] in seen or row.get('status') != 'active'
                        or row.get('affected_fir') not in firs or not isinstance(row.get('text'), str)):
                    raise ValueError('invalid_or_duplicate_row')
                seen.add(row['id'])
                rows.append(row)
            if len(rows) > count:
                raise ValueError('count_mismatch')
            if 'next' not in payload:
                raise ValueError('missing_pagination')
            following = payload['next']
            if following is None:
                if len(rows) != count:
                    raise ValueError('count_mismatch')
                result.update(complete=True, available=True, total=count, reason='complete_query')
                break
            if not safe_next(following, firs):
                raise ValueError('unsafe_next')
            url = following
            result['reason'] = 'page_budget_reached'
            if result['credits_remaining'] is not None and result['credits_remaining'] < 2:
                result['reason'] = 'credits_low'
                break
    except Exception as exc:
        # Never expose request exceptions, tokens, response bodies, or URLs.
        result['reason'] = 'invalid_response' if isinstance(exc, (ValueError, TypeError)) else 'request_failed'
    result['sample_count'] = len(rows)
    result['partial'] = bool(rows) and not result['complete']
    return result


def parsed_time(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result if result.tzinfo is not None else None
    except (ValueError, TypeError, AttributeError):
        return None


def save_observation(directory, result):
    """Immutable source metadata; no provider-generated readings or credentials."""
    import gzip
    import hashlib
    import json
    from pathlib import Path
    fields = ('id', 'number', 'status', 'affected_fir', 'location_code', 'q_code',
              'effective_start', 'effective_end', 'created_at', 'updated_at')
    payload = {k: v for k, v in result.items() if k != 'rows'}
    payload.update(kind='source_observation', source='notac', archive_version=1,
                   rows=[{k: row[k] for k in fields if k in row} for row in result.get('rows', [])])
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    digest = hashlib.sha256(raw).hexdigest()
    path = Path(directory) / 'notac' / (result['fetched_at'].replace(':', '-') + '_' + digest + '.json.gz')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if gzip.decompress(path.read_bytes()) != raw:
            raise ValueError('archive mismatch')
    else:
        with path.open('xb') as stream:
            stream.write(gzip.compress(raw, mtime=0))
    return path


async def collect_regions(session, token, regions, previous, danger_re, closure_re, archive_dir=None, now=None):
    now = now or datetime.now(timezone.utc)
    # Shared credential limits apply across all regions. FAA cooldowns do not
    # suppress the newly configured official API provider.
    deadlines = [parsed_time(r.get('cooldown_until')) for r in previous.values()
                 if isinstance(r, dict) and r.get('provider') == 'NOTAC']
    blocked = max((d for d in deadlines if d is not None and d > now), default=None)
    out = {}
    for key, firs in regions.items():
        old = previous.get(key) or {}
        attempted = parsed_time(old.get('attempted_at')) if old.get('provider') == 'NOTAC' else None
        # Match the existing 110-minute guard, including unsuccessful passes.
        if blocked or (attempted and (now - attempted).total_seconds() < 6600):
            out[key] = {**old, 'provider': 'NOTAC', 'stale': True,
                        'reason': 'cooldown' if blocked else 'source_spacing'}
            if blocked:
                out[key]['cooldown_until'] = blocked.isoformat()
            continue
        try:
            result = await asyncio.wait_for(collect_region(session, token, firs, now), timeout=42)
        except TimeoutError:
            result = {'provider': 'NOTAC', 'firs': firs, 'fetched_at': now.isoformat(),
                      'complete': False, 'reason': 'source_timeout', 'sample_count': None}
        # Counts describe validated returned rows only, even when paging stops.
        # Zero candidates in a sample never means zero across the whole FIR.
        rows = result.get('rows')
        if isinstance(rows, list) and (rows or result.get('complete')):
            result['sample_danger'] = sum(bool(danger_re.search(r['text'])) for r in rows)
            result['sample_closure'] = sum(bool(closure_re.search(r['text'])) for r in rows)
            result['sample_order'] = 'newest'
            timing = {'current': 0, 'future': 0, 'ended': 0, 'unknown': 0}
            for row in rows:
                start, end = parsed_time(row.get('effective_start')), parsed_time(row.get('effective_end'))
                if start and end and end <= start:
                    kind = 'unknown'
                elif end and end <= now:
                    kind = 'ended'
                elif start and start > now:
                    kind = 'future'
                elif start and end and start <= now < end:
                    kind = 'current'
                else:
                    kind = 'unknown'
                timing[kind] += 1
            result['sample_timing'] = timing
        if archive_dir:
            save_observation(archive_dir, result)
        summary = {k: v for k, v in result.items() if k != 'rows'}
        summary['attempted_at'] = now.isoformat()
        if result.get('complete'):
            messages = [r['text'] for r in result['rows']]
            danger = sum(bool(danger_re.search(t)) for t in messages)
            closure = any(closure_re.search(t) for t in messages)
            summary.update(observed_at=now.isoformat(), stale=False, danger=danger, closure=closure,
                           score=round(min(100.0, danger * 8 + (40 if closure else 0)), 1))
            before = parsed_time(old.get('observed_at'))
            if (old.get('provider') == 'NOTAC' and old.get('complete') is True
                    and old.get('firs') == list(firs) and integer(old.get('total'))
                    and before and 0 < (now - before).total_seconds() <= 21600):
                summary['comparison'] = {'observed_at': old['observed_at'],
                                         'total_change': result['total'] - old['total']}
        else:
            # Old observations stay intact; a partial new attempt lives separately.
            summary = {**old, 'provider': 'NOTAC', 'firs': list(firs), 'stale': True,
                       'observed_provider': old.get('observed_provider', old.get('provider', 'FAA')) if old.get('observed_at') else None,
                       'attempted_at': now.isoformat(), 'reason': result.get('reason'), 'latest_attempt': summary}
        until = parsed_time(result.get('cooldown_until'))
        remaining = result.get('credits_remaining')
        if remaining is not None and remaining < 20:
            until = parsed_time(cooldown(402, {}, now))
        if until and until > now:
            blocked = until
            summary['cooldown_until'] = until.isoformat()
        out[key] = summary
    return out
