import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import merge_history as merge
import fetch_data as collector

class DailyMetricsMergeTests(unittest.TestCase):
    now = datetime(2026, 9, 13, 18, tzinfo=timezone.utc)

    def apply(self, local, remote):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'metrics_daily.json'
            path.write_text(json.dumps({'days': local}))
            with patch.object(merge, 'DATA_DIR', root), patch.object(merge, '_remote', return_value={'days': remote}):
                merge.merge_metrics_daily(self.now)
                saved = path.read_text()
                merge.merge_metrics_daily(self.now)
                self.assertEqual(path.read_text(), saved)
            return json.loads(saved)['days']

    def test_newer_remote_wins_and_newer_zero_revision_wins(self):
        old = {'recorded_at': '2026-09-13T10:00:00Z', 'combined': 40}
        new = {'recorded_at': '2026-09-13T12:00:00Z', 'combined': 0}
        self.assertEqual(self.apply({'2026-09-13': old}, {'2026-09-13': new})['2026-09-13'], new)
        self.assertEqual(self.apply({'2026-09-13': new}, {'2026-09-13': old})['2026-09-13'], new)

    def test_legacy_is_retained_without_overwriting_dated_rows(self):
        dated = {'recorded_at': '2026-09-13T10:00:00Z', 'combined': 20}
        saved = self.apply({'2026-09-13': {'combined': 90}, '2026-09-12': {'combined': 0}}, {'2026-09-13': dated})
        self.assertEqual(saved['2026-09-13'], dated)
        self.assertEqual(saved['2026-09-12'], {'combined': 0})

    def test_taipei_midnight_and_invalid_times(self):
        row = {'recorded_at': '2026-09-13T16:00:00Z', 'combined': 10}
        self.assertEqual(self.apply({'2026-09-14': row}, {}), {'2026-09-14': row})
        for bad in [row, {'recorded_at': 'invalid'}, {'recorded_at': '2026-09-13T12:00:00'},
                    {'recorded_at': '2026-09-15T00:00:00Z'}]:
            self.assertEqual(self.apply({'2026-09-13': bad}, {}), {})
        self.assertEqual(self.apply({'bad-date': {}, '2020-01-01': {}, '2026-09-15': {}}, {}), {})

    def test_collector_uses_one_instant_for_date_and_record(self):
        fixed = datetime(2026, 9, 13, 16, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(collector, 'METRICS_DAILY_FILE', root/'metrics.json'), patch.object(collector, 'DATA_FILE', root/'data.json'), patch.object(collector, 'datetime') as clock:
                clock.now.return_value = fixed
                collector.update_daily_metrics({}, None, None, {}, {}, None, {}, [])
            days = json.loads((root/'metrics.json').read_text())['days']
            self.assertEqual(list(days), ['2026-09-14'])
            self.assertEqual(days['2026-09-14']['recorded_at'], fixed.isoformat())

if __name__ == '__main__':
    unittest.main()
