import sys,json,unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import AsyncMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from kalshi_client import collect
NOW=datetime(2026,9,22,tzinfo=timezone.utc)
class Content:
 def __init__(self,payload):self.payload=payload
 async def iter_chunked(self,size):yield json.dumps(self.payload).encode()
class Response:
 def __init__(self,payload,status=200):self.content=Content(payload);self.status=status;self.headers={}
 async def __aenter__(self):return self
 async def __aexit__(self,*args):pass
class Session:
 def __init__(self,rows):self.rows=iter(rows);self.calls=[]
 def get(self,*args,**kwargs):self.calls.append((args,kwargs));return next(self.rows)
class KalshiClientTests(unittest.IsolatedAsyncioTestCase):
 async def test_disabled_never_calls_network(self):
  s=Session([]);r=await collect(s,['TEST'],now=NOW);self.assertEqual(s.calls,[]);self.assertEqual(r['status'],'authorization_pending')
 async def test_complete_empty_is_distinct_from_failure(self):
  r=await collect(Session([Response({'markets':[],'cursor':''})]),['TEST'],authorized=True,now=NOW)
  self.assertTrue(r['complete']);self.assertEqual(r['status'],'available');self.assertEqual(r['markets'],[])
 async def test_rate_limit_stops_all_series_without_retry(self):
  s=Session([Response({},429)]);r=await collect(s,['A','B'],authorized=True,now=NOW)
  self.assertEqual(len(s.calls),1);self.assertEqual(r['reason'],'rate_limited');self.assertIsNotNone(r['retry_at']);self.assertIsNone(r['fetched_at'])
 async def test_page_budget_is_not_complete(self):
  pages=[Response({'markets':[],'cursor':str(i)}) for i in range(3)]
  with patch('kalshi_client.asyncio.sleep',AsyncMock()):r=await collect(Session(pages),['TEST'],authorized=True,now=NOW)
  self.assertEqual(r['requests'],3);self.assertFalse(r['complete']);self.assertEqual(r['reason'],'page_budget')
 async def test_repeated_cursor_is_rejected(self):
  s=Session([Response({'markets':[],'cursor':'same'}),Response({'markets':[],'cursor':'same'})])
  with patch('kalshi_client.asyncio.sleep',AsyncMock()):r=await collect(s,['TEST'],authorized=True,now=NOW)
  self.assertEqual(r['reason'],'invalid_or_unavailable');self.assertEqual(r['requests'],2)
 async def test_no_redirects_or_secrets(self):
  s=Session([Response({'markets':[]})]);await collect(s,['TEST'],authorized=True,now=NOW)
  self.assertFalse(s.calls[0][1]['allow_redirects']);self.assertNotIn('headers',s.calls[0][1])


class KalshiRefreshTests(unittest.IsolatedAsyncioTestCase):
 async def test_persistent_cooldown_does_not_call_api_or_change_source_time(self):
  from kalshi_client import refresh
  old={'retry_at':'2026-09-22T01:00:00Z','fetched_at':'2026-09-21T12:00:00Z','status':'partial','markets':[{'display_midpoint':0}]}
  frozen=json.dumps(old,sort_keys=True);session=Session([])
  r=await refresh(session,['TEST'],old,authorized=True,now=NOW)
  self.assertEqual(session.calls,[]);self.assertEqual(r['fetched_at'],old['fetched_at']);self.assertEqual(r['status'],'stale');self.assertEqual(json.dumps(old,sort_keys=True),frozen)
 async def test_failed_refresh_preserves_prices_with_old_time(self):
  from kalshi_client import refresh
  old={'fetched_at':'2026-09-21T12:00:00Z','markets':[{'display_midpoint':0}]}
  r=await refresh(Session([Response({},503)]),['TEST'],old,authorized=True,now=NOW)
  self.assertEqual(r['status'],'stale');self.assertEqual(r['markets'],old['markets']);self.assertEqual(r['fetched_at'],old['fetched_at']);self.assertFalse(r['complete'])
 async def test_successful_empty_result_does_not_resurrect_old_market(self):
  from kalshi_client import refresh
  old={'fetched_at':'2026-09-21T12:00:00Z','markets':[{'display_midpoint':.5}]}
  r=await refresh(Session([Response({'markets':[]})]),['TEST'],old,authorized=True,now=NOW)
  self.assertEqual(r['markets'],[]);self.assertEqual(r['status'],'available');self.assertTrue(r['complete'])
 async def test_recent_failed_attempt_still_respects_interval(self):
  from kalshi_client import refresh
  session=Session([])
  r=await refresh(session,['TEST'],{'attempted_at':'2026-09-21T23:00:00Z','status':'unavailable'},authorized=True,now=NOW)
  self.assertEqual(session.calls,[]);self.assertEqual(r['reuse_reason'],'collection_interval')
