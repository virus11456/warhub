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


from unittest.mock import patch

MAPS = 'https://www.google.com/maps/place/x/@38.85,-77.04,17z/data=!3d38.8551791!4d-77.049733!16s'


class FakeResp:
    def __init__(self, body, status=200): self.body, self.status = body, status
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def json(self, content_type=None): return self.body


class FakeSession:
    def __init__(self, body): self.body, self.calls = body, []
    def post(self, url, params=None, **kw):
        self.calls.append(params['venue_name'])
        return FakeResp(self.body)


def live(busy=55, lat=38.8552, lng=-77.0497, address=None, forecast=50):
    info = {'venue_open': 'Open'}
    if lat is not None: info.update(venue_lat=lat, venue_lon=lng)
    if address: info['venue_address'] = address
    return {'analysis': {'venue_live_busyness_available': True, 'venue_live_busyness': busy,
                         'venue_forecasted_busyness': forecast, 'venue_live_forecasted_delta': busy - forecast},
            'venue_info': info}


class PizzaBestTimeTests(unittest.IsolatedAsyncioTestCase):
    payload = {'data': [shop(address=MAPS), {'name': 'Pizzato Pizza', 'current_popularity': 40, 'address': MAPS},
                        {'name': 'Extreme Pizza', 'current_popularity': None, 'is_closed_now': True, 'address': MAPS}]}

    async def run_fb(self, body, hour=18, key='k'):
        session = FakeSession(body)
        with patch.dict('os.environ', {'BESTTIME_API_KEY': key}), patch.object(collector, 'besttime_et_hour', return_value=hour):
            return await collector.fetch_pizza_besttime(session, self.payload), session

    async def test_only_after_work_hours_and_only_shops_missing_live_values(self):
        out, session = await self.run_fb(live())
        self.assertEqual(session.calls, ['We, The Pizza'])          # live shop and explicitly closed shop not queried
        self.assertEqual(out['We, The Pizza']['live_busyness'], 55)
        out, session = await self.run_fb(live(), hour=13)
        self.assertEqual((out, session.calls), ({}, []))
        out, session = await self.run_fb(live(), key='')
        self.assertEqual((out, session.calls), ({}, []))

    async def test_wrong_venue_or_no_live_value_is_ignored(self):
        self.assertEqual((await self.run_fb(live(lat=38.95, lng=-77.2)))[0], {})
        no_live = live(); no_live['analysis']['venue_live_busyness_available'] = False
        self.assertEqual((await self.run_fb(no_live))[0], {})
        # Without coordinates the street number and name must match.
        self.assertIn('We, The Pizza', (await self.run_fb(live(lat=None, address='2100 Crystal Dr, Arlington')))[0])
        self.assertEqual((await self.run_fb(live(lat=None, address='1800 Wilson Blvd, Arlington')))[0], {})

    def test_backup_fills_only_missing_values_and_is_labelled(self):
        fb = {'We, The Pizza': {'live_busyness': 0, 'forecasted': 40, 'recorded_at': 't'},
              'Pizzato Pizza': {'live_busyness': 99, 'forecasted': 10, 'recorded_at': 't'}}
        rows = {r['name']: r for r in collector.transform_pizza_shops(self.payload, fb)}
        we = rows['We, The Pizza']
        self.assertEqual((we['busyness'], we['is_open'], we['data_source'], we['percentage_of_usual']), (0, True, 'besttime', 0))
        self.assertEqual(we['hourly_24h'][-1], {'at': 't', 'v': 0, 'source': 'besttime'})
        self.assertEqual(rows['Pizzato Pizza']['busyness'], 40)          # PizzINT value wins
        self.assertNotEqual(rows['Pizzato Pizza']['data_source'], 'besttime')
        self.assertEqual(rows['Extreme Pizza']['status'], 'closed')
