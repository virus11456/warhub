import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import refresh_translations as refresh

class RefreshTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_translations_change_without_collection_or_notifications(self):
        original={'updated_at':'2026-09-12T00:23:29Z','score':{'combined_score':30},
            'news':[{'title':'English title','url':'https://example.com','ts':'2026-09-11'}],
            'polymarket':[{'question':'Question?','yes_price':.2,'risk_score':20}],
            '_notify':{'last_digest_at':'unchanged'}}
        async def news(session, rows): rows[0].update(title='中文標題',title_en='English title',title_zh='中文標題')
        async def markets(session, rows): rows[0]['question_zh']='中文問題？'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'data.json';p.write_text(json.dumps(original))
            with patch.dict('os.environ',{'GROQ_API_KEY':'test-only'}), \
                 patch.object(refresh.collector,'_translate_titles',news), \
                 patch.object(refresh.collector,'_translate_market_questions',markets), \
                 patch.object(refresh.collector,'main',new_callable=AsyncMock) as main:
                await refresh.refresh_file(object(),p)
                main.assert_not_called()
            result=json.loads(p.read_text())
        for field in ('updated_at','score','_notify'): self.assertEqual(result[field],original[field])
        self.assertEqual(result['polymarket'][0]['yes_price'],.2)
        self.assertEqual(result['polymarket'][0]['question'],'Question?')
        self.assertEqual(result['news'][0]['ts'],'2026-09-11')
        self.assertEqual(result['translation_cache']['news']['English title'],'中文標題')
    async def test_failure_does_not_write_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'data.json';before='{"news":[{"title":"English"}],"polymarket":[]}'
            p.write_text(before)
            with patch.dict('os.environ',{'GROQ_API_KEY':'test-only'}), \
                 patch.object(refresh.collector,'_translate_titles',new_callable=AsyncMock), \
                 patch.object(refresh.collector,'_translate_market_questions',new_callable=AsyncMock):
                with self.assertRaises(ValueError): await refresh.refresh_file(object(),p)
            self.assertEqual(p.read_text(),before)
