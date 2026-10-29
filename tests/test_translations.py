import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from translations import cached_titles, update_cache, translate_groq, english_titles, CACHE_LIMIT

class Response:
    def __init__(self, status, rows): self.status, self.rows = status, rows
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def json(self, **kwargs):
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'translations':self.rows})}}]}
    async def text(self): return '{"error":{"code":"json_validate_failed"}}'

class Session:
    def __init__(self, status=200, rows=None): self.status, self.rows, self.calls = status, rows, []
    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        inputs=json.loads(kwargs['json']['messages'][1]['content'])
        rows=self.rows if self.rows is not None else [{'id':r['id'],'text':f"中文標題 {r['id']}"} for r in reversed(inputs)]
        return Response(self.status,rows)

class RejectsOne(Session):
    """Groq-style 400 for any batch that contains the poisoned title."""
    def post(self, url, **kwargs):
        inputs=json.loads(kwargs['json']['messages'][1]['content'])
        if any('poison' in r['text'] for r in inputs):
            self.calls.append((url, kwargs)); return Response(400, [])
        return super().post(url, **kwargs)

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
    async def test_english_display_preserves_chinese_original_and_observation_time(self):
        rows=[{'title':'共機5架次', 'title_zh':'共機5架次', 'ts':'2026-09-14T00:00:00Z'},
              {'title':'中文新聞', 'title_en':'Original English title', 'ts':'unchanged'}]
        s=Session(rows=[{'id':0,'text':'5 PLA aircraft sorties'}])
        cache=await english_titles(s, rows, {})
        self.assertEqual(rows[0]['title'],'共機5架次')
        self.assertEqual(rows[0]['title_zh'],'共機5架次')
        self.assertEqual(rows[0]['ts'],'2026-09-14T00:00:00Z')
        self.assertEqual(rows[0]['title_english'],'5 PLA aircraft sorties')
        self.assertEqual(rows[1]['title_english'],'Original English title')
        self.assertEqual(len(s.calls),1)
        retry=Session();copies=[{'title':'共機5架次'}]
        await english_titles(retry,copies,{'english_translation_cache':cache})
        self.assertEqual(retry.calls,[])
        self.assertEqual(copies[0]['title_english'],'5 PLA aircraft sorties')

    async def test_chinese_output_is_not_an_english_translation(self):
        rows=[{'title':'原始中文'}]
        await english_titles(Session(rows=[{'id':0,'text':'仍是中文'}]),rows,{})
        self.assertNotIn('title_english',rows[0])
        self.assertEqual(rows[0]['english_translation_status'],'unavailable')
    async def test_batch_id_mapping_dedup_and_original_preservation(self):
        items=[{'title':'First?'},{'title':'Second?'},{'title':'First?'}];s=Session()
        await translate_groq(s,items,{})
        self.assertEqual([i['title_zh'] for i in items],['中文標題 0','中文標題 1','中文標題 0'])
        self.assertEqual(items[0]['title_en'],'First?')
        self.assertEqual(len(s.calls),1)
        self.assertEqual(s.calls[0][0],'https://api.groq.com/openai/v1/chat/completions')
        self.assertEqual(s.calls[0][1]['json']['model'],'openai/gpt-oss-20b')
        self.assertTrue(s.calls[0][1]['json']['response_format']['json_schema']['strict'])
    async def test_translation_adding_a_country_is_rejected_alone(self):
        items=[{'title':'Pakistan imports wheat as food costs, US-Iran war fuel inflation'},{'title':'US warns Gulf states'}]
        s=Session(rows=[{'id':0,'text':'巴基斯坦進口小麥因食品成本、俄美伊戰爭燃料通膨'},{'id':1,'text':'美國警告海灣國家'}])
        await translate_groq(s,items,{})
        self.assertNotIn('title_zh',items[0])                       # wrong title stays untranslated, retried next run
        self.assertEqual(items[0]['translation_error'],'entity_mismatch')
        self.assertEqual(items[1]['title_zh'],'美國警告海灣國家')       # the rest of the batch still applies
        self.assertIn('never 俄',s.calls[0][1]['json']['messages'][0]['content'])
    async def test_cached_translation_adding_a_country_is_retranslated(self):
        items=[{'title':'US-Iran war fuel inflation'}];s=Session(rows=[{'id':0,'text':'美伊戰爭推升燃料通膨'}])
        await translate_groq(s,items,{'US-Iran war fuel inflation':'俄美伊戰爭燃料通膨'})
        self.assertEqual(len(s.calls),1)
        self.assertEqual(items[0]['title_zh'],'美伊戰爭推升燃料通膨')
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
    async def test_http_400_batch_is_retried_singly_and_only_the_bad_title_stays_untranslated(self):
        s=RejectsOne();items=[{'title':'headline one'},{'title':'poison title'},{'title':'headline two'}]
        await translate_groq(s,items,{})
        self.assertEqual([i.get('translation_status') for i in items],['translated','unavailable','translated'])
        self.assertEqual(items[1]['translation_error'],'groq_http_400')
        self.assertEqual(len(s.calls),4)                     # whole batch, then three single tries
        await translate_groq(s,[{'title':'market?'}],{})    # a 400 does not stop later sources
        self.assertEqual(len(s.calls),5)

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


class EntityCheckTests(unittest.TestCase):
    def test_only_added_countries_are_flagged(self):
        from translation_check import added_entities as a
        self.assertEqual(a('US-Iran war fuel inflation', '俄美伊戰爭燃料通膨'), ['(?<!塞)俄'])
        for en, zh in [('Russo-Ukrainian war, day 1702', '俄烏戰爭第1702天'), ('Eritrea invades Ethiopia by October 31?', '厄立特里亞於10月31日前入侵埃塞俄比亞？'),
                       ('Chinese ships near PH shoal — PCG', '中國船隻在菲律賓海域'), ('Kremlin warns Kyiv', '俄羅斯警告烏克蘭'), ('Putin meets Xi', '普丁會見習近平')]:
            self.assertEqual(a(en, zh), [], en)
        self.assertEqual(a(None, '俄'), [])
