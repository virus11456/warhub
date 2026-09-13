import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import merge_history as merge

class ScoreHistoryMergeTests(unittest.TestCase):
    now = datetime(2026, 9, 13, 3, tzinfo=timezone.utc)

    def row(self, hours, score=20, **extra):
        return {'ts': (self.now - timedelta(hours=hours)).isoformat(),
                'model_version': 'wpi-4.0', 'combined': score,
                'regions': {'taiwan': score}, **extra}

    def run_merge(self, local, remote):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'history.json'
            path.write_text(json.dumps(local))
            with patch.object(merge, 'DATA_DIR', root), patch.object(merge, '_remote', return_value=remote):
                merge.merge_score_history(self.now)
                first = path.read_text()
                merge.merge_score_history(self.now)
                self.assertEqual(path.read_text(), first)
            return json.loads(first)

    def test_union_keeps_remote_only_points_and_whole_local_revision(self):
        remote = [self.row(6), self.row(4, 30), self.row(2)]
        local = [self.row(6), self.row(4, 0), self.row(0)]
        saved = self.run_merge(local, remote)
        self.assertEqual([r['combined'] for r in saved], [20, 0, 20, 20])
        self.assertEqual(len(saved), 4)

    def test_preserves_basis_only_when_scores_match(self):
        basis = {'combined': ['a', 'p'], 'regions': {'taiwan': ['poly', 'gdelt']}}
        remote = [self.row(4, score_basis=basis), self.row(2, score_basis=basis)]
        saved = self.run_merge([self.row(4), self.row(2, 0)], remote)
        self.assertEqual(saved[0]['score_basis'], basis)
        self.assertNotIn('score_basis', saved[1])

    def test_timezones_retention_invalid_rows_and_separate_models(self):
        valid = self.row(2)
        equivalent = {**valid, 'ts': valid['ts'].replace('+00:00', 'Z'), 'combined': 0}
        invalid = [None, {}, {'ts': 'invalid'}, {'ts': '2026-09-13T00:00:00'},
                   self.row(-1), self.row(745), self.row(1, model_version={})]
        saved = self.run_merge([equivalent, *invalid], [valid, self.row(744), self.row(2, model_version='older')])
        self.assertEqual(len(saved), 3)
        self.assertEqual(saved[0]['ts'], self.row(744)['ts'])
        self.assertEqual(saved[-1]['combined'], 0)

    def test_recover_from_non_list_local(self):
        self.assertEqual(self.run_merge({}, [self.row(2)]), [self.row(2)])

if __name__ == '__main__':
    unittest.main()
