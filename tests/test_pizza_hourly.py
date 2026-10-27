import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fetch_data as collector


def shop(**extra):
    return {'name': 'We, The Pizza', 'current_popularity': None, 'is_closed_now': False, **extra}


class PizzaHourlyTests(unittest.TestCase):
    def test_keeps_observation_times_and_separates_missing_from_zero(self):
        points = [{'current_popularity': None, 'recorded_at': 't1'},
                  {'current_popularity': 0, 'recorded_at': 't2'},
                  {'current_popularity': 55.4, 'recorded_at': 't3'},
                  {'current_popularity': 140, 'recorded_at': 't4'},
                  {'current_popularity': 30}]
        hourly, _ = collector.pizza_hourly(shop(sparkline_24h=points))
        self.assertEqual(hourly, [{'at': 't1', 'v': None}, {'at': 't2', 'v': 0},
                                  {'at': 't3', 'v': 55}, {'at': 't4', 'v': None}])

    def test_usual_week_is_24_slots_per_valid_day(self):
        base = {'2': [{'hour': 11, 'popularity': 0}, {'hour': 12, 'popularity': 80}, {'hour': 24, 'popularity': 9},
                      {'hour': True, 'popularity': 9}],
                '7': [{'hour': 12, 'popularity': 50}],
                '3': [{'hour': 12, 'popularity': None}]}
        _, usual = collector.pizza_hourly(shop(baseline_popular_times=base))
        self.assertEqual(set(usual), {'2'})
        self.assertEqual(len(usual['2']), 24)
        self.assertEqual((usual['2'][11], usual['2'][12], usual['2'][0]), (0, 80, None))
        self.assertEqual(collector.pizza_hourly(shop()), ([], None))

    def test_transform_adds_chart_fields(self):
        out = collector.transform_pizza_shops({'data': [shop(baseline_popular_times={'0': [{'hour': 9, 'popularity': 20}]})]})
        row = next(r for r in out if r['name'] == 'We, The Pizza')
        self.assertEqual(row['usual_week']['0'][9], 20)
        self.assertEqual(row['hourly_24h'], [])


if __name__ == '__main__':
    unittest.main()
