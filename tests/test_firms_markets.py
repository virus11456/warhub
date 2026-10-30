import asyncio
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fetch_data as f
import firms_baseline as fb
import scoring as sc

NOW = datetime(2026, 10, 29, 18, 0, tzinfo=timezone.utc)


def snap(hours_ago, counts, **extra):
    at = (NOW - timedelta(hours=hours_ago)).strftime('%Y-%m-%dT%H:%M:00Z')
    return {'observed_at': at, 'conflict_counts': counts, 'total_24h': 9000, **extra}


def series(n=10, counts=None):
    rows = []
    for i in range(n, 0, -1):
        rows = fb.update(rows, snap(i * 4, counts or {'ukraine': 100, 'russia': 100}), NOW)
    return rows


class FirmsBaselineTests(unittest.TestCase):
    def test_usual_level_is_50_and_more_than_usual_scores_higher(self):
        s = series()
        self.assertEqual(fb.relative(s, snap(0, {'ukraine': 100, 'russia': 100}), ['ukraine', 'russia'])['score'], 50.0)
        high = fb.relative(s, snap(0, {'ukraine': 200, 'russia': 200}), ['ukraine', 'russia'])
        self.assertGreater(high['score'], 99)
        self.assertEqual(high['baseline'], 200.0)

    def test_absent_label_in_valid_snapshot_is_zero_not_missing(self):
        s = series(counts={'taiwan': 0})
        r = fb.relative(s, snap(0, {}), ['taiwan'])
        self.assertEqual((r['count'], r['score']), (0, 50.0))

    def test_short_stale_failed_or_arealess_input_has_no_score(self):
        self.assertEqual(fb.relative(series(3), snap(0, {'ukraine': 1}), ['ukraine'])['reason'], 'baseline_accumulating')
        for bad in (snap(0, {'ukraine': 1}, stale=True), snap(0, {'ukraine': 1}, error='x'),
                    {'conflict_counts': {'ukraine': 1}}, snap(0, {'ukraine': -1}), None):
            self.assertIsNone(fb.relative(series(), bad, ['ukraine'])['score'])
        self.assertEqual(fb.relative(series(), snap(0, {}), [])['reason'], 'no_fire_area')

    def test_series_dedupes_by_acquisition_time_and_drops_old_rows(self):
        s = fb.update(series(), snap(4, {'ukraine': 999}), NOW)       # same acquisition time replaces, no duplicate
        self.assertEqual(len(s), 10)
        old = fb.update([{'at': (NOW - timedelta(days=8)).isoformat(), 'counts': {'ukraine': 1}}], None, NOW)
        self.assertEqual(old, [])
        self.assertEqual(fb.update(s, snap(0, {'ukraine': 1}, stale=True), NOW), s)  # carried-over data is not a sample

    def test_wpi_f_is_mean_of_regional_relative_scores(self):
        firms = {'relative': {'ukraine': {'score': 70}, 'korea': {'score': 30}, 'taiwan': {'score': None}}}
        self.assertEqual(sc.calculate_wpi(None, [], firms=firms)['factors']['f'], 50.0)
        self.assertIsNone(sc.calculate_wpi(None, [], firms={**firms, 'stale': True})['factors']['f'])
        self.assertIsNone(sc.calculate_wpi(None, [], firms={'relative': {'ukraine': {'score': None}}})['factors']['f'])


class Resp:
    def __init__(self, status, body): self.status, self.body = status, body
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass
    def raise_for_status(self):
        if self.status != 200: raise RuntimeError(self.status)
    async def json(self, **kw): return self.body


def gamma(question, yes='0.05', cid=None, **extra):
    return {'conditionId': cid or question, 'question': question, 'outcomes': '["Yes","No"]',
            'outcomePrices': f'["{yes}","{1 - float(yes):.4f}"]', 'volume': '1000', 'endDate': '2099-01-01T00:00:00Z',
            'active': True, 'closed': False, **extra}


class Session:
    def __init__(self, tag_ok=True, search_status=200):
        self.tag_ok, self.search_status, self.queries = tag_ok, search_status, []
    def get(self, url, params=None, **kw):
        if url.endswith('/tags/slug/geopolitics'):
            return Resp(200 if self.tag_ok else 500, {'id': 1})
        if url == f.POLYMARKET_SEARCH:
            self.queries.append(params['q'])
            events = {'taiwan': [{'markets': [gamma('China x Taiwan military clash before 2027?'),
                                             gamma('Will China blockade Taiwan in 2026?', closed=True),
                                             gamma('Lai Ching-te out as President of Taiwan by December 31, 2026?'),
                                             gamma('Will Russia invade Ukraine?', cid='dup')]}]}.get(params['q'], [])
            return Resp(self.search_status, {'events': events})
        return Resp(200, [gamma('Will Russia invade Ukraine?', cid='dup')])


class RegionSearchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        async def no_translate(session, rows): pass
        self.orig, f._translate_market_questions = f._translate_market_questions, no_translate
    async def asyncTearDown(self):
        f._translate_market_questions = self.orig

    async def test_region_search_adds_open_conflict_markets_once(self):
        s = Session()
        rows = await f.fetch_polymarket(s)
        self.assertEqual(sorted(s.queries), ['north korea', 'philippines', 'south china sea', 'taiwan'])
        self.assertEqual([r['question'] for r in rows], ['Will Russia invade Ukraine?', 'China x Taiwan military clash before 2027?'])
        taiwan = next(r for r in f.build_region_risks(rows, {}, {'error': 'x'}, {'error': 'x'}) if r['key'] == 'taiwan')
        self.assertEqual(taiwan['factors']['poly'], 5.0)
        self.assertNotIn('no_market', taiwan['factors'])

    async def test_failed_search_keeps_main_list_and_failed_main_list_returns_empty(self):
        self.assertEqual(len(await f.fetch_polymarket(Session(search_status=503))), 1)
        self.assertEqual(await f.fetch_polymarket(Session(tag_ok=False)), [])


if __name__ == '__main__':
    unittest.main()
