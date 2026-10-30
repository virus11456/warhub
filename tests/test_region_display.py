import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import alerts
import fetch_data as f

NOW = datetime(2026, 10, 30, 8, 30, tzinfo=timezone.utc)


def hist(*scores, key='taiwan', step=2):
    """Earlier runs, oldest first, `step` hours apart, the last one `step` hours before NOW."""
    n = len(scores)
    return [{'ts': (NOW - timedelta(hours=step * (n - i))).isoformat(timespec='minutes'),
             'model_version': f.MODEL_VERSION, 'regions': {key: s}} for i, s in enumerate(scores)]


def region(score, **factors):
    return {'key': 'taiwan', 'score': score, 'level': f.region_level(score), 'factors': factors}


class RegionDisplayTests(unittest.TestCase):
    def shown(self, raw, history, **factors):
        r = region(raw, **factors)
        f.region_display([r], history, NOW)
        return r

    def test_single_run_spike_or_drop_is_not_shown_but_raw_is_kept(self):
        r = self.shown(80, hist(20, 22))
        self.assertEqual((r['score'], r['level'], r['score_raw'], r['level_raw']), (22, 'WATCH', 80, 'CRITICAL'))
        self.assertEqual(r['display'], {'method': 'median3', 'samples': [20, 22, 80]})
        self.assertEqual(self.shown(0, hist(31, 38))['score'], 31)

    def test_change_that_holds_two_runs_is_shown_in_full_not_averaged_down(self):
        self.assertEqual(self.shown(80, hist(20, 80))['score'], 80)
        self.assertEqual(self.shown(20, hist(80, 20))['score'], 20)

    def test_airspace_confirmation_short_history_and_missing_score_show_this_run(self):
        self.assertEqual(self.shown(80, hist(20, 22), notam=90)['score'], 80)
        self.assertEqual(self.shown(80, hist(20, 22), notam_closure=True)['display'], {'method': 'airspace'})
        self.assertEqual(self.shown(80, hist(22))['score'], 80)                       # one earlier run only
        self.assertEqual(self.shown(80, hist(20, 22, step=4))['score'], 80)           # 8 h ago is outside 6.5 h
        self.assertEqual(self.shown(80, hist(20, None, 22))['score'], 22)             # missing earlier value skipped
        r = self.shown(None, hist(20, 22))
        self.assertIsNone(r['score']); self.assertEqual(r['display'], {'method': 'latest'})

    def test_other_model_versions_are_not_mixed_in(self):
        old = hist(20, 22)
        for h in old: h['model_version'] = 'wpi-3.9'
        self.assertEqual(self.shown(80, old)['score'], 80)

    def test_owner_alert_uses_this_runs_score(self):
        r = self.shown(70, hist(20, 22))
        jumps, levels, pending = alerts.region_jumps([r], {'region_levels': {'taiwan': 'WATCH'}}, NOW)
        self.assertEqual(levels['taiwan'], 'CRITICAL')
        self.assertIn('taiwan', pending)          # raw jump recorded for confirmation, despite median 22


if __name__ == '__main__':
    unittest.main()
