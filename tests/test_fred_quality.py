import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from fred_quality import parse_observation
from data_quality import source_health
import fetch_data as fd


class FredTests(unittest.TestCase):
    def test_observation_date_is_not_fetch_date(self):
        row = parse_observation({'observations': [{'date':'2026-09-10','value':'0'}]},
                                datetime(2026,9,12,tzinfo=timezone.utc))
        self.assertEqual(row['value'], 0)
        self.assertEqual(row['observation_date'], '2026-09-10')
        self.assertTrue(row['fetched_at'].startswith('2026-09-12'))

    def test_missing_is_not_zero(self):
        for value in ('.', '', None):
            row = parse_observation({'observations': [{'date':'2026-09-10','value':value}]})
            self.assertIsNone(row['value'])
            self.assertEqual(row['status'], 'missing')

    def test_reject_invalid_values_and_dates(self):
        for date, value in [('2099-01-01','1'), ('bad','1'), ('2026-09-10','NaN'),
                            ('2026-09-10','inf'), ('2026-09-10', True)]:
            with self.assertRaises(ValueError):
                parse_observation({'observations': [{'date':date,'value':value}]})

    def test_health_requires_dates_and_lists_both_dates(self):
        health = source_health({'fred': {'em_oas':1,'hy_oas':2}})['fred']
        self.assertEqual(health['status'], 'unavailable')
        fred = {'em_oas':1,'hy_oas':2,'observations': {
            'em_oas': {'observation_date':'2026-09-10'}, 'hy_oas': {'observation_date':'2026-09-11'}}}
        health = source_health({'fred':fred})['fred']
        self.assertEqual(health['status'], 'available')
        self.assertIn('2026-09-10、2026-09-11', health['note'])


class FredFetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_failure_log_does_not_include_request_secret(self):
        class Session:
            def get(self, *a, **kw):
                raise RuntimeError('https://example.test/?api_key=TEST_PRIVATE_VALUE')
        with patch.object(fd, 'FRED_API_KEY', 'TEST_PRIVATE_VALUE'), self.assertLogs(fd.log, 'WARNING') as logs:
            result = await fd.fetch_fred(Session())
        self.assertNotIn('TEST_PRIVATE_VALUE', str(logs.output))
        self.assertIsNone(result['em_oas'])
        self.assertEqual(result['observations']['em_oas']['status'], 'unavailable')

    async def test_collector_preserves_value_and_official_metadata(self):
        class Response:
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
            def raise_for_status(self): pass
            async def json(self,**kw):
                return {'observations': [{'date':'2026-09-10','value':'1.31'}]}
        class Session:
            def get(self,*args,**kw): return Response()
        with patch.object(fd,'FRED_API_KEY','test'):
            result = await fd.fetch_fred(Session())
        self.assertEqual(result['em_oas'], 1.31)
        self.assertEqual(result['observations']['em_oas']['observation_date'], '2026-09-10')
