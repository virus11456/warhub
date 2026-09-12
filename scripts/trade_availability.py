"""Bounded public dataset-catalog checks, never proof of commodity-level coverage."""
import asyncio
import time
import weakref
from datetime import datetime, timezone
import aiohttp

URL='https://comtradeapi.un.org/public/v1/getDA/C/M/HS'
STATES=weakref.WeakKeyDictionary()
MAX_REQUESTS=4
LIMIT=512

class Availability:
    def __init__(self, saved=None):
        self.cache=dict(saved or {})
        self.requests=0
        self.stopped=False
        self.elapsed=0
        self.lock=asyncio.Lock()
    async def query(self,session,reporter,period):
        key=f'{reporter}:{period}'
        async with self.lock:
            now=datetime.now(timezone.utc)
            row=self.cache.get(key,{})
            try:
                age=(now-datetime.fromisoformat(row['checked_at'])).total_seconds()
                ttl=86400 if row['status']=='available' else 21600
                if 0<=age<ttl:return row['status']!='not_listed'
            except (KeyError,TypeError,ValueError):pass
            # Expired negative cache must never suppress a source request.
            if self.stopped or self.requests>=MAX_REQUESTS or self.elapsed>=16:return True
            self.requests+=1
            started=time.monotonic()
            status='unknown'
            try:
                async with session.get(URL,params={'reporterCode':str(reporter),'period':str(period)},
                     timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status in (401,403,429):self.stopped=True
                    response.raise_for_status()
                    body=await response.json(content_type=None)
                rows=body.get('data')
                if body.get('error') or not isinstance(rows,list) or body.get('count')!=len(rows):
                    raise ValueError('invalid_catalog')
                if not rows:status='not_listed'
                elif all(str(r.get('reporterCode'))==str(reporter) and str(r.get('period'))==str(period)
                         and r.get('freqCode')=='M' and r.get('typeCode')=='C'
                         and r.get('classificationSearchCode')=='HS' for r in rows):
                    status='available'
                else:raise ValueError('wrong_catalog_scope')
            except (aiohttp.ClientError,TimeoutError,ValueError,TypeError,AttributeError):
                self.stopped=True
            finally:self.elapsed+=time.monotonic()-started
            self.cache.pop(key,None)
            self.cache[key]={'status':status,'checked_at':now.isoformat()}
            self.cache=dict(list(self.cache.items())[-LIMIT:])
            return status!='not_listed'

def setup(session,saved=None):
    state=Availability(saved);STATES[session]=state;return state

async def should_query(session,reporter,period):
    state=STATES.get(session) if session is not None else None
    return await state.query(session,reporter,period) if state else True
