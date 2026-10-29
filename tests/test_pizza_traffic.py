import asyncio
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fetch_data as collector
import pizza_traffic as pt

# Wednesday 2026-10-28 20:00 in Washington (EDT, UTC-4)
NOW = datetime(2026, 10, 29, 0, 0, tzinfo=timezone.utc)
NAME = 'We, The Pizza'


def week(value=30):
    """BestTime week_raw2: Monday=0, slots start at 6 AM."""
    return [{'day_int': d, 'day_raw': [value] * 24} for d in range(7)]


def venues(*names, usual=30):
    return {'venues': {n: {'venue_id': 'v' + str(i), 'usual_week': pt.usual_week_from_besttime(week(usual))}
                       for i, n in enumerate(names)}}


class WeekConversionTests(unittest.TestCase):
    def test_besttime_days_map_to_sunday_based_clock_hours(self):
        raw = [{'day_int': 0, 'day_raw': list(range(24))}]          # Monday 6 AM … Tuesday 5 AM
        usual = pt.usual_week_from_besttime(raw)
        self.assertEqual(usual['1'][6], 0)                          # Monday 06:00 is slot 0
        self.assertEqual(usual['1'][23], 17)
        self.assertEqual(usual['2'][0], 18)                         # after midnight belongs to Tuesday
        self.assertEqual(usual['2'][5], 23)
        self.assertIsNone(usual['1'][0])                            # Monday 00:00 came from Sunday's row, absent here

    def test_invalid_rows_and_values_are_dropped(self):
        self.assertIsNone(pt.usual_week_from_besttime([{'day_int': 9, 'day_raw': [1] * 24}, {'day_int': 1, 'day_raw': [1]}]))
        usual = pt.usual_week_from_besttime([{'day_int': 2, 'day_raw': [140, -1, 0] + [None] * 21}])
        self.assertEqual(usual['3'][6:9], [None, None, 0])          # 0 is a real empty hour

    def test_usual_at_uses_washington_time(self):
        usual = pt.usual_week_from_besttime(week(0))
        usual['3'][20] = 44                                         # Wednesday 20:00 local
        self.assertEqual(pt.usual_at(usual, NOW), 44)


class ShopTests(unittest.TestCase):
    def test_status_needs_both_ratio_and_gap(self):
        self.assertEqual(pt.shop_status(10, 5)[0], 'normal')        # 200% but only +5
        self.assertEqual(pt.shop_status(36, 35)[0], 'normal')       # low absolute value, usual for the hour
        self.assertEqual(pt.shop_status(10, 35)[0], 'quiet')
        self.assertEqual(pt.shop_status(50, 30), ('busy', 167, None))
        self.assertEqual(pt.shop_status(70, 30), ('spike', 233, 'HIGH'))
        self.assertEqual(pt.shop_status(90, 30), ('spike', 300, 'EXTREME'))
        self.assertEqual(pt.shop_status(45, None), ('normal', None, None))

    def test_missing_setup_off_hours_and_failure_are_distinct(self):
        none = pt.build_shops({}, {}, None, NOW, True)
        self.assertTrue(all(s['status'] == 'setup_needed' for s in none))
        self.assertTrue(all(s['status'] == 'setup_needed' for s in pt.build_shops({}, {}, None, NOW, False)))
        waiting = pt.build_shops({}, venues(NAME), None, NOW, False)
        self.assertEqual(waiting[0]['status'], 'waiting')
        failed = pt.build_shops({NAME: {'error': True, 'error_message': 'quota'}}, venues(NAME), None, NOW, True)
        self.assertEqual((failed[0]['status'], failed[0]['error_message'], failed[0]['is_open']), ('unavailable', 'quota', None))
        closed = pt.build_shops({NAME: {'live_available': False, 'open': 'Closed'}}, venues(NAME), None, NOW, True)
        self.assertEqual((closed[0]['status'], closed[0]['is_open']), ('closed', False))

    def test_live_reading_joins_24h_history_and_old_points_drop(self):
        prev = [{'name': NAME, 'hourly_24h': [{'at': (NOW - timedelta(hours=30)).isoformat(), 'v': 9},
                                              {'at': (NOW - timedelta(hours=2)).isoformat(), 'v': 0}]}]
        shop = pt.build_shops({NAME: {'live_available': True, 'live_busyness': 50}}, venues(NAME), prev, NOW, True)[0]
        self.assertEqual([p['v'] for p in shop['hourly_24h']], [0, 50])
        self.assertEqual((shop['busyness'], shop['usual_now'], shop['status'], shop['data_source']), (50, 30, 'busy', 'besttime'))

    def test_summary_index_needs_two_comparable_shops(self):
        two = ['We, The Pizza', 'Extreme Pizza']
        shops = pt.build_shops({two[0]: {'live_available': True, 'live_busyness': 60},
                                two[1]: {'live_available': True, 'live_busyness': 30}}, venues(*two), None, NOW, True)
        s = pt.summarize(shops, venues(*two), True, NOW)
        self.assertEqual((s['state'], s['level'], s['index'], s['live_count']), ('ok', 'spike', 50.0, 2))
        one = pt.summarize(shops[:1], venues(two[0]), True, NOW)
        self.assertIsNone(one['index'])
        self.assertEqual(pt.summarize([], {}, True, NOW)['state'], 'setup_needed')
        self.assertEqual(pt.summarize([], venues(NAME), False, NOW)['state'], 'off_hours')
        self.assertEqual(pt.spike_events(shops)[0]['place_name'], two[0])


class BackupTests(unittest.TestCase):
    def payload(self, live=None, minutes_ago=10, name=NAME):
        rows = [{'hour': h, 'popularity': 30} for h in range(6, 24)]
        return {'data': [{'name': name, 'current_popularity': live,
                          'recorded_at': (NOW - timedelta(minutes=minutes_ago)).isoformat().replace('+00:00', 'Z'),
                          'baseline_popular_times': {str(d): rows for d in range(7)}},
                         {'name': 'Not one of ours', 'current_popularity': 90}]}

    def test_backup_fills_usual_week_and_fresh_live_only_where_ours_is_missing(self):
        backup = pt.backup_shops(self.payload(live=72))
        self.assertEqual(list(backup), [NAME])
        shop = pt.build_shops({}, {}, None, NOW, True, backup)[0]
        self.assertEqual((shop['busyness'], shop['data_source'], shop['usual_now'], shop['status']), (72, 'backup', 30, 'spike'))
        self.assertEqual(shop['recorded_at'], (NOW - timedelta(minutes=10)).isoformat())   # original observation time
        self.assertEqual(pt.summarize([shop], {}, True, NOW)['state'], 'ok')
        # Our own live reading wins over the backup.
        own = pt.build_shops({NAME: {'live_available': True, 'live_busyness': 40}}, venues(NAME), None, NOW, True, backup)[0]
        self.assertEqual((own['busyness'], own['data_source']), (40, 'besttime'))

    def test_stale_or_missing_backup_live_is_not_now(self):
        for backup in (pt.backup_shops(self.payload(live=72, minutes_ago=200)), pt.backup_shops(self.payload(live=None))):
            shops = pt.build_shops({}, {}, None, NOW, True, backup)
            shop = next(s for s in shops if s['name'] == NAME)
            self.assertEqual((shop['busyness'], shop['status'], shop['data_source']), (None, 'baseline_only', 'none'))
            self.assertIsNotNone(shop['usual_week'])
            self.assertEqual(pt.summarize(shops, {}, True, NOW)['state'], 'baseline_only')
        self.assertEqual(pt.backup_shops({'data': [{'name': NAME, 'current_popularity': 0}]})[NAME]['live'], 0)   # 0 is valid

    def test_health_reports_baseline_only_as_partial(self):
        from data_quality import source_health
        h = source_health({'pizza': [{}], 'pizza_summary': {'state': 'baseline_only'}})['pizza']
        self.assertEqual(h['status'], 'partial')


class FetchPizzaTests(unittest.TestCase):
    def run_fetch(self, store, et_hour, key='k'):
        calls = []
        async def live(session, k, venue):
            calls.append(venue['name']); return {'live_available': True, 'live_busyness': 40}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'v.json'; path.write_text(json.dumps(store))
            async def no_backup(session): return {}
            with patch.object(pt, 'VENUES_FILE', path), patch.object(collector, 'besttime_live', live), \
                 patch.object(collector, 'fetch_pizza_backup', no_backup), \
                 patch.object(collector, 'besttime_et_hour', lambda: et_hour), patch.dict('os.environ', {'BESTTIME_API_KEY': key}):
                return asyncio.run(collector.fetch_pizza(None, None)), calls

    def test_only_set_up_venues_are_queried_in_window(self):
        out, calls = self.run_fetch(venues(NAME), 20)
        self.assertEqual(calls, ['We, The Pizza'])                  # one credit, not six
        self.assertEqual(out['summary']['live_count'], 1)

    def test_no_query_off_hours_or_before_setup(self):
        self.assertEqual(self.run_fetch(venues(NAME), 9)[1], [])
        out, calls = self.run_fetch({}, 20)
        self.assertEqual((calls, out['summary']['state']), ([], 'setup_needed'))


class SetupTests(unittest.TestCase):
    def test_targets_skip_ready_venues_unless_redo(self):
        import besttime_setup as setup
        pizza, bars = setup.targets('all', venues(NAME), True)
        self.assertNotIn(NAME, [n for n, _ in pizza])
        self.assertEqual(len(pizza) + len(bars), 5 + len(collector.PENTAGON_BARS))
        pizza, bars = setup.targets('pizza', venues(NAME), False)
        self.assertEqual((len(pizza), bars), (6, []))


if __name__ == '__main__':
    unittest.main()


class HealthTests(unittest.TestCase):
    def test_setup_needed_is_not_an_outage(self):
        from data_quality import source_health
        h = source_health({'pizza': [], 'pizza_summary': {'state': 'setup_needed'}})['pizza']
        self.assertEqual(h['status'], 'not_configured')
        h = source_health({'pizza': [{}], 'pizza_summary': {'state': 'no_live', 'live_count': 0, 'total': 6}})['pizza']
        self.assertEqual(h['status'], 'unavailable')

    def test_digest_says_not_set_up(self):
        import alerts
        self.assertIn('尚未在 BestTime 建檔', alerts._fmt_pizza_shops([{}], {'status': 'not_configured'}))

