import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import alerts


class ContentTests(unittest.TestCase):
    def test_missing_and_invalid_scores_are_not_zero_or_exceptions(self):
        for value in (None, True, '0', float('nan'), float('inf'), -1, 101):
            self.assertEqual(alerts._fmt_score(value), '資料不足')
        self.assertEqual(alerts._fmt_score(0), '0.0')
        for value in (None, True, '0', float('nan'), -1, 1.01):
            self.assertEqual(alerts._fmt_coverage(value), '資料不足')
        self.assertEqual(alerts._fmt_coverage(0), '0%')
        self.assertEqual(alerts._fmt_coverage(0.6), '60%')

    def test_partial_aviation_preserves_zero_and_marks_missing(self):
        text = alerts._fmt_aviation({'summary': {'uav': 0, 'total': 8}})
        self.assertIn('無人機 0', text)
        self.assertIn('加油機 缺資料', text)
        self.assertIn('部分資料', text)
        self.assertIn('可見總數 8', text)
        self.assertIn('ADS-B 覆蓋不完整', text)
        self.assertNotIn('全球軍機', text)

    def test_stale_or_failed_aviation_is_not_current_zero(self):
        for source, health, label in [({'stale': True}, {}, '資料過期'),
                                    ({'error': 'failed'}, {}, '資料不可用'),
                                    ({}, {'status': 'stale'}, '資料過期')]:
            text = alerts._fmt_aviation({**source, 'summary': {'total': 0}}, health)
            self.assertIn(label, text)
            self.assertNotIn('總數 0', text)

    def test_empty_and_unknown_pizza_never_claim_no_anomaly(self):
        for shops in (None, [], [{'is_open': None, 'busyness': None, 'status': 'unavailable'}]):
            text = alerts._fmt_pizza_shops(shops)
            self.assertNotIn('未見偏忙', text)
            self.assertNotIn('無店家爆量', text)
            self.assertNotIn('忙碌度 0%', text)

    def test_pizza_separates_closed_missing_stale_and_live_zero(self):
        shops = [{'is_open': False}, {'is_open': None},
                 {'is_open': True, 'busyness': 99, 'status': 'spike', 'stale': True},
                 {'is_open': True, 'busyness': 0, 'status': 'quiet'}]
        text = alerts._fmt_pizza_shops(shops)
        self.assertIn('有效即時人流 1/4', text)
        self.assertIn('已知未營業 1', text)
        self.assertIn('缺值或過期 2', text)
        self.assertIn('有效樣本未見', text)
        self.assertNotIn('99%', text)

    def test_firms_zero_stale_error_and_partial_are_distinct(self):
        self.assertIn('0 處', alerts._fmt_firms({'conflict_total': 0}))
        for source, label in [({}, '資料不足'), ({'conflict_total': 0, 'stale': True}, '資料過期'),
                              ({'conflict_total': 0, 'error': 'failed'}, '資料不可用')]:
            text = alerts._fmt_firms(source)
            self.assertIn(label, text)
            self.assertNotIn('0 處', text)
        self.assertIn('部分資料', alerts._fmt_firms({'conflict_total': 5, 'partial': True}))

    def test_digest_keeps_input_and_original_timestamp(self):
        data = {'updated_at': '2026-09-14T13:23:24Z', 'score': {'coverage': None},
                'aviation': {'summary': {'total': 0}}, 'source_health': {'aviation': {'status': 'stale'}}}
        original = copy.deepcopy(data)
        text = alerts.build_digest(data)
        self.assertIn('2026-09-14T13:23:24Z', text)
        self.assertIn('資料覆蓋率：資料不足', text)
        self.assertIn('資料過期', text)
        self.assertEqual(data, original)

    def test_hot_shop_requires_live_value_and_does_not_fabricate_baseline(self):
        text = alerts._fmt_pizza_shops([
            {'name': 'valid', 'is_open': True, 'status': 'busy', 'busyness': 80},
            {'name': 'missing', 'is_open': True, 'status': 'spike', 'busyness': None}])
        self.assertIn('valid', text)
        self.assertIn('80%', text)
        self.assertIn('缺平時比較值', text)
        self.assertNotIn('missing', text)
        self.assertNotIn('平時 0%', text)
