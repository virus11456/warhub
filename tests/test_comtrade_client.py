import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from comtrade_client import Client, parse_weights

PARAMS = dict(reporterCode='36', period='202607', flowCode='X', partnerCode='156',
              partner2Code='0', motCode='0', customsCode='C00', cmdCode='2601')

class Response:
    status = 200
    headers = {}
    def __init__(self, body, status=200): self.body=body; self.status=status
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    def raise_for_status(self): pass
    async def json(self, **kwargs): return self.body

class Session:
    def __init__(self, response): self.response=response; self.calls=[]
    def get(self, url, **kwargs): self.calls.append((url,kwargs)); return self.response

class Tests(unittest.IsolatedAsyncioTestCase):
    def test_scope_weight_and_duplicates(self):
        row={**PARAMS, 'netWgt':0}
        self.assertEqual(parse_weights({'data':[row]}, PARAMS), {'2601':0})
        self.assertEqual(parse_weights({'data':[{**row,'netWgt':None}]},PARAMS),{})
        for rows in ([{**row,'partnerCode':0}], [row,row], [{**row,'netWgt':-1}], [{**row,'netWgt':float('nan')}]):
            with self.assertRaises(ValueError): parse_weights({'data':rows},PARAMS)
        with self.assertRaises(ValueError): parse_weights({'error':'bad','data':[]},PARAMS)

    async def test_auth_header_and_shared_spacing(self):
        with patch.dict(os.environ, {'COMTRADE_API_KEY':'test-only'}): client=Client()
        session=Session(Response({'data':[{**PARAMS,'netWgt':42}]}))
        with patch('comtrade_client.asyncio.sleep',new_callable=AsyncMock) as sleep:
            self.assertEqual(await client.query(session,PARAMS),{'2601':42})
            await client.query(session,{**PARAMS, 'cmdCode':'1001'})
            self.assertGreater(sleep.call_args.args[0],0)
        url, options=session.calls[0]
        self.assertIn('/data/v1/get/',url)
        self.assertEqual(options['headers']['Ocp-Apim-Subscription-Key'],'test-only')
        self.assertNotIn('test-only',url)
        self.assertNotIn('test-only',str(client.report()))

    async def test_rate_limit_stops_and_persists_cooldown(self):
        client=Client(); session=Session(Response({},429))
        self.assertIsNone(await client.query(session,PARAMS))
        await client.query(session,PARAMS)
        self.assertEqual(len(session.calls),1)
        restored=Client(client.report())
        await restored.query(session,PARAMS)
        self.assertEqual(len(session.calls),1)

    async def test_public_and_budget(self):
        with patch.dict(os.environ, {'COMTRADE_API_KEY':''}): client=Client()
        session=Session(Response({'data':[]}))
        self.assertEqual(await client.query(session,PARAMS),{})
        self.assertIn('/public/v1/preview/',session.calls[0][0])
        self.assertNotIn('Ocp-Apim-Subscription-Key',session.calls[0][1]['headers'])
        client.requests=80
        self.assertIsNone(await client.query(session,{**PARAMS, 'period':'202608'}))
        self.assertEqual(len(session.calls),1)
