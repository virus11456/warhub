import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from translations import cached_titles, update_cache, translate_groq, CACHE_LIMIT

class Response:
    def __init__(self, status, rows): self.status, self.rows = status, rows
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def json(self, **kwargs):
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'translations':self.rows})}}]}

class Session:
    def __init__(self, status=200, rows=None): self.status, self.rows, self.calls = status, rows, []
    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        inputs=json.loads(kwargs['json']['messages'][1]['content'])
        rows=self.rows if self.rows is not None else [{'id':r['id'],'text':f"中文標題 {r['id']}"} for r in reversed(inputs)]
        return Response(self.status,rows)

class CacheTests(unittest.TestCase):
    def test_translations_survive_disappearing_titles_and_sources_stay_separate(self):
        old={'news':[{'title_en':'same','title_zh':'新聞標題'}], 'polymarket':[{'question':'same','question_zh':'市場題目'}]}
        cache=update_cache(old,[],[])
        next_snapshot={'translation_cache':cache, 'news':[], 'polymarket':[]}
        self.assertEqual(cached_titles(next_snapshot,'news'),{'same':'新聞標題'})
        self.assertEqual(cached_titles(next_snapshot,'polymarket'),{'same':'市場題目'})
        self.assertNotIn('different',cached_titles(next_snapshot,'news'))
    def test_cache_bounded_and_latest_correction_wins(self):
        previous={'translation_cache':{'news':{str(i):'中文' for i in range(CACHE_LIMIT+10)}}}
        out=update_cache(previous,[{'title_en':'new','title_zh':'新標題'},{'title_en':str(CACHE_LIMIT+9),'title_zh':'修正標題'}],[])
        self.assertEqual(len(out['news']),CACHE_LIMIT)
        self.assertNotIn('0',out['news'])
        self.assertEqual(out['news'][str(CACHE_LIMIT+9)],'修正標題')

class GroqTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env=patch.dict('os.environ',{'GROQ_API_KEY':'test-only-not-a-real-key','GROQ_TRANSLATION_MODEL':''})
        self.env.start();self.addCleanup(self.env.stop)
    async def test_batch_id_mapping_dedup_and_original_preservation(self):
        items=[{'title':'First?'},{'title':'Second?'},{'title':'First?'}];s=Session()
        await translate_groq(s,items,{})
        self.assertEqual([i['title_zh'] for i in items],['中文標題 0','中文標題 1','中文標題 0'])
        self.assertEqual(items[0]['title_en'],'First?')
        self.assertEqual(len(s.calls),1)
        self.assertEqual(s.calls[0][0],'https://api.groq.com/openai/v1/chat/completions')
        self.assertEqual(s.calls[0][1]['json']['model'],'openai/gpt-oss-20b')
        self.assertTrue(s.calls[0][1]['json']['response_format']['json_schema']['strict'])
    async def test_missing_key_retains_cache_without_network(self):
        items=[{'title':'known'},{'title':'new'}];s=Session()
        with patch.dict('os.environ',{'GROQ_API_KEY':''}): await translate_groq(s,items,{'known':'已翻譯'})
        self.assertEqual(s.calls,[])
        self.assertEqual(items[0]['title_zh'],'已翻譯')
        self.assertEqual(items[1]['translation_error'],'groq_missing_key')
    async def test_rate_limit_stops_later_batches_and_other_source(self):
        s=Session(429);items=[{'title':f'headline {i}'} for i in range(25)]
        await translate_groq(s,items,{})
        await translate_groq(s,[{'title':'market?'}],{})
        self.assertEqual(len(s.calls),1)
        self.assertTrue(all(i['translation_error']=='groq_http_429' for i in items))
    async def test_invalid_ids_or_incomplete_results_never_apply(self):
        for rows in ([{'id':0,'text':'中文'}], [{'id':0,'text':'中文'},{'id':0,'text':'重複'}],
                     [{'id':0,'text':'English'},{'id':1,'text':'中文'}]):
            with self.subTest(rows=rows):
                items=[{'title':'one'},{'title':'two'}]
                await translate_groq(Session(rows=rows),items,{})
                self.assertTrue(all('title_zh' not in i for i in items))
                self.assertTrue(all(i['translation_error']=='groq_ValueError' for i in items))
    async def test_batches_are_bounded(self):
        s=Session(); await translate_groq(s,[{'title':f'headline {i}'} for i in range(21)],{})
        self.assertEqual(len(s.calls),3)
        self.assertEqual([len(json.loads(c[1]['json']['messages'][1]['content'])) for c in s.calls],[10,10,1])

    async def test_non_object_completion_does_not_apply(self):
        class ArrayResponse(Response):
            async def json(self, **kwargs):
                return {'choices':[{'finish_reason':'stop', 'message':{'content':'["錯誤格式"]'}}]}
        class ArraySession(Session):
            def post(self, url, **kwargs): return ArrayResponse(200, [])
        items=[{'title':'one'}]
        await translate_groq(ArraySession(), items, {})
        self.assertNotIn('title_zh', items[0])
        self.assertEqual(items[0]['translation_error'], 'groq_ValueError')
