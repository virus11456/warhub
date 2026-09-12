import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import AsyncMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from pla_official import parse_report, report_links, view, collect
from merge_history import _union_days

URL='https://air.mnd.gov.tw/TW/News/News_Detail.aspx?CID=213&ID=59225'
NOW='2026-09-12T08:00:00+00:00'
HTML='''<h1>中共解放軍臺海周邊海、空域動態（115年9月10日）</h1>
<p>一、日期：中華民國115年9月9日（星期三）0600時至115年9月10日（星期四）0600時止。</p>
<p>二、活動動態：迄0600時止，偵獲共機18架次（逾越中線進入北部、中部、西南及東部空域共13架次）、共艦8艘及公務船1艘，持續在臺海周邊活動。國軍運用任務機、艦及岸置飛彈系統嚴密監控與應處。</p>'''

class OfficialTests(unittest.TestCase):
    def test_total_subset_and_period(self):
        d,r=parse_report(HTML,URL,NOW)
        self.assertEqual(d,'2026-09-10'); self.assertEqual(r['aircraft'],18)
        self.assertEqual(r['area_aircraft'],13); self.assertEqual(r['ships'],8)
        self.assertEqual(r['government_ships'],1)
        self.assertEqual(r['period_start'],'2026-09-09T06:00:00+08:00')
    def test_zero_and_missing_are_distinct(self):
        h=HTML.replace('18架次','0架次').replace('共13架次','共0架次').replace('共艦8艘','共艦未公布')
        _,r=parse_report(h,URL,NOW)
        self.assertEqual(r['aircraft'],0);self.assertIsNone(r['ships'])
        self.assertEqual(view({'2026-09-10':r})['latest']['aircraft'],0)
    def test_explicit_no_aircraft_report(self):
        h=HTML.replace('共機18架次（逾越中線進入北部、中部、西南及東部空域共13架次）、','')+'<p>三、上述期間未偵獲共機，故無提供航跡圖。</p>'
        self.assertEqual(parse_report(h,URL,NOW)[1]['aircraft'],0)
        with self.assertRaises(ValueError):parse_report(h.replace('上述期間未偵獲共機',''),URL,NOW)

    def test_invalid_period_and_subset_rejected(self):
        for h in [HTML.replace('9月9日','9月8日'),HTML.replace('0600時至','1200時至'),
                  HTML.replace('共13架次','共19架次'),HTML.replace('（115年9月10日）','（115年9月11日）'),
                  HTML.replace('偵獲共機18架次','13架共機逾越中線')]:
            with self.assertRaises(ValueError):parse_report(h,URL,NOW)
        with self.assertRaises(ValueError):parse_report(HTML,URL,'2026-09-09T00:00:00+00:00')
    def test_official_revisions_override_larger_estimates(self):
        date,old=parse_report(HTML,URL,NOW)
        new={**old,'aircraft':6,'checked_at':'2026-09-12T09:00:00+00:00'}
        for left,right in [(old,new),(new,old)]:
            self.assertEqual(_union_days({'days':{date:left}},{'days':{date:right}})[date]['aircraft'],6)
        legacy={'aircraft':27}
        self.assertEqual(_union_days({'days':{date:legacy}},{'days':{date:new}})[date],new)
        self.assertEqual(view({date:legacy})['days'],[])
    def test_links_are_official_and_deduplicated(self):
        h=f'<a href="{URL}">one</a><a href="{URL}">two</a><a href="https://evil.example/">bad</a>'
        self.assertEqual(report_links(h),[URL])

class FailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_failure_preserves_checked_time_and_legacy(self):
        _,row=parse_report(HTML,URL,NOW)
        class Session:
            def get(self,*a,**kw):raise TimeoutError()
        out=await collect(Session(),{'days':{'2026-09-10':row,'2026-09-09':{'aircraft':11}}},datetime.fromisoformat(NOW))
        self.assertEqual(out['days']['2026-09-10'],row)
        self.assertEqual(out['unverified_days']['2026-09-09']['aircraft'],11)
