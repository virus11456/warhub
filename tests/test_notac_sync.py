import copy
import re
import sys
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import notac_sync as s
import notac_client as n
from test_notac_client import Session, Response

NOW = datetime(2026, 9, 22, 10, tzinfo=timezone.utc)
def row(i, **extra):
    return dict(id=i, affected_fir='RCAA', status='active', text='DANGER SYNTHETIC',
                record_updated_at='2026-09-22T09:00:00Z',
                effective_start='2026-09-21T00:00:00Z',
                effective_end='2026-09-23T00:00:00Z', **extra)
def page(rows, cursor, more=False):
    return {'results': rows, 'next_cursor': cursor, 'as_of': NOW.isoformat(),
            'next': s.BASE+'?fir=RCAA&cursor='+cursor if more else None}

class Tests(unittest.IsolatedAsyncioTestCase):
    async def collect(self, session, old=None, budget=None):
        with patch.object(s.asyncio, 'sleep', AsyncMock()):
            return await s.collect_delta(session, 'fixture', ['RCAA'], old or {},
                budget or s.Budget({}, NOW), re.compile('DANGER'), re.compile('CLOSED'), NOW)

    async def test_resume_across_runs_then_revision_and_withdrawal(self):
        first = await self.collect(Session(Response(page([row('a')], 'p1', True)),
                                           Response(page([row('b')], 'p2', True))))
        self.assertFalse(first['complete'])
        self.assertEqual(first['sample_count'], 2)
        before = copy.deepcopy(first)
        session = Session(Response(page([row('b'), row('c')], 'p3')))
        full = await self.collect(session, first)
        self.assertIn('cursor=p2', session.calls[0][0])
        self.assertEqual(full['total'], 3)
        self.assertEqual(first, before)
        revised = row('c'); revised['text'] = 'NORMAL'; revised['record_updated_at'] = '2026-09-22T09:30:00Z'
        withdrawn = {'id': 'a', 'status': 'cancelled', 'record_archived_at': NOW.isoformat(), 'record_updated_at': NOW.isoformat()}
        updated = await self.collect(Session(Response(page([withdrawn, revised], 'p4'))), full)
        self.assertEqual(updated['total'], 2)
        self.assertFalse(updated['sync_state']['records']['c']['_danger'])
        self.assertNotIn('text', updated['sync_state']['records']['c'])
        replayed = await self.collect(Session(Response(page([row('a')], 'p5'))), updated)
        self.assertEqual(replayed['total'], 2)

    async def test_failed_page_does_not_advance_cursor_or_mutate_records(self):
        good = page([row('a')], 'p1', True)
        bad = page([row('b'), {'id': 'bad'}], 'p2')
        out = await self.collect(Session(Response(good), Response(bad)))
        self.assertFalse(out['complete'])
        self.assertEqual(out['sync_state']['cursor'], 'p1')
        self.assertEqual(list(out['sync_state']['records']), ['a'])

    async def test_unsafe_next_never_requested(self):
        p = page([row('a')], 'p1', True); p['next'] = p['next'].replace('notac.aero', 'evil.test')
        session = Session(Response(p))
        out = await self.collect(session)
        self.assertEqual(len(session.calls), 1)
        self.assertFalse(out['complete'])
        self.assertIsNone(out['sync_state']['cursor'])

    async def test_empty_complete_zero_and_expired_excluded(self):
        r = row('expired'); r['effective_end'] = '2026-09-22T08:00:00Z'
        out = await self.collect(Session(Response(page([r], 'p1'))))
        self.assertTrue(out['complete']); self.assertEqual(out['total'], 0)

    async def test_daily_monthly_run_budget_and_low_credit(self):
        for field, value in [('day_calls', s.PER_DAY), ('month_calls', s.PER_MONTH)]:
            old = {'sync_budget': {'day': NOW.date().isoformat(), 'month': NOW.strftime('%Y-%m'), field: value}}
            budget = s.Budget({'a': old}, NOW); session = Session()
            out = await self.collect(session, old, budget)
            self.assertFalse(session.calls); self.assertFalse(out['complete'])
        budget = s.Budget({}, NOW); budget.used_run = s.PER_RUN
        session = Session(); await self.collect(session, budget=budget); self.assertFalse(session.calls)
        session = Session(Response(page([], 'p1', True), headers={'X-Credits-Remaining':'22'}))
        out = await self.collect(session); self.assertEqual(len(session.calls), 1)
        self.assertFalse(out['complete']); self.assertEqual(out['sync_budget']['day_calls'], 1)

    async def test_http_failure_counts_and_does_not_leak_body(self):
        out = await self.collect(Session(Response({'private': 'secret'}, 429, {'Retry-After':'100'})))
        self.assertEqual(out['sync_budget']['day_calls'], 1)
        self.assertTrue(out['cooldown_until']); self.assertNotIn('secret', str(out))

    async def test_integrated_partial_state_and_old_observation_retained(self):
        previous={'taiwan': {'provider':'NOTAC','observed_at':'2026-09-21T00:00:00Z','total':5,'score':8}}
        session=Session(Response(page([row('a')], 'p1', True)),Response(page([row('b')], 'p2', True)))
        with patch.object(s.asyncio,'sleep',AsyncMock()):
            out=await n.collect_regions(session,'fixture',{'taiwan':['RCAA']},previous,re.compile('DANGER'),re.compile('CLOSED'),now=NOW,incremental=True)
        r=out['taiwan']; self.assertTrue(r['stale']); self.assertEqual(r['total'],5)
        self.assertEqual(r['observed_at'],previous['taiwan']['observed_at'])
        self.assertEqual(r['sync_state']['cursor'],'p2')
        self.assertEqual(r['latest_attempt']['sample_danger'],2)
        self.assertNotIn('sync_state',r['latest_attempt'])
        later=NOW+timedelta(hours=2)
        final=page([], 'p3'); final['as_of']=later.isoformat()
        with patch.object(s.asyncio,'sleep',AsyncMock()):
            out2=await n.collect_regions(Session(Response(final)),'fixture',{'taiwan':['RCAA']},out,re.compile('DANGER'),re.compile('CLOSED'),now=later,incremental=True)
        self.assertFalse(out2['taiwan']['stale']); self.assertEqual(out2['taiwan']['total'],2)

    async def test_stale_server_clock_does_not_publish_fresh_score(self):
        p=page([], 'p1');p['as_of']=(NOW-timedelta(hours=7)).isoformat()
        out=await self.collect(Session(Response(p)))
        self.assertFalse(out['complete']);self.assertIsNone(out['total'])

    async def test_budget_rollover_does_not_carry_previous_month_usage(self):
        old={'sync_budget':{'day':'2026-08-31','month':'2026-08','day_calls':90,'month_calls':2800}}
        out=await self.collect(Session(Response(page([], 'p1'))),old,s.Budget({'a':old},NOW))
        self.assertTrue(out['complete']);self.assertEqual(out['sync_budget']['month_calls'],1)
