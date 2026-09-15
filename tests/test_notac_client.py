"""Synthetic protocol fixtures only; never contact NOTAC."""
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import notac_client as n


class Response:
    def __init__(self, payload, status=200, headers=None):
        self.payload, self.status, self.headers = payload, status, headers or {}
        self.content = self
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False
    async def iter_chunked(self, size): yield json.dumps(self.payload).encode()


class Session:
    def __init__(self, *responses): self.responses, self.calls = list(responses), []
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def row(identity='fixture'):
    return {'id': identity, 'status': 'active', 'affected_fir': 'RCAA', 'text': 'SYNTHETIC TEST'}


NEXT = n.BASE + '?fir=RCAA&status=active&sort=newest&page=2'


class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_candidates_describe_sample_only_and_archive_original_times(self):
        import re
        import tempfile
        import gzip
        now=datetime(2026,9,15,tzinfo=timezone.utc)
        notice={**row(), 'text':'DANGER AREA', 'effective_start':'2026-09-14T00:00:00Z'}
        payload={'provider':'NOTAC','firs':['RCAA'],'fetched_at':now.isoformat(),'rows':[notice],
                 'complete':False,'partial':True,'sample_count':1,'reported_count':600,'reason':'page_budget_reached'}
        previous={'taiwan':{'provider':'FAA','observed_at':'2020-01-01T00:00:00Z','total':7}}
        with tempfile.TemporaryDirectory() as folder, patch.object(n,'collect_region',AsyncMock(return_value=payload)):
            result=await n.collect_regions(Session(),'fixture',{'taiwan':['RCAA']},previous,re.compile('DANGER'),re.compile('CLOSED'),folder,now)
            result=result['taiwan']
            self.assertEqual(result['total'],7)
            self.assertEqual(result['observed_provider'],'FAA')
            self.assertTrue(result['stale'])
            self.assertEqual(result['latest_attempt']['sample_danger'],1)
            self.assertEqual(result['latest_attempt']['sample_closure'],0)
            saved=json.loads(gzip.decompress(next(Path(folder).rglob('*.gz')).read_bytes()))
            self.assertEqual(saved['rows'][0]['effective_start'],notice['effective_start'])
            self.assertNotIn('text',saved['rows'][0])
            self.assertEqual(result['latest_attempt']['sample_timing']['unknown'],1)

    async def test_active_query_does_not_mean_all_notices_are_effective_now(self):
        import re
        now=datetime(2026,9,15,tzinfo=timezone.utc)
        rows=[{**row('current'),'effective_start':'2026-09-14T00:00:00Z','effective_end':'2026-09-16T00:00:00Z'},
              {**row('future'),'effective_start':'2026-09-16T00:00:00Z','effective_end':'2026-09-17T00:00:00Z'},
              {**row('ended'),'effective_start':'2026-09-13T00:00:00Z','effective_end':'2026-09-14T00:00:00Z'},
              {**row('unknown'),'effective_start':'2026-09-14T00:00:00','effective_end':None}]
        r={'provider':'NOTAC','firs':['RCAA'],'fetched_at':now.isoformat(),'rows':rows,'complete':True,'total':4,'sample_count':4}
        with patch.object(n,'collect_region',AsyncMock(return_value=r)):
            out=await n.collect_regions(Session(),'fixture',{'taiwan':['RCAA']},{},re.compile('DANGER'),re.compile('CLOSED'),now=now)
        self.assertEqual(out['taiwan']['sample_timing'],{'current':1,'future':1,'ended':1,'unknown':1})
    async def test_missing_key_no_request(self):
        s = Session()
        r = await n.collect_region(s, '', ['RCAA'])
        self.assertIsNone(r['total'])
        self.assertFalse(s.calls)

    async def test_valid_empty_is_zero_and_token_not_in_url(self):
        s = Session(Response({'count': 0, 'next': None, 'results': []}))
        r = await n.collect_region(s, 'fixture-token', ['RCAA'])
        self.assertEqual(r['total'], 0)
        self.assertTrue(r['complete'])
        self.assertNotIn('fixture-token', s.calls[0][0])
        self.assertFalse(s.calls[0][1]['allow_redirects'])

    async def test_incomplete_count_is_not_complete(self):
        s = Session(Response({'count': 37, 'next': None, 'results': [row()]}))
        r = await n.collect_region(s, 'fixture-token', ['RCAA'])
        self.assertIsNone(r['total'])
        self.assertTrue(r['partial'])

    async def test_two_pages_then_stop_without_partial_zero(self):
        s = Session(Response({'count': 3, 'next': NEXT, 'results': [row('a')]}),
                    Response({'count': 3, 'next': NEXT.replace('page=2', 'page=3'), 'results': [row('b')]}))
        with patch.object(n.asyncio, 'sleep', AsyncMock()):
            r = await n.collect_region(s, 'fixture-token', ['RCAA'])
        self.assertEqual(len(s.calls), 2)
        self.assertEqual(r['sample_count'], 2)
        self.assertIsNone(r['total'])
        self.assertEqual(r['reason'], 'page_budget_reached')

    async def test_next_must_preserve_host_path_and_filters(self):
        for url in [NEXT.replace('notac.aero', 'example.com'), NEXT.replace('active', 'any'),
                    NEXT.replace('RCAA', 'EGLL'), NEXT + '&key=fixture-token', NEXT.replace('https:', 'http:')]:
            s = Session(Response({'count': 2, 'next': url, 'results': [row()]}))
            r = await n.collect_region(s, 'fixture-token', ['RCAA'])
            self.assertFalse(r['complete'])
            self.assertEqual(len(s.calls), 1)

    async def test_http_error_no_retry_and_respects_cooldown(self):
        now = datetime(2026, 12, 31, tzinfo=timezone.utc)
        for code in (401, 402, 403, 429):
            s = Session(Response({'private': 'never print this'}, code, {'Retry-After': '3600'}))
            r = await n.collect_region(s, 'fixture-token', ['RCAA'], now)
            self.assertEqual(len(s.calls), 1)
            self.assertEqual(r['reason'], 'http_' + str(code))
            self.assertNotIn('fixture-token', json.dumps(r))
            self.assertNotIn('private', json.dumps(r))
            self.assertIsNone(r['total'])
            if code == 402: self.assertEqual(r['cooldown_until'], '2027-01-01T00:00:00+00:00')

    async def test_duplicate_row_or_wrong_fir_rejected(self):
        for rows in [[row(), row()], [{**row(), 'affected_fir': 'EGLL'}]]:
            r = await n.collect_region(Session(Response({'count': len(rows), 'next': None, 'results': rows})),
                                       'fixture-token', ['RCAA'])
            self.assertFalse(r['complete'])

    async def test_complete_two_pages_preserves_original_fields(self):
        first = {**row('a'), 'effective_start': '2026-09-15T00:00:00Z'}
        s = Session(Response({'count': 2, 'next': NEXT, 'results': [first]}),
                    Response({'count': 2, 'next': None, 'results': [row('b')]}))
        with patch.object(n.asyncio, 'sleep', AsyncMock()):
            r = await n.collect_region(s, 'fixture-token', ['RCAA'])
        self.assertTrue(r['complete'])
        self.assertEqual(r['rows'][0], first)

    async def test_low_credits_stops_before_second_page(self):
        s = Session(Response({'count': 2, 'next': NEXT, 'results': [row()]}, headers={'X-Credits-Remaining': '1'}))
        r = await n.collect_region(s, 'fixture-token', ['RCAA'])
        self.assertEqual(r['reason'], 'credits_low')
        self.assertEqual(len(s.calls), 1)

class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_cooldown_shared_and_original_observation_retained(self):
        import re
        now = datetime(2026, 9, 15, tzinfo=timezone.utc)
        old = {'provider':'NOTAC','observed_at':'2026-09-14T00:00:00Z','total':4,'score':8}
        s=Session(Response({},429,{'Retry-After':'3600'}))
        r=await n.collect_regions(s,'fixture-token',{'a':['RCAA'],'b':['EGLL']},{'a':old},re.compile('DANGER'),re.compile('CLOSED'),now=now)
        self.assertEqual(len(s.calls),1)
        self.assertEqual(r['a']['observed_at'],old['observed_at'])
        self.assertEqual(r['a']['total'],4)
        self.assertTrue(r['a']['stale'])
        self.assertTrue(r['b']['cooldown_until'])
        s2=Session()
        r2=await n.collect_regions(s2,'fixture-token',{'a':['RCAA'],'b':['EGLL']},r,re.compile('DANGER'),re.compile('CLOSED'),now=now)
        self.assertFalse(s2.calls)

    async def test_full_zero_and_immutable_metadata_archive(self):
        import re,tempfile,gzip
        now=datetime(2026,9,15,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            s=Session(Response({'count':0,'results':[],'next':None}))
            r=await n.collect_regions(s,'fixture-token',{'a':['RCAA']},{},re.compile('DANGER'),re.compile('CLOSED'),directory,now)
            self.assertEqual(r['a']['total'],0)
            self.assertEqual(r['a']['score'],0)
            self.assertFalse(r['a']['stale'])
            files=list(Path(directory).rglob('*.gz'))
            self.assertEqual(len(files),1)
            archive=json.loads(gzip.decompress(files[0].read_bytes()))
            self.assertEqual(archive['kind'],'source_observation')
            self.assertNotIn('fixture-token',json.dumps(archive))

    async def test_new_source_not_compared_to_faa_and_partial_not_scored(self):
        import re
        s=Session(Response({'count':37,'results':[row()],'next':None}))
        old={'observed_at':'2026-09-14T00:00:00Z','total':7,'score':8}
        r=await n.collect_regions(s,'fixture-token',{'a':['RCAA']},{'a':old},re.compile('DANGER'),re.compile('CLOSED'))
        self.assertTrue(r['a']['stale'])
        self.assertEqual(r['a']['total'],7)
        self.assertNotIn('comparison',r['a'])
        self.assertTrue(r['a']['latest_attempt']['partial'])
