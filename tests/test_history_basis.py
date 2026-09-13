import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fetch_data as collector


class HistoryBasisTests(unittest.TestCase):
    def test_preserves_old_rows_and_records_only_contributing_factors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.json'
            old = {'ts': (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
                   'model_version': 'wpi-4.0', 'combined': 30, 'regions': {'taiwan': 20}}
            path.write_text(json.dumps([old]))
            score = {'combined_score': 25, 'polymarket_score': 10,
                     'factors': {'p': 10, 'a': 0, 'g': None, 'z': 40, 'w': False,
                                 's': float('nan'), 'unknown': 20}}
            regions = [{'key': 'taiwan', 'score': 20,
                        'factors': {'poly': 10, 'gdelt': 0, 'notam': None,
                                    'firms_hotspots': 50, 'avi_count': 100}},
                       {'key': 'korea', 'score': None, 'factors': {}}]
            with patch.object(collector, 'HISTORY_FILE', path):
                result = collector.update_history(score, None, regions)
            saved = json.loads(path.read_text())
            self.assertEqual(saved, result)
            self.assertEqual(saved[0], old)
            self.assertEqual(saved[-1]['score_basis'], {
                'combined': ['a', 'p', 'z'],
                'regions': {'taiwan': ['gdelt', 'poly'], 'korea': []}})
            self.assertEqual(saved[-1]['regions']['taiwan'], 20)


if __name__ == '__main__':
    unittest.main()
