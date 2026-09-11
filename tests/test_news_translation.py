import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import fetch_data

class Response:
    def __init__(self,status=200): self.status=status
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
    async def json(self,**kwargs): return [[['繁體中文標題','original']]]
class Session:
    def __init__(self,status=200): self.calls=[];self.status=status
    def get(self,url,**kwargs): self.calls.append(kwargs);return Response(self.status)
class NewsTranslation(unittest.IsolatedAsyncioTestCase):
    async def test_separate_titles_and_reuse_persisted_translation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'data.json';p.write_text(json.dumps({'news':[{'title_en':'old','title_zh':'已翻譯標題'}]}))
            items=[{'title':'old'},{'title':'new\nheadline'}];session=Session()
            with patch.object(fetch_data,'DATA_FILE',p): await fetch_data._translate_titles(session,items)
        self.assertEqual(items[0]['title'],'已翻譯標題')
        self.assertEqual(items[1]['title_zh'],'繁體中文標題')
        self.assertEqual(items[1]['title_en'],'new\nheadline')
        self.assertEqual(len(session.calls),1)
        self.assertEqual(session.calls[0]['params']['q'],'new\nheadline')
    async def test_rejection_keeps_original_without_claiming_translation(self):
        with tempfile.TemporaryDirectory() as tmp:
            items=[{'title':'English headline'}];session=Session(429)
            with patch.object(fetch_data,'DATA_FILE',Path(tmp)/'absent.json'):
                await fetch_data._translate_titles(session,items)
        self.assertEqual(items[0]['title_en'],'English headline')
        self.assertEqual(items[0]['translation_status'],'unavailable')
        self.assertNotIn('title_zh',items[0])
        self.assertEqual(len(session.calls),1)

    async def test_market_translation_preserves_original_and_numeric_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            items=[{'question':'US strike on Cuba by December 31?', 'yes_price':.14, 'risk_score':14}]
            with patch.object(fetch_data,'DATA_FILE',Path(tmp)/'absent.json'):
                await fetch_data._translate_market_questions(Session(),items)
        self.assertEqual(items[0]['question'],'US strike on Cuba by December 31?')
        self.assertEqual(items[0]['question_zh'],'繁體中文標題')
        self.assertEqual(items[0]['yes_price'],.14)
        self.assertEqual(items[0]['risk_score'],14)

    async def test_market_deadline_does_not_become_exact_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'data.json'
            q='US strike on Cuba by December 31?'
            p.write_text(json.dumps({'polymarket':[{'question':q,'question_zh':'美國12月31日攻擊古巴？'}]}))
            items=[{'question':q}]
            with patch.object(fetch_data,'DATA_FILE',p):
                await fetch_data._translate_market_questions(Session(),items)
        self.assertEqual(items[0]['question_zh'],'美國12月31日前攻擊古巴？')
