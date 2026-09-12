import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from test_source_budgets import Session
import fetch_data as f


class NotamBackoff(unittest.IsolatedAsyncioTestCase):
    async def test_denied_empty_source_persists_and_skips_next_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'data.json'
            path.write_text('{}')
            with patch.object(f, 'DATA_FILE', path), patch.object(f, 'REGION_FIRS', {'a':['AAAA']}):
                first = Session(status=403)
                rows = await f.fetch_notams(first)
                self.assertEqual(first.calls, 1)
                self.assertTrue(rows['a']['stale'])
                self.assertNotIn('danger', rows['a'])
                self.assertNotIn('observed_at', rows['a'])
                self.assertGreater(datetime.fromisoformat(rows['a']['cooldown_until']), datetime.now(timezone.utc))
                path.write_text(json.dumps({'notams': rows}))
                second = Session()
                self.assertEqual(await f.fetch_notams(second), rows)
                self.assertEqual(second.calls, 0)

    async def test_expired_backoff_recovers_valid_zero_without_old_metadata(self):
        old = {'stale': True, 'danger': 3, 'observed_at': '2000-01-01T00:00:00+00:00',
               'cooldown_until': (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'data.json'
            path.write_text(json.dumps({'notams': {'a': old}}))
            with patch.object(f, 'DATA_FILE', path), patch.object(f, 'REGION_FIRS', {'a':['AAAA']}):
                session = Session()
                result = (await f.fetch_notams(session))['a']
                self.assertEqual(session.calls, 1)
                self.assertEqual(result['danger'], 0)
                self.assertFalse(result.get('stale'))
                self.assertNotIn('cooldown_until', result)
                self.assertNotEqual(result['observed_at'], old['observed_at'])
