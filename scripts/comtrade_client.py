"""Shared, bounded Comtrade transport; credentials never enter URLs or reports."""
import asyncio
import math
import os
import time
import weakref
from datetime import datetime, timezone, timedelta
import aiohttp

STATES = weakref.WeakKeyDictionary()

class Client:
    def __init__(self, saved=None):
        self.key = os.getenv('COMTRADE_API_KEY', '').strip()
        self.lock = asyncio.Lock()
        self.last = None
        self.started = None
        self.requests = 0
        self.successes = 0
        self.status = 'not_queried'
        self.cooldown_until = (saved or {}).get('cooldown_until')
        self.stopped = False

    def report(self):
        return {'mode': 'authenticated' if self.key else 'public_preview',
                'status': self.status, 'requests': self.requests,
                'successes': self.successes, 'cooldown_until': self.cooldown_until}

    async def query(self, session, params):
        async with self.lock:
            now = datetime.now(timezone.utc)
            try:
                if now < datetime.fromisoformat(self.cooldown_until):
                    self.status = 'cooldown'; return None
            except (TypeError, ValueError):
                pass
            if self.stopped:
                return None
            if self.requests >= 80 or (self.started is not None and time.monotonic() - self.started >= 180):
                self.status = 'budget_exhausted'; return None
            if self.last is not None:
                await asyncio.sleep(max(0, 3 - (time.monotonic() - self.last)))
            self.started = self.started if self.started is not None else time.monotonic()
            self.last = time.monotonic()
            self.requests += 1
            endpoint = 'data/v1/get' if self.key else 'public/v1/preview'
            headers = {'Accept': 'application/json'}
            if self.key:
                headers['Ocp-Apim-Subscription-Key'] = self.key
            query = {**params, 'customsCode': 'C00', 'maxRecords': '500'}
            try:
                async with session.get('https://comtradeapi.un.org/' + endpoint + '/C/M/HS',
                                       params=query, headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status in (401, 403, 429):
                        self.stopped = True
                        self.status = 'rate_limited' if response.status == 429 else 'access_denied'
                        try:
                            seconds = max(60, min(86400, int(response.headers.get('Retry-After', '3600'))))
                        except (TypeError, ValueError):
                            seconds = 3600
                        self.cooldown_until = (now + timedelta(seconds=seconds)).isoformat()
                        return None
                    response.raise_for_status()
                    body = await response.json(content_type=None)
                weights = parse_weights(body, query)
                self.successes += 1
                self.status = 'available' if weights else 'empty'
                return weights
            except (aiohttp.ClientError, TimeoutError, ValueError, TypeError, AttributeError):
                self.status = 'request_failed'
                self.stopped = True
                return None


def parse_weights(body, params):
    rows = body.get('data')
    if body.get('error') or not isinstance(rows, list) or len(rows) >= 500:
        raise ValueError('invalid_or_truncated_response')
    expected = set(params['cmdCode'].split(','))
    result = {}
    seen = set()
    for row in rows:
        cmd = str(row.get('cmdCode'))
        if cmd not in expected or any(str(row.get(k)) != str(params[k]) for k in
                ('reporterCode', 'period', 'flowCode', 'partnerCode', 'partner2Code', 'motCode', 'customsCode')):
            raise ValueError('wrong_scope')
        if cmd in seen:
            raise ValueError('duplicate_aggregate')
        seen.add(cmd)
        weight = row.get('netWgt')
        if weight is None:
            continue
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight) or weight < 0:
            raise ValueError('invalid_weight')
        result[cmd] = weight
    return result


def setup(session, saved=None):
    client = Client(saved)
    STATES[session] = client
    return client

async def weights(session, params):
    client = STATES.get(session)
    if client is None:
        client = setup(session)
    return await client.query(session, params)
