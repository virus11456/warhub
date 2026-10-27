import gzip
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fetch_data as collector
import notam_baseline as nb

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)


def record(danger, hours_ago=0, **extra):
    return {'complete': True, 'stale': False, 'danger': danger, 'closure': False,
            'observed_at': (NOW - timedelta(hours=hours_ago)).isoformat(), **extra}


def series(values, step=2):
    """Oldest first; the last value is the current observation."""
    n = len(values)
    return nb.update({}, {}, NOW) | {'taiwan': [
        {'at': (NOW - timedelta(hours=step * (n - 1 - i))).isoformat(), 'danger': v, 'closure': False}
        for i, v in enumerate(values)]}


class RelativeScoreTests(unittest.TestCase):
    def test_usual_level_is_50_and_more_notices_raise_the_score(self):
        rows = series([19] * 14 + [19])
        self.assertEqual(nb.relative(rows['taiwan'], record(19))['score'], 50.0)
        self.assertEqual(nb.relative(rows['taiwan'], record(39))['score'], 100.0)
        self.assertEqual(nb.relative(rows['taiwan'], record(9))['score'], 25.0)
        self.assertEqual(nb.relative(rows['taiwan'], record(19))['baseline_danger'], 19.0)

    def test_quiet_region_stays_defined_and_a_new_notice_stands_out(self):
        rows = series([0] * 15)
        self.assertEqual(nb.relative(rows['taiwan'], record(0))['score'], 50.0)
        self.assertEqual(nb.relative(rows['taiwan'], record(3))['score'], 100.0)

    def test_short_baseline_partial_or_stale_records_are_not_scored(self):
        self.assertEqual(nb.relative(series([19] * 6)['taiwan'], record(19))['reason'], 'baseline_accumulating')
        self.assertEqual(nb.relative(series([19] * 15, step=1)['taiwan'], record(19))['reason'], 'baseline_accumulating')
        for bad in (record(19, complete=False), record(19, stale=True), record(True), record(-1), {**record(19), 'observed_at': 'x'}):
            self.assertIsNone(nb.relative(series([19] * 15)['taiwan'], bad)['score'])

    def test_update_keeps_7_days_dedupes_and_ignores_unusable_rounds(self):
        old = {'taiwan': [{'at': (NOW - timedelta(days=8)).isoformat(), 'danger': 5},
                          {'at': (NOW - timedelta(hours=2)).isoformat(), 'danger': 7}]}
        kept = nb.update(old, {'taiwan': record(9), 'korea': record(1, complete=False)}, NOW)
        self.assertEqual([r['danger'] for r in kept['taiwan']], [7, 9])
        self.assertEqual(kept['korea'], [])
        again = nb.update(kept, {'taiwan': record(9)}, NOW)
        self.assertEqual(len(again['taiwan']), 2)

    def test_seed_reads_only_recent_analysis_snapshots(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            def write(name, payload):
                path = root / '2026' / '10' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(gzip.compress(json.dumps(payload).encode()))
            write('20261008T100000_a.json.gz', {'files': {'data.json': {'notams': {'taiwan': record(20, 2)}}}})
            write('20261008T110000_b.json.gz', {'kind': 'source_observation', 'notams': {'taiwan': record(99, 1)}})
            write('20260920T100000_c.json.gz', {'files': {'data.json': {'notams': {'taiwan': record(50, 400)}}}})
            seeded = nb.seed_from_archives(root, NOW)
        self.assertEqual([r['danger'] for r in seeded['taiwan']], [20])


class RegionScoringTests(unittest.TestCase):
    def test_region_uses_relative_score_only_and_records_distinct_basis(self):
        notams = {'taiwan': {**record(19), 'score': 100, 'relative': {'score': 50.0, 'baseline_danger': 19.0}},
                  'korea': {**record(0), 'score': 0, 'relative': {'score': None, 'reason': 'baseline_accumulating'}}}
        regions = collector.build_region_risks([], {}, {}, {}, notams)
        factors = {r['key']: r['factors'] for r in regions}
        self.assertEqual((factors['taiwan']['notam'], factors['taiwan']['notam_source']), (50.0, 'relative'))
        self.assertNotIn('notam', factors['korea'])                 # old saturated score never used
        self.assertEqual(factors['korea']['notam_danger'], 0)        # raw count still shown
        score = {'combined_score': None, 'polymarket_score': None, 'factors': {}}
        with tempfile.TemporaryDirectory() as td, patch.object(collector, 'HISTORY_FILE', Path(td) / 'h.json'):
            row = collector.update_history(score, None, regions)[-1]
        self.assertEqual(row['score_basis']['regions']['taiwan'], ['notam_rel'])
        self.assertEqual(row['score_basis']['regions']['korea'], [])


if __name__ == '__main__':
    unittest.main()
