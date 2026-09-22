"""Bounded read-only public Kalshi client. Tests use mock sessions."""
import asyncio
from copy import deepcopy
import json
import re
from datetime import datetime, timedelta, timezone
import aiohttp
from kalshi_market_data import select_markets, timestamp

BASE='https://external-api.kalshi.com/trade-api/v2/markets'
MAX_REQUESTS=3
MAX_BYTES=2_000_000


async def collect(session, series_tickers, *, authorized=False, now=None, include_background=False):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Timezone-aware now required')
    at=now.astimezone(timezone.utc).isoformat()
    result={'provider':'kalshi','attempted_at':None,'fetched_at':None,
            'status':'authorization_pending','markets':[], 'complete':False,
            'requests':0,'series_completed':[], 'retry_at':None}
    if authorized is not True:
        return result
    series=list(dict.fromkeys(series_tickers))
    if not series or len(series)>3 or any(not isinstance(t,str) or not re.fullmatch(r'[A-Z0-9_-]{1,80}',t) for t in series):
        raise ValueError('Provide one to three explicitly selected series')
    result['attempted_at']=at
    raw=[]
    reason=None
    for ticker in series:
        cursor=None
        seen_cursors=set()
        while result['requests']<MAX_REQUESTS:
            params={'series_ticker':ticker,'status':'open','limit':100}
            if cursor:params['cursor']=cursor
            if result['requests']:
                await asyncio.sleep(1)
            result['requests']+=1
            try:
                async with session.get(BASE,params=params,timeout=aiohttp.ClientTimeout(total=15),allow_redirects=False) as response:
                    if response.status in (401,403,429):
                        reason='rate_limited' if response.status==429 else 'access_denied'
                        if response.status==429:
                            delay=response.headers.get('Retry-After','60')
                            seconds=int(delay) if str(delay).isdigit() else 60
                            result['retry_at']=(now+timedelta(seconds=max(60,min(seconds,86400)))).isoformat()
                        break
                    if response.status!=200:
                        reason='http_error';break
                    body=bytearray()
                    async for chunk in response.content.iter_chunked(65536):
                        body.extend(chunk)
                        if len(body)>MAX_BYTES:raise ValueError('Response too large')
                    payload=json.loads(body)
                    if not isinstance(payload,dict) or not isinstance(payload.get('markets'),list):
                        raise ValueError('Invalid market page')
                    next_cursor=payload.get('cursor')
                    if next_cursor is not None and (not isinstance(next_cursor,str) or len(next_cursor)>2048):
                        raise ValueError('Invalid cursor')
                    if next_cursor and next_cursor in seen_cursors:
                        raise ValueError('Repeated cursor')
                    # Validate page shape before retaining any part of it.
                    if any(not isinstance(m,dict) or not isinstance(m.get('ticker'),str) for m in payload['markets']):
                        raise ValueError('Invalid market record')
                    raw.extend(payload['markets'])
                    if not next_cursor:
                        result['series_completed'].append(ticker);break
                    seen_cursors.add(next_cursor);cursor=next_cursor
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError):
                reason='invalid_or_unavailable';break
        if reason:break
        if ticker not in result['series_completed']:
            reason='page_budget';break
    if not reason and len(result['series_completed'])<len(series):reason='page_budget'
    result['markets']=select_markets(raw,at,include_background=include_background)
    result['complete']=len(result['series_completed'])==len(series) and reason is None
    result['status']='available' if result['complete'] else ('partial' if raw else 'unavailable')
    result['reason']=reason
    result['fetched_at']=at if result['complete'] or raw else None
    return result


async def refresh(session, series_tickers, previous=None, *, authorized=False, now=None, include_background=False):
    """Keep source times intact across throttling, failures and cached reads.

    History is supplied by the existing immutable snapshot archiver; this helper
    never changes the previous object or invents new observations from old prices.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Timezone-aware now required')
    previous = previous if isinstance(previous, dict) else {}
    if not authorized:
        return await collect(session, series_tickers, now=now)
    retry = timestamp(previous.get('retry_at'))
    attempted = timestamp(previous.get('attempted_at'))
    fetched = timestamp(previous.get('fetched_at'))
    # Retry-After survives process restarts. Failed attempts also respect cadence.
    cooling = retry is not None and retry > now
    recent = attempted is not None and 0 <= (now-attempted).total_seconds() < 6600
    if cooling or recent:
        result = deepcopy(previous)
        result['requests'] = 0
        result['reused'] = True
        result['reuse_reason'] = 'rate_limit_cooldown' if cooling else 'collection_interval'
        if fetched is not None and (now-fetched).total_seconds() >= 21600:
            result['status'] = 'stale'
        return result
    result = await collect(session, series_tickers, authorized=True, now=now, include_background=include_background)
    result['reused'] = False
    result['scope'] = {'series': list(dict.fromkeys(series_tickers)), 'all_platform_markets': False}
    if result['fetched_at'] is None and fetched is not None and fetched <= now:
        result['markets'] = deepcopy(previous.get('markets') or [])
        result['fetched_at'] = previous['fetched_at']
        result['status'] = 'stale'
        result['reused'] = True
    return result
