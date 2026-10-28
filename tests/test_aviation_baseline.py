import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fetch_data as f

NOW = datetime(2026, 10, 28, 14, 0, tzinfo=timezone.utc)


def history(per_day):
    """per_day: {hour: total} repeated over the last 7 days."""
    rows = []
    for day in range(1, 8):
        for hour, tot in per_day.items():
            rows.append({'ts': (NOW - timedelta(days=day)).replace(hour=hour).isoformat(), 'avi': {'tot': tot}})
    return rows


class AviationBaselineTests(unittest.TestCase):
    def test_compares_with_same_time_of_day_only(self):
        # US afternoon ~400, US night ~120: an afternoon reading of 400 is normal, not +100%.
        b = f.aviation_baseline(history({2: 120, 6: 120, 13: 380, 15: 420, 20: 400}), NOW)
        # 7 days of 15:00 + 6 of 13:00 (the 13:00 reading 7 days back falls outside the window).
        self.assertEqual(b, {'avg': 401.5, 'samples': 13})

    def test_window_wraps_midnight(self):
        b = f.aviation_baseline(history({23: 100, 1: 140, 12: 999}), NOW.replace(hour=0, minute=30))
        self.assertEqual(b['avg'], 120.0)

    def test_too_few_days_or_bad_rows_stay_unscored(self):
        rows = history({14: 300})[:4] + [{'ts': 'x'}, {'ts': NOW.isoformat(), 'avi': {'tot': 0}}, {'avi': None}]
        self.assertIsNone(f.aviation_baseline(rows, NOW))
        self.assertIsNone(f.aviation_baseline([], NOW))


if __name__ == '__main__':
    unittest.main()
