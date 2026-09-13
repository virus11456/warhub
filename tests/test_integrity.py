import unittest, sys, tempfile, json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import scoring as sc
import fetch_data as f
import alerts
from data_quality import source_health

def market(q,yes=.8): return {'question':q,'yes_price':yes,'volume':100}
class Response:
    status=200
    def __init__(self,value): self.value=value
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
    def raise_for_status(self): pass
    async def json(self,**kwargs): return self.value
    async def text(self): return self.value if isinstance(self.value,str) else json.dumps(self.value)
class Session:
    def __init__(self,value): self.value=value
    def get(self,*args,**kwargs): return Response(self.value)

class Integrity(unittest.TestCase):
    def test_partial_trade_and_old_usda_labels(self):
        health=source_health({'food':{'items':[{'wan_ton':12,'incomplete':True}]},'usda':{'items':[{'week_net_kt':0,'stale':True}]}})
        self.assertEqual(health['food']['status'],'partial')
        self.assertEqual(health['usda']['status'],'stale')

    def test_verified_revision_survives_larger_headline(self):
        from merge_history import _union_days
        verified={'aircraft':12,'verified':True,'source_url':'https://example.test/report'}
        unverified={'aircraft':40,'verified':False}
        for local,remote in [(verified,unverified),(unverified,verified)]:
            self.assertEqual(_union_days({'days':{'2026-09-10':local}},{'days':{'2026-09-10':remote}})['2026-09-10'],verified)

    def test_usda_missing_and_next_year_sales(self):
        from usda import assemble
        release={'marketYear':2027,'marketYearStart':'2026-06-01'}
        record={'weekEndingDate':'2026-09-03T00:00:00','unitId':1,'currentMYNetSales':0,'nextMYNetSales':972000}
        item,rows=assemble('大豆',801,release,[record])
        self.assertEqual(item['week_net_kt'],0)
        self.assertEqual(item['next_year_net_kt'],972)
        self.assertIsNone(item['commit_kt'])
        self.assertTrue(item['incomplete'])
        self.assertEqual(rows[0]['market_year'],2027)
        missing,_=assemble('大豆',801,release,[])
        self.assertIsNone(missing['week_net_kt'])
    def test_usda_wrong_unit_rejected(self):
        from usda import normalize
        self.assertIsNone(normalize({'weekEndingDate':'2026-09-03','unitId':2,'currentMYNetSales':1000},2027)['net'])

    def test_market_filter(self):
        for q in ['Will 7 Fed rate cuts happen in 2026?','Will Iran win the FIFA World Cup?','Will Taiwan elect a president?','Will Counter-Strike release?']:
            self.assertIsNone(sc.market_risk(market(q)))
        self.assertIsNotNone(sc.market_risk(market('Will China invade Taiwan?')))
    def test_peace_direction(self):
        self.assertAlmostEqual(sc.market_risk(market('Russia Ukraine ceasefire?',.8)),20)
        self.assertLess(sc.market_average([market('Russia Ukraine ceasefire?',.9)]),sc.market_average([market('Russia Ukraine ceasefire?',.1)]))
    def test_ambiguous_peace_and_deescalation_excluded(self):
        for q in ['US announces end of Iranian blockade by September 30, 2026?', 'Will Israel break the ceasefire?', 'Will the US lift its blockade?']:
            self.assertIsNone(sc.market_risk(market(q)))
    def test_invalid_values_and_expiration(self):
        for n in [None,float('nan'),float('inf'),-1,2]:
            self.assertIsNone(sc.market_risk(market('Will China invade Taiwan?',n)))
        self.assertIsNone(sc.market_risk({**market('Will China invade Taiwan?'),'end_date':'2020-01-01T00:00:00Z'}))
    def test_outcome_order(self):
        self.assertEqual(f._parse_outcome_prices({'outcomes':'["No","Yes"]','outcomePrices':'["0.2","0.8"]'}),(.8,.2))
    def test_missing_is_not_safe(self):
        s=sc.calculate_wpi(None,[])
        self.assertIsNone(s['combined_score']); self.assertEqual(s['alert_level'],'INSUFFICIENT_DATA')
    def test_stale_excluded(self):
        s=sc.calculate_wpi(None,[],gdelt={'ukraine':{'latest':10,'stale':True}})
        self.assertIsNone(s['factors']['g']);self.assertEqual(s['coverage'],0)
    def test_fire_not_war_probability(self):
        s=sc.calculate_wpi(None,[],firms={'total_24h':500000,'delta_ratio':20})
        self.assertIsNone(s['factors']['f'])
    def test_wpi_coverage(self):
        s=sc.calculate_wpi(20,[market('Will China invade Taiwan?')],aviation={'summary':{'anomaly_pct':30}},wikipedia={'score':20})
        self.assertIsNotNone(s['combined_score']);self.assertEqual(s['coverage'],.68)
    def test_region_no_false_zero(self):
        regions=f.build_region_risks([],{}, {'error':'failed'}, {'error':'failed'})
        self.assertTrue(all(r['score'] is None for r in regions))
    def test_complete_counts_are_observations(self):
        regions=f.build_region_risks([],{}, {'conflict_counts':{'ukraine':100},'conflict_hotspots':[]},{'region_counts':{'歐洲':90},'aircraft':[]})
        r=next(r for r in regions if r['key']=='ukraine')
        self.assertEqual(r['factors']['firms_hotspots'],100);self.assertEqual(r['factors']['avi_count'],90)
    def test_unknown_pizza_not_closed(self):
        shops=f.transform_pizza_shops({})
        self.assertTrue(all(s['busyness'] is None and s['status']=='unavailable' for s in shops))
    def test_null_digest(self):
        d={'score':sc.calculate_wpi(None,[]),'regions':f.build_region_risks([],{}, {},{})}
        self.assertIn('資料不足',alerts.build_digest(d))
    def test_seismic_archive_and_chf(self):
        with tempfile.TemporaryDirectory() as td, patch.object(f,'METRICS_DAILY_FILE',Path(td)/'daily.json'), patch.object(f,'DATA_FILE',Path(td)/'none.json'):
            s=f.update_daily_metrics(sc.calculate_wpi(None,[]),None,None,{},None,None,{'total_72h':3},[],{'USDCHF=X':{'dev':-6}})
            r=next(iter(s.values()));self.assertEqual(r['seismic'],3);self.assertIsNone(r['fin']['risk_off_cluster']);self.assertTrue(r['fin']['risk_off_signals']['chf']);self.assertEqual(r['fin']['risk_off_observed'],1)

class Sources(unittest.IsolatedAsyncioTestCase):
    async def test_besttime_http_failure_not_closed(self):
        class Failed(Response):
            status=403
        class BarsSession:
            def post(self,*args,**kwargs): return Failed({})
        with patch.dict('os.environ',{'BESTTIME_API_KEY':'test-only'}), patch.object(f,'ZoneInfo',None):
            result=await f.fetch_bars(BarsSession())
        self.assertFalse(result['available'])
        self.assertIn('來源請求',result['reason'])
        self.assertTrue(all(b['http_status']==403 for b in result['bars']))

    async def test_comtrade_coverage_is_per_product(self):
        from unittest.mock import AsyncMock
        with patch.object(f, 'FOOD_EXPORTERS', [('842','US'),('76','Brazil')]), patch.object(f, '_comtrade_month', AsyncMock(side_effect=[{'1201':0},{'1001':1000}])), patch.object(f.asyncio,'sleep',AsyncMock()):
            totals,count,us,coverage=await f._food_mirror_total(None,202601)
            self.assertEqual(totals['1201'],0)
            self.assertNotIn('1005',totals)
            self.assertEqual(coverage['1201'],['842'])
            self.assertEqual(coverage['1001'],['76'])
            self.assertEqual(coverage['1005'],[])

    async def test_eonet_v3(self):
        result=await f.fetch_eonet(Session({'events':[{'geometry':[{'date':'2026-01-01','coordinates':[1,2]},{'date':'2026-01-02','coordinates':[3,4]}]}]}))
        self.assertEqual(result[0]['lat'],4);self.assertEqual(result[0]['date'],'2026-01-02')
    async def test_comtrade_empty_not_zero(self):
        self.assertIsNone(await f._comtrade_one(Session({'data':[]}), '36','2601',202601))
    async def test_firms_bad_csv(self):
        d=await f.fetch_firms(Session('<html>failure</html>'))
        self.assertIn('error',d)
    async def test_aircraft_counts_before_slice(self):
        d=await f.fetch_aviation(Session({'ac':[{'t':'E3','lat':48,'lon':2,'alt_baro':20000,'hex':str(i)} for i in range(50)]}))
        self.assertEqual(len(d['aircraft']),30);self.assertEqual(d['region_counts']['歐洲'],50)
if __name__=='__main__': unittest.main()

class Pipeline(unittest.IsolatedAsyncioTestCase):
    async def test_full_pipeline_with_missing_sources(self):
        from contextlib import ExitStack
        from unittest.mock import AsyncMock
        funcs=['pizzint','aviation','firms','gdelt','food_imports','usda_esr','nuclear_seismic','wikipedia_anxiety','notams','bars','strategic_imports','pla_sorties','finance','fred']
        lists=['polymarket','eonet','gnews','food_history','strategic_history','tw_military_news']
        with tempfile.TemporaryDirectory() as td, ExitStack() as stack:
            stack.enter_context(patch.dict('os.environ',{'WARHUB_NO_NOTIFY':'1'}))
            stack.enter_context(patch.object(f,'DATA_DIR',Path(td)))
            for name in ['DATA_FILE','HISTORY_FILE','METRICS_DAILY_FILE']:
                stack.enter_context(patch.object(f,name,Path(td)/(name+'.json')))
            for name in funcs+lists:
                value=[] if name in lists else {}
                if name=='aviation':value={'error':'missing'}
                stack.enter_context(patch.object(f,'fetch_'+name,AsyncMock(return_value=value)))
            await f.main()
            data=json.loads(f.DATA_FILE.read_text())
            self.assertIsNone(data['score']['combined_score'])
            self.assertEqual(data['source_health']['pizza']['status'],'unavailable')
            self.assertNotIn('_notify',data)

    async def test_fast_pipeline_preserves_slow_data_without_querying_it(self):
        from contextlib import ExitStack
        from unittest.mock import AsyncMock
        import copy
        funcs=['pizzint','aviation','firms','gdelt','nuclear_seismic','wikipedia_anxiety','notams','bars','pla_sorties','finance']
        lists=['polymarket','eonet','gnews','tw_military_news']
        previous={'food': {'schema_version':2, 'updated_at':'2026-09-01T00:00:00+00:00', 'items':[{'wan_ton':12}]},
                  'usda':None, 'strat':{}, 'fred':{}, 'food_hist':[{'month':'2026-07'}], 'strat_hist':[]}
        original=copy.deepcopy(previous)
        with tempfile.TemporaryDirectory() as td, ExitStack() as stack:
            stack.enter_context(patch.dict('os.environ',{'WARHUB_NO_NOTIFY':'1','WARHUB_COLLECTION_MODE':'fast'}))
            stack.enter_context(patch.object(f,'DATA_DIR',Path(td)))
            for name in ['DATA_FILE','HISTORY_FILE','METRICS_DAILY_FILE']:
                stack.enter_context(patch.object(f,name,Path(td)/(name+'.json')))
            f.DATA_FILE.write_text(json.dumps(previous))
            slow=[]
            for name in ['food_imports','usda_esr','strategic_imports','fred','food_history','strategic_history']:
                slow.append(stack.enter_context(patch.object(f,'fetch_'+name,AsyncMock(side_effect=AssertionError('slow source queried')))))
            for name in funcs+lists:
                value=[] if name in lists else {}
                if name=='aviation':value={'error':'missing'}
                stack.enter_context(patch.object(f,'fetch_'+name,AsyncMock(return_value=value)))
            await f.main()
            data=json.loads(f.DATA_FILE.read_text())
            for key,value in original.items(): self.assertEqual(data[key],value)
            for mock in slow: mock.assert_not_called()
            self.assertEqual(data['source_health']['food']['status'],'stale')
            self.assertIn('polymarket',data['collection']['duration_seconds'])
            self.assertNotIn('food_imports',data['collection']['duration_seconds'])
            self.assertNotIn('_notify',data)
