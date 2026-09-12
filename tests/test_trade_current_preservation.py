import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from trade_quality import preserve_current_coverage, enrich

class Tests(unittest.TestCase):
    def setUp(self):
        self.old={'schema_version':2,'ref_month':'2026-07','updated_at':'2026-09-11T00:00:00+00:00',
                  'items':[{'cmd':'2601','wan_ton':90,'reporter_codes':['36','76'],'yoy_pct':20}]}
        self.new=copy.deepcopy(self.old)
        self.new['updated_at']='2026-09-12T00:00:00+00:00'

    def test_partial_retains_snapshot_and_original_time(self):
        self.new['items'][0].update(wan_ton=60,reporter_codes=['36'])
        result=preserve_current_coverage(self.old,self.new)
        self.assertEqual(result['items'],self.old['items'])
        self.assertEqual(result['updated_at'],self.old['updated_at'])
        self.assertEqual(result['last_attempted_at'],self.new['updated_at'])
        self.assertTrue(result['stale'])
        self.assertEqual(enrich({'strat':result})['strat']['items'][0]['yoy_pct'],None)

    def test_same_coverage_can_revise_down_to_zero(self):
        self.new['items'][0]['wan_ton']=0
        self.assertIs(preserve_current_coverage(self.old,self.new),self.new)

    def test_new_month_is_not_blended_with_old(self):
        self.new['ref_month']='2026-08'
        self.new['items'][0].update(wan_ton=1,reporter_codes=['36'])
        self.assertIs(preserve_current_coverage(self.old,self.new),self.new)
        self.new['ref_month']='2026-06'
        self.assertEqual(preserve_current_coverage(self.old,self.new)['ref_month'],'2026-07')

    def test_changed_reporter_set_is_not_better_coverage(self):
        self.new['items'][0]['reporter_codes']=['36','710']
        self.assertTrue(preserve_current_coverage(self.old,self.new)['stale'])
        self.new['items'][0]['reporter_codes']=['36','76','710']
        self.assertIs(preserve_current_coverage(self.old,self.new),self.new)

    def test_previous_year_coverage_is_preserved(self):
        self.old['prev_year_month']=self.new['prev_year_month']='2025-07'
        self.old['items'][0].update(prev_wan_ton=85,reporter_codes_prev=['36','76'])
        self.new['items'][0].update(prev_wan_ton=60,reporter_codes_prev=['36'])
        result=preserve_current_coverage(self.old,self.new)
        self.assertEqual(result['refresh_status'],'baseline_coverage_regressed')
        self.assertEqual(result['items'][0]['prev_wan_ton'],85)
