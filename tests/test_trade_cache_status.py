import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fetch_data as fd
from data_quality import source_health


class TradeCacheStatus(unittest.IsolatedAsyncioTestCase):
    async def test_cached_collectors_keep_source_time_and_partial_zero(self):
        stamp = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
        original = {'schema_version': 2, 'updated_at': stamp, 'ref_month': '2026-07',
                    'items': [{'wan_ton': 0, 'incomplete': True}]}

        class NoNetwork:
            def get(self, *args, **kwargs):
                raise AssertionError('cache reuse must not query the source')

        for key, collector in [('food', fd.fetch_food_imports), ('strat', fd.fetch_strategic_imports)]:
            with self.subTest(source=key), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'data.json'
                path.write_text(json.dumps({key: original}))
                with patch.object(fd, 'DATA_FILE', path):
                    result = await collector(NoNetwork())
                self.assertEqual(result['updated_at'], stamp)
                self.assertEqual(result['items'], original['items'])
                self.assertEqual(result['ref_month'], original['ref_month'])
                self.assertGreater(result['cache_reused_at'], stamp)
                health = source_health({key: result, 'collection': {'slow_refresh': True}})[key]
                self.assertEqual(health['status'], 'partial')
                self.assertEqual(health['observed_at'], stamp)
                self.assertIn('未重新查詢', health['note'])
                self.assertNotIn('cache_reused_at', json.loads(path.read_text())[key])

    def test_new_query_is_not_labelled_cache_reuse(self):
        result = {'updated_at': '2026-09-12T18:00:00+00:00', 'items': [{'wan_ton': 0}]}
        health = source_health({'food': result})['food']
        self.assertEqual(health['status'], 'available')
        self.assertNotIn('快取', health['note'])
