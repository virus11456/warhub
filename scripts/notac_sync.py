"""Resumable NOTAC delta ingestion. Cursor is opaque; partial mirrors never score."""
import asyncio
import copy
import json
from datetime import timedelta
from urllib.parse import urlencode, urlsplit, parse_qs
import aiohttp
from notac_client import parsed_time, cooldown, MAX_BYTES

BASE = 'https://notac.aero/api/v1/notam/delta/'
FIELDS = ('id', 'number', 'status', 'affected_fir', 'location_code', 'q_code',
          'effective_start', 'effective_end', 'record_updated_at', 'record_archived_at')
PER_RUN = 8
PER_DAY = 90
PER_MONTH = 2800


class Budget:
    def __init__(self, previous, now):
        self.day, self.month = now.date().isoformat(), now.strftime('%Y-%m')
        ledgers = [r.get('sync_budget', {}) for r in previous.values() if isinstance(r, dict)]
        self.used_day = sum(r.get('day_calls', 0) for r in ledgers if r.get('day') == self.day)
        self.used_month = sum(r.get('month_calls', 0) for r in ledgers if r.get('month') == self.month)
        self.used_run = 0
        balances = [(r.get('latest_attempt') or r).get('credits_remaining')
                    for r in previous.values() if isinstance(r, dict)
                    and (r.get('sync_budget') or {}).get('month') == self.month]
        self.remaining = min((v for v in balances if type(v) is int and v >= 0), default=None)

    def allowed(self):
        return (self.used_run < PER_RUN and self.used_day < PER_DAY
                and self.used_month < PER_MONTH
                and (self.remaining is None or self.remaining >= 23))

    def charge(self, ledger):
        self.used_run += 1
        self.used_day += 1
        self.used_month += 1
        ledger['day_calls'] += 1
        ledger['month_calls'] += 1


def next_cursor(url, firs):
    parts = urlsplit(url)
    params = parse_qs(parts.query, keep_blank_values=True)
    selected = [c for group in params.get('fir', []) for c in group.split(',')]
    if (parts.scheme != 'https' or parts.netloc != 'notac.aero'
            or parts.path != '/api/v1/notam/delta/' or parts.fragment
            or set(params) != {'fir', 'cursor'} or sorted(selected) != sorted(firs)
            or len(params['cursor']) != 1 or not params['cursor'][0]):
        raise ValueError('unsafe_next')
    return params['cursor'][0]


async def collect_delta(session, token, firs, old, budget, danger_re, closure_re, now):
    prior = old.get('sync_state') or {}
    if prior and (prior.get('version') != 1 or prior.get('firs') != list(firs)):
        # Do not reuse positions from another scope.
        prior = {}
    state = copy.deepcopy(prior) or {'version': 1, 'firs': list(firs), 'records': {}, 'cursor': None, 'tombstones': {}}
    ledger_old = old.get('sync_budget') or {}
    ledger = {'day': budget.day, 'month': budget.month,
              'day_calls': ledger_old.get('day_calls', 0) if ledger_old.get('day') == budget.day else 0,
              'month_calls': ledger_old.get('month_calls', 0) if ledger_old.get('month') == budget.month else 0}
    result = {'provider': 'NOTAC', 'firs': list(firs), 'fetched_at': now.isoformat(),
              'protocol': 'delta-v1', 'complete': False, 'available': False, 'total': None,
              'reported_count': None, 'pages': 0, 'credits_remaining': None,
              'reason': 'request_budget_reached', 'sync_state': state, 'sync_budget': ledger}
    visited = set()
    for _ in range(2):
        if not token:
            result['reason'] = 'missing_key'
            break
        if not budget.allowed():
            break
        cursor = state.get('cursor')
        if cursor in visited:
            result['reason'] = 'pagination_cycle'
            break
        visited.add(cursor)
        params = {'fir': ','.join(firs)}
        if cursor:
            params['cursor'] = cursor
        url = BASE + '?' + urlencode(params)
        # Count before I/O: timeout/unknown responses must not grant a free retry.
        budget.charge(ledger)
        result['pages'] += 1
        try:
            await asyncio.sleep(0.6)
            async with session.get(url, headers={'Authorization': 'Bearer ' + token},
                                   allow_redirects=False, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                remaining = resp.headers.get('X-Credits-Remaining')
                if isinstance(remaining, str) and remaining.isdigit():
                    budget.remaining = result['credits_remaining'] = int(remaining)
                if resp.status != 200:
                    result.update(reason='http_' + str(resp.status),
                                  cooldown_until=cooldown(resp.status, resp.headers, now))
                    break
                body = bytearray()
                async for chunk in resp.content.iter_chunked(65536):
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        raise ValueError('response_too_large')
                payload = json.loads(body)
            position, as_of = payload.get('next_cursor'), parsed_time(payload.get('as_of'))
            last = parsed_time(state.get('as_of'))
            if (not isinstance(position, str) or not position or as_of is None
                    or not now - timedelta(hours=6) < as_of <= now + timedelta(minutes=5)
                    or (last and as_of < last) or 'next' not in payload
                    or not isinstance(payload.get('results'), list)):
                raise ValueError('invalid_delta')
            following = payload['next']
            if following is not None and next_cursor(following, firs) != position:
                raise ValueError('cursor_mismatch')
            if following is not None and position == cursor:
                raise ValueError('cursor_not_advancing')
            records = copy.deepcopy(state['records'])
            tombstones = dict(state.get('tombstones') or {})
            for row in payload['results']:
                if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id']:
                    raise ValueError('invalid_id')
                if parsed_time(row.get('record_updated_at')) is None:
                    raise ValueError('missing_change_time')
                withdrawn_at = parsed_time(tombstones.get(row['id']))
                if withdrawn_at and withdrawn_at >= parsed_time(row['record_updated_at']):
                    continue
                saved = records.get(row['id'])
                if saved and parsed_time(saved['record_updated_at']) > parsed_time(row['record_updated_at']):
                    continue
                withdrawn = row.get('status') == 'cancelled' or row.get('record_archived_at') is not None
                if withdrawn:
                    if row.get('record_archived_at') is not None and parsed_time(row['record_archived_at']) is None:
                        raise ValueError('invalid_withdrawal')
                    records.pop(row['id'], None)
                    tombstones[row['id']] = row['record_updated_at']
                else:
                    if (row.get('affected_fir') not in firs or not isinstance(row.get('text'), str)
                            or row.get('status') not in ('active', 'upcoming', 'expired')):
                        raise ValueError('invalid_row')
                    tombstones.pop(row['id'], None)
                    records[row['id']] = {**{k: row[k] for k in FIELDS if k in row},
                                          '_danger': bool(danger_re.search(row['text'])),
                                          '_closure': bool(closure_re.search(row['text']))}
            # Whole-page atomic advancement. Failed pages keep the previous cursor.
            state.update(records=records, tombstones=tombstones, cursor=position, as_of=payload['as_of'])
            result['reason'] = 'page_budget_reached'
            if following is None:
                result.update(complete=True, available=True, reason='complete_query')
                state['caught_up_at'] = payload['as_of']
                break
        except Exception as exc:
            result['reason'] = 'invalid_response' if isinstance(exc, (ValueError, TypeError, KeyError, AttributeError)) else 'request_failed'
            break
    # Do not score expired/upcoming rows. Retain them in state for future transitions.
    rows = []
    for row in state['records'].values():
        start, end = parsed_time(row.get('effective_start')), parsed_time(row.get('effective_end'))
        if (row.get('status') == 'expired' or (end and end <= now) or (start and start > now)
                or (row.get('status') == 'upcoming' and not start)):
            continue
        rows.append(row)
    result.update(rows=rows, sample_count=len(rows), partial=bool(rows) and not result['complete'])
    if result['complete']:
        result['total'] = len(rows)
        result['reported_count'] = len(rows)
    return result
