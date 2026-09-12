import unittest,sys
from pathlib import Path
from datetime import datetime,timezone,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from trade_availability import Availability,MAX_REQUESTS

class Response:
 status=200
 def __init__(self,body):self.body=body
 async def __aenter__(self):return self
 async def __aexit__(self,*a):pass
 def raise_for_status(self):pass
 async def json(self,**kw):return self.body
class Session:
 def __init__(self,body):self.body=body;self.calls=0
 def get(self,*a,**kw):self.calls+=1;return Response(self.body)

class CatalogTests(unittest.IsolatedAsyncioTestCase):
 async def test_empty_catalog_skips_and_is_cached_without_renewal(self):
  s=Session({'count':0,'data':[],'error':''});a=Availability()
  self.assertFalse(await a.query(s,'36',202607));stamp=a.cache['36:202607']['checked_at']
  self.assertFalse(await a.query(s,'36',202607));self.assertEqual(s.calls,1)
  self.assertEqual(a.cache['36:202607']['checked_at'],stamp)
 async def test_failure_and_wrong_scope_never_mean_missing(self):
  for body in [{'count':0,'data':[],'error':'rate limit'},{'count':1,'data':[{'reporterCode':999,'period':202607}]}]:
   a=Availability();s=Session(body)
   self.assertTrue(await a.query(s,'36',202607));self.assertTrue(a.stopped)
   self.assertTrue(await a.query(s,'76',202607));self.assertEqual(s.calls,1)
 async def test_valid_dataset_is_not_commodity_coverage(self):
  a=Availability();s=Session({'count':1,'error':'','data':[{'reporterCode':36,'period':202607,'freqCode':'M','typeCode':'C','classificationSearchCode':'HS'}]})
  self.assertTrue(await a.query(s,'36',202607));self.assertEqual(a.cache['36:202607']['status'],'available')
 async def test_budget_and_expired_negative_fail_open(self):
  a=Availability();s=Session({'count':0,'data':[]})
  for n in range(MAX_REQUESTS):self.assertFalse(await a.query(s,str(n),202607))
  old=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
  a.cache['36:202607']={'status':'not_listed','checked_at':old}
  self.assertTrue(await a.query(s,'36',202607));self.assertEqual(s.calls,MAX_REQUESTS)
