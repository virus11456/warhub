import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from kalshi_market_data import normalize, reviewed_pair

class KalshiAdapterTests(unittest.TestCase):
    def raw(self, **changes):
        # Synthetic fixture; this is not an actual market or price observation.
        return {'ticker':'TEST-EXAMPLE-YES','market_type':'binary','title':'Synthetic test contract',
                'status':'active','close_time':'2030-01-01T00:00:00Z','yes_bid_dollars':'0.3200',
                'yes_ask_dollars':'0.3600','yes_bid_size_fp':'3.00','yes_ask_size_fp':'4.00',**changes}
    def parse(self, **changes):return normalize(self.raw(**changes),'2026-09-22T00:00:00Z')
    def test_bid_ask_not_last_trade(self):
        r=self.parse(last_price_dollars='0.95');self.assertEqual(r['display_midpoint'],.34);self.assertEqual(r['last_price'],.95);self.assertIsNone(r['quote_observed_at'])
    def test_zero_retained_but_empty_book_not_probability(self):
        r=self.parse(yes_bid_dollars='0',yes_ask_dollars='0',yes_bid_size_fp='0');self.assertEqual(r['yes_bid'],0);self.assertIsNone(r['display_midpoint'])
    def test_invalid_or_crossed_quotes(self):
        for v in [None,True,'NaN','Infinity','1.2','-0.1']:
            self.assertIsNone(self.parse(yes_bid_dollars=v)['display_midpoint'])
        self.assertIsNone(self.parse(yes_bid_dollars='.8')['display_midpoint'])
    def test_closed_and_expired(self):
        self.assertIsNone(self.parse(status='closed')['display_midpoint'])
        self.assertIsNone(self.parse(close_time='2020-01-01T00:00:00Z')['display_midpoint'])
    def test_rule_change_changes_identity(self):
        self.assertNotEqual(self.parse()['rules_fingerprint'],self.parse(rules_primary='Different rule')['rules_fingerprint'])
    def test_explicit_review_required_and_rules_change_invalidates(self):
        a=self.parse();b={**a,'provider':'polymarket','id':'polymarket:synthetic'}
        self.assertFalse(reviewed_pair(a,b,{}))
        review={'status':'equivalent','evidence':['fixture'],'reviewed_at':'2026-09-22T00:00:00Z','contracts':{a['id']:a['rules_fingerprint'],b['id']:b['rules_fingerprint']},'event_definition':'synthetic','event_deadline':'2030-01-01T00:00:00Z','same_resolution_criteria':True,'same_yes_direction':True}
        self.assertTrue(reviewed_pair(a,b,review));self.assertFalse(reviewed_pair({**a,'rules_fingerprint':'changed'},b,review))
    def test_same_selection_as_existing_polymarket(self):
        from kalshi_market_data import select_markets
        from market_selection import selected_market_risk
        from scoring import market_risk
        # Snapshot of the existing collector's exclusions, intentionally independent.
        exclusions=['world cup','fifa','olympic','super bowl','nba','nfl','mlb','premier league','champions league','grammy','oscar','album','box office','bitcoin','ethereum','eurovision','tiktok','counter-strike','esports','valorant','dota']
        cases={'Will China invade Taiwan?':True,'Russia Ukraine ceasefire before GTA VI?':True,
               'Will Iran win the FIFA World Cup?':False,'Will Taiwan hold an election?':False,
               'Will there be a nuclear test?':True,'Will there be an NBA strike?':False,
               'Will this album be called War?':False,'Will global warming rise?':False,
               'Will Iran avoid a military attack?':False,'Will Ukraine end the war?':False,
               'Will Iran announce a peace agreement?':True,'Will China GDP rise?':False}
        for title, expected in cases.items():
            with self.subTest(title=title):
                candidate={'question':title,'yes_price':.34,'end_date':'2030-01-01T00:00:00Z'}
                original=None if any(e in title.lower() for e in exclusions) else market_risk(candidate)
                self.assertEqual(selected_market_risk(candidate),original)
                result=select_markets([self.raw(title=title)],'2026-09-22T00:00:00Z')
                self.assertEqual(bool(result),expected)
    def test_peace_direction_and_dedup(self):
        from kalshi_market_data import select_markets
        raw=self.raw(title='Russia Ukraine ceasefire?')
        result=select_markets([raw,raw,None],'2026-09-22T00:00:00Z')
        self.assertEqual(len(result),1);self.assertEqual(result[0]['event_direction'],'deescalation')
        self.assertNotIn('risk_score',result[0])
    def test_selected_market_still_requires_usable_quotes(self):
        from kalshi_market_data import select_markets
        raw=self.raw(title='Will China invade Taiwan?',yes_bid_size_fp='0')
        self.assertEqual(select_markets([raw],'2026-09-22T00:00:00Z'),[])

class PolymarketCollectorParity(unittest.IsolatedAsyncioTestCase):
    async def test_excluded_malformed_market_cannot_abort_later_valid_market(self):
        from unittest.mock import patch, AsyncMock
        import fetch_data
        class Response:
            status=200
            def __init__(self,data):self.data=data
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            def raise_for_status(self):pass
            async def json(self):return self.data
        class Session:
            def get(self,url,**kwargs):
                if '/tags/' in url:return Response({'id':1})
                return Response([
                    {'id':'excluded','question':'Will a war movie win an Oscar?','outcomes':['Yes','No'],'outcomePrices':[.5,.5],'volume':'invalid'},
                    {'id':'valid','question':'Will China invade Taiwan?','outcomes':['No','Yes'],'outcomePrices':[.7,.3],'volume':100,'endDate':'2030-01-01T00:00:00Z'}])
        with patch.object(fetch_data,'_translate_market_questions',AsyncMock()):
            result=await fetch_data.fetch_polymarket(Session())
        self.assertEqual([m['id'] for m in result],['valid'])
        self.assertEqual(result[0]['yes_price'],.3)
        self.assertEqual(result[0]['risk_score'],30)
