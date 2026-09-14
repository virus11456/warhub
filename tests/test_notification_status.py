import copy
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import alerts
import notification_status as status


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 14, 15, tzinfo=timezone.utc)
        self.data = {'updated_at': (self.now - timedelta(minutes=20)).isoformat()}

    def test_distinct_snapshot_reasons_and_boundary(self):
        for data, expected in [(None, 'invalid_snapshot'), ({}, 'invalid_observation_time'),
                ({'updated_at': '2026-09-14T15:00:00'}, 'invalid_observation_time'),
                ({'updated_at': (self.now + timedelta(seconds=1)).isoformat()}, 'future_observation'),
                ({'updated_at': (self.now - timedelta(minutes=110)).isoformat()}, 'stale_snapshot'),
                ({**self.data, '_notify': 'broken'}, 'invalid_receipts'),
                (self.data, 'ready'),
                ({**self.data, '_notify': {'digest_snapshot_at': self.data['updated_at']}}, 'already_delivered')]:
            self.assertEqual(status.snapshot_reason(data, self.now), expected)

    def test_legacy_success_requires_nonempty_all_true_receipts(self):
        for receipts, expected in [({}, None), ({'a': False}, None), ({'a': True, 'b': False}, None),
                                    ({'a': 1}, None), ({'a': True}, self.now.isoformat())]:
            self.assertEqual(status.last_success({'delivery': {'checked_at': self.now.isoformat(),
                'digest': receipts}}, self.now), expected)
        self.assertIsNone(status.last_success({'digest_success_at': (self.now + timedelta(hours=1)).isoformat()}, self.now))

    def test_report_redacts_targets_preserves_input_and_distinguishes_limits(self):
        self.data['_notify'] = {'telegram_retry_at': self.now.timestamp() + 30,
            'delivery': {'checked_at': self.now.isoformat(), 'digest': {'secret-target': True, 'private-target': False}}}
        original = copy.deepcopy(self.data)
        text = status.report(self.data, self.now, quiet=True)
        self.assertIn('部分成功', text)
        self.assertIn('尚餘約 30 秒', text)
        self.assertIn('成功時間：未知', text)
        self.assertIn('安靜模式：啟用', text)
        self.assertNotIn('secret-target', text)
        self.assertNotIn('private-target', text)
        self.assertEqual(self.data, original)

    def test_missing_or_empty_results_do_not_claim_success(self):
        for value in (None, {}, {'_notify': {'delivery': {'digest': {}}}}):
            self.assertIn('沒有發送結果；不能視為成功', status.report(value, self.now))

    def test_cli_missing_snapshot_still_writes_diagnostic_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / 'summary'
            result = subprocess.run([sys.executable, str(Path(status.__file__)), '--data', directory + '/missing'],
                env={**os.environ, 'GITHUB_STEP_SUMMARY': str(summary)}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn('快照格式無效', summary.read_text())


class SuccessRetentionTests(unittest.IsolatedAsyncioTestCase):
    async def test_failure_and_no_send_retain_success_without_fabricating_new_time(self):
        now = datetime.now(timezone.utc)
        before = (now - timedelta(hours=2)).isoformat()
        data = {'updated_at': now.isoformat()}
        previous = {'delivery': {'checked_at': before, 'digest': {'old': True}}}
        with patch.object(alerts, '_send_all', AsyncMock(return_value={'failed': False})):
            failed = await alerts.run_notifications(data, previous, digest_only=True)
        self.assertEqual(failed['digest_success_at'], before)
        failed['bucket'] = int(now.timestamp() // 3600) // alerts.DIGEST_EVERY_HOURS
        with patch.object(alerts, '_send_all', AsyncMock(return_value={})):
            skipped = await alerts.run_notifications(data, failed, digest_only=True)
        self.assertEqual(skipped['digest_success_at'], before)

    async def test_success_records_send_time_separately_from_observation(self):
        observed = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        with patch.object(alerts, '_send_all', AsyncMock(return_value={'target': True})):
            result = await alerts.run_notifications({'updated_at': observed}, {}, digest_only=True)
        self.assertEqual(result['digest_snapshot_at'], observed)
        self.assertGreater(status.timestamp(result['digest_success_at']), status.timestamp(observed))
