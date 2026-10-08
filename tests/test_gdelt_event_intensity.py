import asyncio
import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fetch_data as collector
import gdelt_event_intensity as gei
from scoring import calculate_wpi

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


def event(eid, articles, quad='4', a1='', a2='', geo='', place=''):
    row = [''] * 61
    row[0], row[33], row[29], row[7], row[17], row[53], row[52] = str(eid), str(articles), quad, a1, a2, geo, place
    row[1], row[59] = '20261008', '20261008120000'
    return row


def series(n, hours_apart=2, region=10, total=1000, end=NOW):
    rows = []
    for i in range(n):
        stop = end - timedelta(hours=hours_apart * (n - 1 - i))
        rows.append({'window_start': (stop - timedelta(hours=2)).isoformat(), 'window_end': stop.isoformat(),
                     'total_articles': total, 'region_articles': dict.fromkeys(gei.REGION_RULES, region)})
    return rows


class CountingTests(unittest.TestCase):
    def test_conflict_articles_by_region_dedupe_and_rules(self):
        batches = [[event(1, 10, a1='UKR'), event(2, 20, quad='1', a1='UKR'), event(3, 5, geo='IS'),
                    event(4, 7, place='Spratly Islands'), event(5, 3, a1='CHN', a2='PHL'), event(6, 55, a1='USA')],
                   [event(1, 10, a1='UKR'), event(7, 4, a1='TWN', a2='CHN'), event(8, 6, geo='KN')]]
        counts = gei.count_articles(batches)
        self.assertEqual(counts['total_articles'], 110)  # event 1 counted once; all quad classes in total
        self.assertEqual(counts['region_articles'],
                         {'ukraine': 10, 'mideast': 5, 'taiwan': 4, 'korea': 6, 'southsea': 10})

    def test_invalid_or_empty_input_is_rejected_not_zero(self):
        with self.assertRaises(ValueError): gei.count_articles([[event(1, 'x')]])
        with self.assertRaises(ValueError): gei.count_articles([[event(1, -1)]])
        with self.assertRaises(ValueError): gei.count_articles([[event(1, 0)]])

    def test_batch_stamps_cover_two_hours(self):
        stamps = gei.batch_stamps('20261008120000')
        self.assertEqual(stamps[0], '20261008101500'); self.assertEqual(stamps[-1], '20261008120000')
        with self.assertRaises(ValueError): gei.batch_stamps('20261008120700')


class MetricsTests(unittest.TestCase):
    def test_baseline_must_accumulate_before_scoring(self):
        out = gei.regional_metrics(series(6), NOW, fresh=True)
        self.assertIsNone(out['ukraine']['score'])
        self.assertEqual(out['ukraine']['reason'], 'baseline_accumulating')
        self.assertEqual(out['ukraine']['latest'], 1.0)

    def test_score_relative_to_own_baseline_and_valid_zero(self):
        rows = series(14)
        self.assertEqual(gei.regional_metrics(rows, NOW, fresh=True)['ukraine']['score'], 50.0)
        rows[-1] = {**rows[-1], 'region_articles': {**rows[-1]['region_articles'], 'ukraine': 0, 'mideast': 30}}
        out = gei.regional_metrics(rows, NOW, fresh=True)
        self.assertEqual(out['ukraine']['score'], 0.0)        # measured zero stays zero
        self.assertEqual(out['ukraine']['delta_pct'], -100.0)
        self.assertEqual(out['mideast']['score'], 100.0)       # capped
        self.assertFalse(out['ukraine']['stale'])

    def test_sparse_region_and_failed_round_are_not_scored(self):
        rows = series(14, region=1)
        self.assertEqual(gei.regional_metrics(rows, NOW, fresh=True)['korea']['reason'], 'baseline_too_sparse')
        stale = gei.regional_metrics(series(14), NOW, fresh=False)['ukraine']
        self.assertTrue(stale['stale'])
        self.assertEqual(gei.regional_metrics([], NOW, fresh=False)['taiwan'],
                         {'provider': 'gdelt_events', 'stale': True, 'score': None, 'reason': 'no_observation'})

    def test_series_keeps_48h_replaces_same_window_and_drops_invalid(self):
        old = series(3, end=NOW - timedelta(hours=60))
        current = series(2)
        bad = [{'window_end': 'nope'}, {**current[0], 'total_articles': True}]
        replacement = {**current[-1], 'total_articles': 2000}
        kept = gei.update_series(old + current + bad, replacement, NOW)
        self.assertEqual(len(kept), 2)
        self.assertEqual(kept[-1]['total_articles'], 2000)


class ScoringTests(unittest.TestCase):
    def events(self, score=60, stale=False):
        return {'regions': {k: {'score': score, 'stale': stale, 'delta_pct': 20} for k in gei.REGION_RULES}}

    def test_wpi_prefers_doc_and_falls_back_to_events_only_when_fresh(self):
        doc = {'taiwan': {'latest': 1.0, 'stale': False}}
        self.assertEqual(calculate_wpi(None, [], gdelt=doc, gdelt_events=self.events())['g_source'], 'doc')
        fallback = calculate_wpi(None, [], gdelt={'taiwan': {'latest': 1.0, 'stale': True}}, gdelt_events=self.events())
        self.assertEqual((fallback['g_source'], fallback['factors']['g']), ('events', 60))
        none = calculate_wpi(None, [], gdelt={}, gdelt_events=self.events(stale=True))
        self.assertEqual((none['g_source'], none['factors']['g']), (None, None))

    def test_regions_use_events_with_distinct_history_basis(self):
        doc = {'ukraine': {'latest': 2.0, 'delta_pct': 5, 'stale': False}}
        regions = collector.build_region_risks([], doc, {}, {}, {}, self.events())
        by_key = {r['key']: r['factors'] for r in regions}
        self.assertNotIn('gdelt_source', by_key['ukraine'])
        self.assertEqual(by_key['ukraine']['gdelt'], 50.0)
        self.assertEqual((by_key['taiwan']['gdelt'], by_key['taiwan']['gdelt_source']), (60, 'events'))
        score = calculate_wpi(None, [], gdelt={}, gdelt_events=self.events())
        with tempfile.TemporaryDirectory() as td, patch.object(collector, 'HISTORY_FILE', Path(td) / 'h.json'):
            row = collector.update_history(score, None, regions)[-1]
        self.assertEqual(row['score_basis']['combined'], ['g_events'])
        self.assertEqual(row['score_basis']['regions']['taiwan'], ['gdelt_events'])
        self.assertEqual(row['score_basis']['regions']['ukraine'], ['gdelt'])


class SourceHealthTests(unittest.TestCase):
    def test_status_counts_backup_regions_and_accumulating_baseline(self):
        from data_quality import source_health
        doc = {k: {'stale': True} for k in gei.REGION_RULES}
        doc['ukraine'] = {'stale': False, 'latest': 1}
        events = {'regions': {k: {'stale': False, 'score': 40} for k in ('mideast', 'taiwan')}}
        health = source_health({'gdelt': doc, 'gdelt_events': events})['gdelt']
        self.assertEqual((health['status'], health['label']), ('partial', 'GDELT（事件檔備援）'))
        self.assertIn('3/5', health['note']); self.assertIn('2 區用事件檔', health['note'])
        waiting = {'regions': {k: {'stale': False, 'score': None, 'reason': 'baseline_accumulating'} for k in gei.REGION_RULES}}
        health = source_health({'gdelt': {k: {'stale': True} for k in gei.REGION_RULES}, 'gdelt_events': waiting})['gdelt']
        self.assertEqual(health['status'], 'stale'); self.assertIn('基準累積中', health['note'])


def export_zip(stamp, rows):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr(f'{stamp}.export.CSV', '\n'.join('\t'.join(r) for r in rows))
    return buffer.getvalue()


class Response:
    def __init__(self, status, body): self.status, self.body = status, body
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    def raise_for_status(self):
        if self.status >= 400: raise RuntimeError('http')
    @property
    def content(self):
        body = self.body
        class Reader:
            async def iter_chunked(self, n):
                # Deliver in small pieces, like a real network stream.
                for i in range(0, len(body), 7):
                    yield body[i:i + 7]
        return Reader()


class Session:
    def __init__(self, files, status=200): self.files, self.status, self.urls = files, status, []
    def get(self, url, **kwargs):
        self.urls.append(url)
        return Response(self.status, self.files.get(url.rsplit('/', 1)[1], b''))


class FetchTests(unittest.IsolatedAsyncioTestCase):
    def files(self):
        latest = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        latest -= timedelta(minutes=latest.minute % 15)
        stamps = gei.batch_stamps(latest.strftime('%Y%m%d%H%M%S'))
        files = {f'{s}.export.CSV.zip': export_zip(s, [event(int(s[-6:]) + i, 10, a1='UKR' if i == 0 else 'USA')
                                                       for i in range(2)]) for s in stamps}
        blob = files[f'{stamps[-1]}.export.CSV.zip']
        files['lastupdate.txt'] = (f'{len(blob)} {hashlib.md5(blob).hexdigest()} http://data.gdeltproject.org/gdeltv2/{stamps[-1]}.export.CSV.zip\n'
                                   f'10 {"0" * 32} http://data.gdeltproject.org/gdeltv2/{stamps[-1]}.mentions.CSV.zip\n').encode()
        return files

    async def test_collects_two_hour_window_within_request_cap(self):
        session = Session(self.files())
        state = await collector.fetch_gdelt_events(session, {})
        self.assertEqual(state['status'], 'available')
        self.assertEqual(len(session.urls), 9)
        self.assertEqual(state['series'][-1]['region_articles']['ukraine'], 80)
        self.assertEqual(state['series'][-1]['total_articles'], 160)
        self.assertEqual(state['regions']['ukraine']['reason'], 'baseline_accumulating')

    async def test_rate_limit_keeps_previous_observations_stale(self):
        previous = {'series': series(14, end=datetime.now(timezone.utc) - timedelta(hours=1)),
                    'last_success_at': 'earlier'}
        session = Session(self.files(), status=429)
        state = await collector.fetch_gdelt_events(session, previous)
        self.assertEqual((state['status'], state['error']), ('failed', 'SourceBackoff'))
        self.assertEqual(len(session.urls), 1)
        self.assertEqual(state['last_success_at'], 'earlier')
        self.assertEqual(len(state['series']), 14)
        self.assertTrue(all(r['stale'] and r['score'] is not None for r in state['regions'].values()))


if __name__ == '__main__':
    unittest.main()
