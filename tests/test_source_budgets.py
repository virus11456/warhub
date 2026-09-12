from datetime import datetime, timezone, timedelta
import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from contextlib import ExitStack
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fetch_data as f
REAL_SLEEP = asyncio.sleep

class Response:
    def __init__(self, session, status, payload, hang=False):
        self.session, self.status, self.payload, self.hang = session, status, payload, hang
    async def __aenter__(self):
        if self.hang:
            try: await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.session.cancelled = True
                raise
        return self
    async def __aexit__(self, *args): pass
    def raise_for_status(self):
        if self.status >= 400: raise RuntimeError('HTTP error')
    async def text(self): return json.dumps(self.payload)
    async def json(self, **kwargs): return self.payload

class Session:
    def __init__(self, status=200, hang_after=None):
        self.status, self.hang_after, self.calls, self.cancelled = status, hang_after, 0, False
    def request(self, *args, **kwargs):
        self.calls += 1
        payload={'timeline':[{'data':[{'value':1,'date':(datetime.now(timezone.utc)-timedelta(minutes=15*i)).strftime('%Y%m%dT%H%M%SZ')} for i in range(6)]}], 'notamList':[]}
        return Response(self, self.status, payload, self.hang_after is not None and self.calls > self.hang_after)
    get = post = request

class SourceBudgets(unittest.IsolatedAsyncioTestCase):
    def test_rotation_gives_each_region_a_first_position(self):
        mapping={str(n):n for n in range(5)}
        orders=[f.source_region_order(mapping,slot=n) for n in range(5)]
        self.assertEqual({order[0][0] for order in orders},set(mapping))
        self.assertTrue(all(dict(order)==mapping for order in orders))
        self.assertEqual(f.source_region_order({},slot=0),[])

    def setup_source(self, stack, td):
        old={'observed_at':'2000-01-01T00:00:00+00:00', 'latest':9, 'danger':2, 'score':16}
        path=Path(td)/'data.json'
        path.write_text(json.dumps({k:{'a':old,'b':old} for k in ['gdelt','notams']}))
        stack.enter_context(patch.object(f,'DATA_FILE',path))
        stack.enter_context(patch.object(f,'REGIONS',{'a':{'gdelt_q':'a'},'b':{'gdelt_q':'b'}}))
        stack.enter_context(patch.object(f,'REGION_FIRS',{'a':['AAAA'],'b':['BBBB']}))
        stack.enter_context(patch.object(f.asyncio,'sleep',AsyncMock()))
        stack.enter_context(patch.object(f,'source_region_order',lambda mapping:list(mapping.items())))
        return old

    async def test_denial_and_rate_limit_stop_source_after_one_request(self):
        for fn in (f.fetch_gdelt, f.fetch_notams):
            for status in (401,403,429):
                with self.subTest(source=fn.__name__,status=status), tempfile.TemporaryDirectory() as td, ExitStack() as stack:
                    old=self.setup_source(stack,td)
                    session=Session(status)
                    out=await fn(session)
                    self.assertEqual(session.calls,1)
                    self.assertEqual(set(out),{'a','b'})
                    for row in out.values(): self.assertEqual({k:v for k,v in row.items() if k!='cooldown_until'},{**old,'stale':True})

    async def test_timeout_keeps_completed_region_and_cancels_pending_request(self):
        for fn,budget in [(f.fetch_gdelt,'GDELT_BUDGET_SECONDS'),(f.fetch_notams,'NOTAM_BUDGET_SECONDS')]:
            with self.subTest(source=fn.__name__), tempfile.TemporaryDirectory() as td, ExitStack() as stack:
                old=self.setup_source(stack,td)
                stack.enter_context(patch.object(f,budget,0.02))
                session=Session(hang_after=1)
                out=await fn(session)
                self.assertTrue(session.cancelled)
                self.assertFalse(out['a'].get('stale',False))
                self.assertEqual(out['b'],{**old,'stale':True})
                self.assertEqual(session.calls,2)

    async def test_successful_source_still_collects_all_regions(self):
        for fn in (f.fetch_gdelt,f.fetch_notams):
            with self.subTest(source=fn.__name__), tempfile.TemporaryDirectory() as td, ExitStack() as stack:
                self.setup_source(stack,td)
                session=Session()
                out=await fn(session)
                self.assertEqual(session.calls,2)
                self.assertEqual(set(out),{'a','b'})
                self.assertTrue(all(not row.get('stale') for row in out.values()))

    async def test_timeout_during_pacing_keeps_completed_region(self):
        for fn,budget in [(f.fetch_gdelt,'GDELT_BUDGET_SECONDS'),(f.fetch_notams,'NOTAM_BUDGET_SECONDS')]:
            with self.subTest(source=fn.__name__), tempfile.TemporaryDirectory() as td, ExitStack() as stack:
                old=self.setup_source(stack,td)
                stack.enter_context(patch.object(f.asyncio,'sleep',REAL_SLEEP))
                stack.enter_context(patch.object(f,budget,0.02))
                session=Session()
                out=await fn(session)
                self.assertEqual(session.calls,1)
                self.assertFalse(out['a'].get('stale',False))
                self.assertEqual(out['b'],{**old,'stale':True})
