import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from taiwan_insights import build

class TaiwanInsightsTests(unittest.TestCase):
    now = datetime(2026, 9, 13, 2, tzinfo=timezone.utc)

    def market(self, price=.1, **extra):
        return dict(id='one', question='Will China invade Taiwan by 2030?', question_zh='中國會在2030年前入侵台灣嗎？',
                    yes_price=price, volume=100, slug='taiwan', end_date='2030-01-01T00:00:00Z', **extra)

    def snapshot(self, **extra):
        return {'updated_at': self.now.isoformat(), **extra}

    def day(self, offset, count):
        end = self.now.replace(hour=22) - timedelta(days=offset+1)
        return {'date': (end+timedelta(hours=8)).date().isoformat(), 'aircraft': count,
                'verified': True, 'date_basis': 'period_end', 'source_kind': 'mnd_daily_report',
                'period_end': end.isoformat(), 'source_url': 'https://air.mnd.gov.tw/TW/News/News_Detail.aspx?CID=213&ID=1'}

    def test_activity_baseline_excludes_today_and_needs_fourteen_days(self):
        days = [self.day(0,100)] + [self.day(i,0) for i in range(1,15)]
        result = build(self.snapshot(pla={'days': days}))['activity']
        self.assertEqual(result['status'], 'elevated')
        self.assertEqual(result['median'], 0)
        self.assertEqual(result['baseline_days'], 14)
        self.assertEqual(build(self.snapshot(pla={'days':days[:5]}))['activity']['status'], 'baseline_pending')
        self.assertEqual(build(self.snapshot(pla={'days':[self.day(4,100)]}))['activity']['status'], 'stale')

    def test_same_contract_delta_and_original_timestamp_retention(self):
        earlier = build({'updated_at':(self.now-timedelta(hours=24)).isoformat(), 'polymarket':[self.market(.1)]})
        saved = copy.deepcopy(earlier)
        result = build(self.snapshot(polymarket=[self.market(.15)]), earlier)
        self.assertEqual(result['markets'][0]['delta_pp'],5)
        self.assertEqual(result['markets'][0]['comparison_hours'],24)
        self.assertEqual(earlier,saved)
        result = build(self.snapshot(polymarket=[{**self.market(.15),'end_date':'2031-01-01T00:00:00Z'}]), earlier)
        self.assertIsNone(result['markets'][0]['delta_pp'])

    def test_missing_out_of_window_and_stale_markets(self):
        earlier = build({'updated_at':(self.now-timedelta(hours=30)).isoformat(),'polymarket':[self.market()]})
        self.assertIsNone(build(self.snapshot(polymarket=[self.market(.2)]), earlier)['markets'][0]['delta_pp'])
        self.assertEqual(build(self.snapshot(polymarket=[self.market(stale=True)]))['markets'],[])
        self.assertEqual(build(self.snapshot(polymarket=[{**self.market(), 'end_date':'2020-01-01T00:00:00Z'}]))['markets'],[])

    def test_news_dedup_retention_and_time_labels(self):
        news={'title':'測試 新聞','url':'https://example.com/news','domain':'source','ts':self.now.isoformat()}
        earlier={'news_observations':[news]}
        rows=[news,{**news,'title':'測試新聞','url':'https://example.com/reprint'},
              {**news,'title':'未來','ts':(self.now+timedelta(hours=1)).isoformat()},
              {**news,'title':'不安全','url':'javascript:alert(1)'}]
        result=build(self.snapshot(tw_news=rows,pla={'days':[self.day(0,0)]}),earlier)
        self.assertEqual(result['news']['sample_24h'],1)
        self.assertEqual({r['time_label'] for r in result['timeline']},{'新聞發稿時間','統計截止時間'})
        self.assertEqual(result['activity']['latest']['aircraft'],0)

    def test_market_history_is_bounded_and_retry_is_idempotent(self):
        previous={'market_observations':[{'at':(self.now-timedelta(hours=i)).isoformat(),'markets':[]} for i in range(250)]}
        first=build(self.snapshot(),previous)
        self.assertEqual(len(first['market_observations']),100)
        self.assertEqual(build(self.snapshot(),first)['market_observations'],first['market_observations'])

    def test_news_input_failure_preserves_saved_samples_and_original_time(self):
        row = {'title': '已保存新聞', 'title_zh': None, 'url': 'https://example.com/news', 'domain': '來源',
               'ts': (self.now-timedelta(hours=2)).isoformat()}
        previous = {'news_observations': [row]}
        original = copy.deepcopy(previous)
        for batch, status in [([], 'unavailable'), ([{**row, 'stale': True}], 'stale'),
                              ([row], 'available'), ([row, None], 'partial')]:
            with self.subTest(status=status):
                result = build(self.snapshot(tw_news=batch), previous)
                self.assertEqual(result['news']['input_status'], status)
                self.assertEqual(result['news']['sample_24h'], 1)
                self.assertEqual(result['news']['latest_at'], row['ts'])
                self.assertEqual(result['news_observations'], [row])
                self.assertEqual(previous, original)

    def test_zero_saved_news_is_distinct_from_missing_current_input(self):
        old = {'title': '較早新聞', 'url': 'https://example.com/old', 'domain': '來源',
               'ts': (self.now-timedelta(hours=25)).isoformat()}
        result = build(self.snapshot(tw_news=[old]))
        self.assertEqual(result['news']['input_status'], 'available')
        self.assertEqual(result['news']['sample_24h'], 0)
        self.assertEqual(result['news']['publishers_24h'], 0)
        self.assertEqual(result['news']['latest_at'], old['ts'])
        missing = build(self.snapshot(), result)
        self.assertEqual(missing['news']['input_status'], 'unavailable')
        self.assertEqual(missing['news_observations'], result['news_observations'])

    def test_invalid_news_batch_does_not_claim_available(self):
        for rows in [None, {}, [None, {'title': 123}],
                     [{'title': '未來新聞', 'url': 'https://example.com/future',
                       'ts': (self.now+timedelta(hours=1)).isoformat()}]]:
            with self.subTest(rows=rows):
                result = build(self.snapshot(tw_news=rows))
                self.assertEqual(result['news']['input_status'], 'unavailable')
                self.assertEqual(result['news']['sample_24h'], 0)
                self.assertIsNone(result['news']['latest_at'])

if __name__ == '__main__':
    unittest.main()
