import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import merge_history as merge

class RemoteHistoryReadTests(unittest.TestCase):
    def test_git_failures_and_invalid_json_raise(self):
        for error in (subprocess.CalledProcessError(128, ['git']), OSError('unavailable')):
            with self.subTest(error=type(error).__name__), patch.object(merge.subprocess, 'check_output', side_effect=error):
                with self.assertRaises(RuntimeError):
                    merge._remote('data/history.json')
        with patch.object(merge.subprocess, 'check_output', return_value=b'broken'):
            with self.assertRaises(RuntimeError):
                merge._remote('data/history.json')

    def test_accepts_valid_empty_histories(self):
        for path, value in [('data/history.json', []), ('data/pla_adiz.json', {'days': {}}),
                            ('data/metrics_daily.json', {'days': {}}),
                            ('data/food_history.json', {'months': {}}),
                            ('data/strat_history.json', {'months': {}})]:
            with self.subTest(path=path), patch.object(merge.subprocess, 'check_output', return_value=json.dumps(value).encode()):
                self.assertEqual(merge._remote(path), value)

    def test_wrong_structure_is_not_treated_as_empty(self):
        for path, value in [('data/history.json', {}), ('data/history.json', None),
                            ('data/pla_adiz.json', {'days': []}), ('data/metrics_daily.json', {}),
                            ('data/food_history.json', []), ('data/strat_history.json', {'months': None})]:
            with self.subTest(path=path, value=value), patch.object(merge.subprocess, 'check_output', return_value=json.dumps(value).encode()):
                with self.assertRaises(ValueError):
                    merge._remote(path)

    def test_remote_failure_stops_merge_without_replacing_local_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'history.json'
            original = '[{"ts":"2026-09-13T01:00:00Z","combined":0}]'
            path.write_text(original)
            with patch.object(merge, 'DATA_DIR', root), patch.object(merge.subprocess, 'check_output', side_effect=subprocess.CalledProcessError(128, ['git'])):
                with self.assertRaises(RuntimeError):
                    merge.merge_score_history()
            self.assertEqual(path.read_text(), original)

if __name__ == '__main__':
    unittest.main()
