import gzip
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
from test_comtrade_client import Client, Session, Response, PARAMS
from source_archive import save_comtrade

class ArchiveTests(unittest.IsolatedAsyncioTestCase):
    def test_roundtrip_and_immutable_revisions(self):
        now=datetime(2026,9,12,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as folder:
            row={**PARAMS,'netWgt':0,'isNetWgtEstimated':False,'secret':'excluded'}
            a=save_comtrade(folder,{**PARAMS,'subscription-key':'excluded'},[row],{'2601':0},'authenticated',now)
            self.assertEqual(a,save_comtrade(folder,PARAMS,[row],{'2601':0},'authenticated',now))
            raw=gzip.decompress(a.read_bytes()).decode()
            self.assertNotIn('excluded',raw)
            data=json.loads(raw)
            self.assertEqual(data['weights_kg'],{'2601':0})
            self.assertFalse(data['rows'][0]['isNetWgtEstimated'])
            b=save_comtrade(folder,PARAMS,[{**row,'netWgt':9}],{'2601':9},'authenticated',now)
            self.assertNotEqual(a,b)
            self.assertTrue(a.exists())
            a.write_bytes(gzip.compress(b'corrupt'))
            with self.assertRaises(ValueError): save_comtrade(folder,PARAMS,[row],{'2601':0},'authenticated',now)

    async def test_save_before_return_and_reuse(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'WARHUB_SOURCE_ARCHIVE_DIR':folder}):
            client=Client(); session=Session(Response({'data':[{**PARAMS,'netWgt':42}]}))
            first=await client.query(session,PARAMS)
            first['2601']=999
            self.assertEqual(await client.query(session,PARAMS),{'2601':42})
            self.assertEqual(len(session.calls),1)
            self.assertEqual(client.report()['archived'],1)
            self.assertEqual(len(list(Path(folder).rglob('*.gz'))),1)

    async def test_empty_is_archived_not_zero(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'WARHUB_SOURCE_ARCHIVE_DIR':folder}):
            client=Client(); await client.query(Session(Response({'data':[]})),PARAMS)
            file=next(Path(folder).rglob('*.gz'))
            self.assertEqual(json.loads(gzip.decompress(file.read_bytes()))['weights_kg'],{})
