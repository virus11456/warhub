import sys, unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fetch_data
from data_quality import source_health

class Integration(unittest.IsolatedAsyncioTestCase):
    async def test_cache_is_separate_and_quote_time_survives_translation(self):
        old = {'markets':[{'question':'exact option','question_zh':'既有翻譯'}]}
        current = {'status':'available','reused':False,'fetched_at':'2026-09-22T00:00:00Z','markets':[{'question':'exact option','display_midpoint':0}]}
        with patch('kalshi_client.refresh',AsyncMock(return_value=current)) as collect, patch.object(fetch_data,'_translate_market_questions',AsyncMock()) as translate:
            result = await fetch_data.fetch_kalshi(object(),old)
        self.assertTrue(collect.call_args.kwargs['include_background'])
        self.assertEqual(translate.call_args.kwargs['cached'],{'exact option':'既有翻譯'})
        self.assertEqual(result['fetched_at'],'2026-09-22T00:00:00Z')
        self.assertEqual(result['markets'][0]['display_midpoint'],0)
    async def test_reused_quotes_do_not_trigger_translation(self):
        current = {'status':'stale','reused':True,'markets':[{'question':'old'}]}
        with patch('kalshi_client.refresh',AsyncMock(return_value=current)), patch.object(fetch_data,'_translate_market_questions',AsyncMock()) as translate:
            result = await fetch_data.fetch_kalshi(object(),{})
        translate.assert_not_called();self.assertEqual(result,current)
    def test_health_empty_success_partial_and_failure_are_distinct(self):
        for status in ('available','partial','stale','unavailable'):
            r=source_health({'kalshi':{'status':status,'markets':[],'fetched_at':'2026-09-22T00:00:00Z'}})['kalshi']
            self.assertEqual(r['status'],status);self.assertIsNone(r['observed_at'])
