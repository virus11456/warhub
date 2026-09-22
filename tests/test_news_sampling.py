import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import news_sampling as n
NOW=datetime(2026,9,22,10,tzinfo=timezone.utc)
class Tests(unittest.TestCase):
    def batch(self, region, count=50):
        return {'status':'available','items':[{'title':f'{region} news {i}','url':f'https://example.test/{region}/{i}',
            'domain':'one publisher','ts':NOW.isoformat(),'region':region,'topic':n.TOPICS[region]} for i in range(count)]}

    def test_balanced_display_and_original_archive_not_mutated(self):
        batches={k:self.batch(k) for k in n.QUERIES}
        data=n.merge_samples({},batches,NOW); original=copy.deepcopy(data)
        shown=n.headlines(data,NOW)
        self.assertEqual(len(shown),15)
        self.assertEqual({k:sum(r['region']==k for r in shown) for k in n.QUERIES},dict.fromkeys(n.QUERIES,3))
        shown[0]['title']='translated'
        self.assertEqual(data,original)
        self.assertEqual(data['by_region']['taiwan']['source_names_24h'],1)

    def test_failure_not_zero_and_first_seen_preserved(self):
        first=n.merge_samples({}, {'taiwan':self.batch('taiwan',1)}, NOW)
        old=copy.deepcopy(first)
        second=n.merge_samples(first, {}, NOW+timedelta(hours=2))
        r=second['by_region']['taiwan']
        self.assertIsNone(r['sample_24h'])
        self.assertEqual(r['observed_at'],NOW.isoformat())
        self.assertEqual(r['records'][0]['first_seen_at'],NOW.isoformat())
        self.assertEqual(first,old)
        third=n.merge_samples(second, {'taiwan':self.batch('taiwan',1)}, NOW+timedelta(hours=4))
        self.assertEqual(len(third['by_region']['taiwan']['records']),1)
        self.assertEqual(third['by_region']['taiwan']['records'][0]['ts'],NOW.isoformat())

    def test_valid_empty_zero_and_retention(self):
        first=n.merge_samples({}, {'taiwan':self.batch('taiwan',1)}, NOW)
        second=n.merge_samples(first, {'taiwan':{'status':'available','items':[]}}, NOW+timedelta(days=91))
        self.assertEqual(second['by_region']['taiwan']['sample_24h'],0)
        self.assertEqual(second['by_region']['taiwan']['records'],[])

    def test_rss_dedup_sort_limit_and_invalid_response(self):
        import email.utils
        date=email.utils.format_datetime(NOW)
        xml='<rss><channel>'+''.join(f'<item><title>Headline {i} - Media</title><link>https://example.test/{i}</link><pubDate>{date}</pubDate><source>Media</source></item>' for i in list(range(60))+[0])+'</channel></rss>'
        rows=n.parse_rss(xml,'taiwan',NOW)
        self.assertEqual(len(rows),50); self.assertEqual(rows[0]['title'],'Headline 0')
        with self.assertRaises(ValueError):n.parse_rss('<html/>','taiwan',NOW)

class CollectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_collector_queries_five_regions_and_keeps_archive_out_of_public_summary(self):
        import json, tempfile
        from unittest.mock import patch, AsyncMock
        import fetch_data as f
        from test_notac_client import Session, Response
        class RSS(Response):
            def raise_for_status(self):
                if self.status != 200: raise RuntimeError('source unavailable')
            async def iter_chunked(self, size):
                yield self.payload.encode()
        raw='<rss><channel><item><title>Example</title><link>https://example.test/a</link><source>Media</source><pubDate>Tue, 22 Sep 2026 10:00:00 +0000</pubDate></item></channel></rss>'
        from datetime import datetime
        class Clock:
            @staticmethod
            def now(tz):return NOW
        with tempfile.TemporaryDirectory() as td, patch.object(f,'DATA_DIR',Path(td)), patch.object(f,'DATA_FILE',Path(td)/'data.json'), patch.object(f,'datetime',Clock), patch.object(f,'_translate_titles',AsyncMock()) as translate, patch.object(f.asyncio,'sleep',AsyncMock()):
            session=Session(*(RSS(raw) for _ in range(5)))
            result=await f.fetch_gnews(session)
            self.assertEqual(len(session.calls),5)
            self.assertEqual(len({c[1]['params']['q'] for c in session.calls}),5)
            stored=json.loads((Path(td)/'news_samples.json').read_text())
            self.assertEqual(len(stored['by_region']['taiwan']['records']),1)
            self.assertNotIn('records',result['sampling']['by_region']['taiwan'])
            translate.assert_awaited_once()
            # A throttled source stops the other requests, preserves original observations.
            retry=Session(RSS('',429))
            result2=await f.fetch_gnews(retry)
            self.assertEqual(len(retry.calls),1)
            self.assertTrue(all(row['stale'] for row in result2['headlines']))
            self.assertIsNone(result2['sampling']['by_region']['taiwan']['sample_24h'])
            self.assertEqual(result2['sampling']['by_region']['taiwan']['observed_at'],NOW.isoformat())
            (Path(td)/'news_samples.json').write_text('broken')
            with self.assertRaises(ValueError): await f.fetch_gnews(Session())

class PublicationTests(unittest.TestCase):
    def test_union_preserves_earliest_first_seen_and_latest_status(self):
        import json,tempfile
        from unittest.mock import patch
        import merge_history as m
        original=Tests().batch('taiwan',1)
        remote=n.merge_samples({}, {'taiwan':original},NOW)
        local=n.merge_samples({}, {'taiwan':original},NOW+timedelta(hours=2))
        with tempfile.TemporaryDirectory() as td, patch.object(m,'DATA_DIR',Path(td)), patch.object(m.subprocess,'check_output',side_effect=['data/news_samples.json',json.dumps(remote).encode()]):
            path=Path(td)/'news_samples.json'; path.write_text(json.dumps(local))
            m.merge_news_samples(NOW+timedelta(hours=2))
            saved=json.loads(path.read_text())['by_region']['taiwan']
            self.assertEqual(saved['records'][0]['first_seen_at'],NOW.isoformat())
            self.assertEqual(saved['attempted_at'],(NOW+timedelta(hours=2)).isoformat())

    def test_corrupt_remote_stops_without_overwriting_local(self):
        import tempfile
        from unittest.mock import patch
        import merge_history as m
        with tempfile.TemporaryDirectory() as td, patch.object(m,'DATA_DIR',Path(td)), patch.object(m.subprocess,'check_output',side_effect=['data/news_samples.json',b'broken']):
            path=Path(td)/'news_samples.json'; path.write_text('local original')
            with self.assertRaises(ValueError):m.merge_news_samples(NOW)
            self.assertEqual(path.read_text(),'local original')

    def test_archive_includes_optional_sample_file(self):
        import gzip,json,tempfile
        import archive_snapshot as a
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'data';source.mkdir()
            for name in a.FILES:
                (source/name).write_text(json.dumps({'updated_at':NOW.isoformat()} if name=='data.json' else {}))
            samples=n.merge_samples({}, {}, NOW)
            (source/'news_samples.json').write_text(json.dumps(samples))
            archived=a.archive_snapshot(source,Path(td)/'archives','fixture')
            payload=json.loads(gzip.decompress(archived.read_bytes()))
            self.assertEqual(payload['files']['news_samples.json'],samples)
