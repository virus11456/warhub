import unittest
from datetime import datetime, timezone, timedelta
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from collection_policy import plan
from data_quality import source_health

class Cadence(unittest.TestCase):
    def test_bootstrap_thresholds_and_manual_modes(self):
        now = datetime(2026, 9, 11, tzinfo=timezone.utc)
        for mode in ('auto', 'full'):
            self.assertTrue(plan({}, mode, now)['slow_refresh'])
        self.assertFalse(plan({}, 'fast', now)['slow_refresh'])
        def previous(hours):
            return {'collection': {'slow_attempted_at': (now-timedelta(hours=hours)).isoformat(),
                                   'history_attempted_at': (now-timedelta(hours=hours)).isoformat()}}
        self.assertFalse(plan(previous(5.99), 'auto', now)['slow_refresh'])
        self.assertTrue(plan(previous(6), 'auto', now)['slow_refresh'])
        self.assertFalse(plan(previous(6), 'auto', now)['history_refresh'])
        self.assertTrue(plan(previous(24), 'auto', now)['history_refresh'])
        self.assertTrue(plan(previous(-1), 'auto', now)['slow_refresh'])
        self.assertTrue(plan(previous(1), 'full', now)['history_refresh'])
        with self.assertRaises(ValueError): plan({}, 'typo', now)

    def test_fast_mode_does_not_renew_stale_source(self):
        now = datetime.now(timezone.utc)
        old = (now-timedelta(hours=7)).isoformat()
        data = {'food': {'updated_at': old, 'items': [{'wan_ton': 12}]},
                'collection': plan({'collection': {'slow_attempted_at': old}}, 'fast', now)}
        health = source_health(data)['food']
        self.assertEqual(health['status'], 'stale')
        self.assertEqual(health['observed_at'], old)
        self.assertIn('未重新查詢', health['note'])
