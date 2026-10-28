import asyncio
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fetch_data as collector


class MarketHistoryTests(unittest.TestCase):
    def test_yes_token_needs_a_yes_outcome(self):
        self.assertEqual(collector._yes_token({'clobTokenIds': '["a","b"]', 'outcomes': '["No","Yes"]'}), 'b')
        self.assertIsNone(collector._yes_token({'clobTokenIds': '["a"]', 'outcomes': '["Yes","No"]'}))
        self.assertIsNone(collector._yes_token({'clobTokenIds': 'x', 'outcomes': '["Yes"]'}))
        self.assertIsNone(collector._yes_token({}))

    def test_history_fetch_only_for_shown_taiwan_markets(self):
        end = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()
        tw = {'id': 'tw', 'slug': 'tw', 'question': 'Will China invade Taiwan?', 'end_date': end, 'yes_price': .1, 'volume': 9, 'yes_token': 'T'}
        other = {**tw, 'id': 'x', 'slug': 'x', 'question': 'Will Russia strike Kyiv?', 'yes_token': 'X'}
        asked = []
        class Resp:
            status = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def json(self): return {'history': [{'t': 1790640021, 'p': 0.125}, {'t': 1790726423, 'p': 1.5}, {'t': 1790812825, 'p': 0.1}]}
        class Session:
            def get(self, url, params=None, **kw): asked.append(params['market']); return Resp()
        markets = [tw, other]
        asyncio.run(collector.fetch_market_history(Session(), markets))
        self.assertEqual(asked, ['T'])
        self.assertEqual([p['p'] for p in tw['history_30d']], [12.5, 10.0])   # out-of-range price dropped
        self.assertNotIn('history_30d', other)

    def test_insight_carries_valid_history_only(self):
        import taiwan_insights as ti
        now = datetime.now(timezone.utc)
        m = {'id': 'tw', 'slug': 'tw', 'question': 'Will China invade Taiwan?', 'end_date': (now + timedelta(days=90)).isoformat(),
             'yes_price': .1, 'volume': 9, 'history_30d': [{'at': now.isoformat(), 'p': 10}, {'at': 'bad', 'p': 5}, {'at': now.isoformat(), 'p': 101}]}
        view = ti.build({'updated_at': now.isoformat(), 'polymarket': [m]})['markets'][0]
        self.assertIsNone(view['history_30d'])                               # only one valid point
        m['history_30d'].append({'at': (now - timedelta(days=1)).isoformat(), 'p': 12})
        self.assertEqual(len(ti.build({'updated_at': now.isoformat(), 'polymarket': [m]})['markets'][0]['history_30d']), 2)


if __name__ == '__main__':
    unittest.main()
