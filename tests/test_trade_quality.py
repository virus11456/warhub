import sys,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from trade_quality import enrich,EXPECTED,preserve_food_coverage
import fetch_data as f

class TradeQuality(unittest.TestCase):
 def snapshot(self):
  reps=EXPECTED['strat']['4001']
  return {'strat':{'schema_version':2,'ref_month':'2026-07','items':[{'cmd':'4001','wan_ton':2,'prev_wan_ton':1,'yoy_pct':100,'reporter_codes':reps,'reporter_codes_prev':reps}]},'strat_hist':[]}
 def test_configuration_matches_collector(self):
  self.assertEqual(set(EXPECTED['food']['1201']),{r for r,n in f.FOOD_EXPORTERS})
  for m in f.STRAT_MATERIALS:self.assertEqual(set(EXPECTED['strat'][m['cmd']]),{r for r,n in m['exp']})
 def test_same_country_count_with_different_members_is_not_comparable(self):
  x=self.snapshot();x['strat']['items'][0]['reporter_codes_prev']=['764','360','458','999']
  it=enrich(x)['strat']['items'][0]
  self.assertTrue(it['current_complete']);self.assertIsNone(it['yoy_pct'])
  self.assertEqual(it['comparison_status'],'baseline_unavailable')
 def test_latest_complete_rejects_legacy_partial_and_direct_reporting(self):
  x=self.snapshot();x['strat']['items'][0]['reporter_codes']=[]
  base={'schema_version':2,'src':'mirror','coverage':{'4001':EXPECTED['strat']['4001']},'4001':0}
  x['strat_hist']=[dict(base,ym='2026-03'),dict(base,ym='2026-04',src='china'),dict(base,ym='2026-05',coverage={'4001':['764']}),dict(base,ym='2026-06',schema_version=1)]
  it=enrich(x)['strat']['items'][0]
  self.assertEqual(it['latest_complete']['month'],'2026-03');self.assertEqual(it['latest_complete']['wan_ton'],0)
 def test_zero_base_stale_and_rounding(self):
  x=self.snapshot();x['strat']['items'][0]['yoy_pct']=99.8
  self.assertEqual(enrich(x)['strat']['items'][0]['yoy_pct'],99.8)
  for mode in ['zero','stale']:
   x=self.snapshot()
   if mode=='zero':x['strat']['items'][0]['prev_wan_ton']=0
   else:x['strat']['stale']=True
   self.assertIsNone(enrich(x)['strat']['items'][0]['yoy_pct'])
 def test_food_partial_refresh_preserves_whole_observation(self):
  old={'schema_version':2,'src':'mirror','soy':12,'us_soy':4,'coverage':{'1201':['76','842']}}
  new={'schema_version':2,'src':'mirror','soy':3,'us_soy':3,'coverage':{'1201':['842']}}
  result=preserve_food_coverage(old,new)
  self.assertEqual(result['soy'],12);self.assertEqual(result['us_soy'],4)
  self.assertEqual(set(result['coverage']['1201']),{'76','842'})
