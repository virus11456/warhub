import copy
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import alerts
import notify_snapshot as ns


class SnapshotNotificationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 14, 3, tzinfo=timezone.utc)
        self.observed = self.now - timedelta(minutes=40)
        self.data = {'updated_at': self.observed.isoformat(), 'score': {'experimental': True},
                     'finance': {'value': 0, 'missing': None}, 'news': [],
                     '_notify': {'hotspots': 10, 'hotspot_counter_version': 2}}

    async def test_schedule_can_notify_quiet_update_without_mutating_observations(self):
        original = copy.deepcopy(self.data)
        sender = AsyncMock(return_value={'digest_snapshot_at': self.data['updated_at']})
        with patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'schedule', 'WARHUB_NO_NOTIFY': '0'}), \
             patch.object(ns, 'run_notifications', sender):
            pending = await ns.prepare(self.data, self.now)
        self.assertEqual(self.data, original)
        self.assertTrue(sender.call_args.kwargs['digest_only'])
        updated = ns.apply(self.data, pending)
        self.assertEqual(updated['finance'], {'value': 0, 'missing': None})
        self.assertEqual(updated['updated_at'], original['updated_at'])
        self.assertEqual(ns.fingerprint(updated), ns.fingerprint(original))
        self.assertFalse(ns.eligible(updated, self.now + timedelta(minutes=10)))

    async def test_quiet_and_manual_runs_never_send_saved_snapshot(self):
        sender = AsyncMock()
        for event, quiet in [('schedule', '1'), ('workflow_dispatch', '0'), ('push', '0')]:
            with patch.dict(os.environ, {'GITHUB_EVENT_NAME': event, 'WARHUB_NO_NOTIFY': quiet}), \
                 patch.object(ns, 'run_notifications', sender):
                self.assertIsNone(await ns.prepare(self.data, self.now))
        sender.assert_not_awaited()

    async def test_missing_stale_future_and_already_delivered_are_not_sent(self):
        cases = [None, {}, [], {**self.data, 'updated_at': 'bad'},
                 {**self.data, 'updated_at': '2026-09-14T03:00:00'},
                 {**self.data, 'updated_at': (self.now + timedelta(seconds=1)).isoformat()},
                 {**self.data, 'updated_at': (self.now - timedelta(minutes=110)).isoformat()},
                 {**self.data, '_notify': {'digest_snapshot_at': self.data['updated_at']}}]
        with patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'schedule', 'WARHUB_NO_NOTIFY': '0'}), \
             patch.object(ns, 'run_notifications', AsyncMock()) as sender:
            for snapshot in cases:
                self.assertIsNone(await ns.prepare(snapshot, self.now))
        sender.assert_not_awaited()

    def test_legacy_receipts_skip_old_snapshot_but_allow_newer_quiet_update(self):
        previous = {'delivery': {'checked_at': self.now.isoformat(), 'digest': {'hashed': True}}}
        self.assertFalse(ns.eligible({**self.data, '_notify': previous}, self.now))
        previous['delivery']['checked_at'] = (self.observed - timedelta(hours=2)).isoformat()
        self.assertTrue(ns.eligible({**self.data, '_notify': previous}, self.now))
        previous['delivery']['digest']['failed'] = False
        previous['delivery']['checked_at'] = self.now.isoformat()
        self.assertTrue(ns.eligible({**self.data, '_notify': previous}, self.now))

    def test_publication_is_idempotent_and_rejects_changed_data_or_receipts(self):
        pending = {'snapshot_hash': ns.fingerprint(self.data),
                   'previous_notify': self.data['_notify'], 'notify': {'telegram_retry_at': 123}}
        updated = ns.apply(self.data, pending)
        self.assertEqual(ns.apply(updated, pending), updated)
        for changed in [{**self.data, 'news': [{'title': 'new'}]},
                        {**self.data, '_notify': {'newer': True}},
                        {**self.data, 'updated_at': self.now.isoformat()}]:
            with self.assertRaises(ValueError):
                ns.apply(changed, pending)

    async def test_digest_only_keeps_event_edges_and_records_successful_snapshot(self):
        data = {**self.data, 'score': {'experimental': False, 'alert_level': 'CRITICAL'},
                'firms': {'conflict_total': 1000},
                'pizza': [{'spike_magnitude': 'EXTREME', 'percentage_of_usual': 999}]}
        previous = {'level': 'LOW', 'pizza_extreme': False, 'hotspots': 10,
                    'hotspot_counter_version': 2}
        with patch.object(alerts, '_send_all', AsyncMock(return_value={'hashed': True})) as sender:
            result = await alerts.run_notifications(data, previous, 'LOW', digest_only=True)
        self.assertEqual(sender.call_args_list[0].args[0], [])
        self.assertEqual(len(sender.call_args_list[1].args[0]), 1)
        self.assertIn(self.data['updated_at'], sender.call_args_list[1].args[0][0])
        for key in previous:
            self.assertEqual(result[key], previous[key])
        self.assertEqual(result['digest_snapshot_at'], data['updated_at'])

    async def test_failed_digest_does_not_mark_snapshot_delivered(self):
        with patch.object(alerts, '_send_all', AsyncMock(return_value={'failed': False})):
            result = await alerts.run_notifications(self.data, {}, digest_only=True)
        self.assertIsNone(result['digest_snapshot_at'])
        self.assertIsNone(result['bucket'])


class ReceiptPublicationTests(unittest.TestCase):
    def submission(self, reject_apply=False):
        import subprocess
        import tempfile
        import textwrap
        root = Path(__file__).resolve().parents[1]
        workflow = (root / '.github/workflows/update-data.yml').read_text()
        section = workflow.split('      - name: Commit notification receipts only\n', 1)[1]
        script = textwrap.dedent(section.split('        run: |\n', 1)[1].split('\n      - name:', 1)[0])
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            script = script.replace('/tmp/warhub-notify-state.json', str(directory / 'state.json'))
            (directory / 'state.json').write_text('{}')
            bindir = directory / 'bin'
            bindir.mkdir()
            for command in ('git', 'python', 'sleep'):
                body = '#!/bin/sh\nprintf "%s\\n" "' + command + ' $*" >> "$COMMAND_LOG"\n'
                if command == 'python' and reject_apply:
                    body += 'exit 42\n'
                if command == 'git':
                    body += 'if [ "$1" = diff ]; then exit 1; fi\n'
                    body += 'if [ "$1" = push ] && [ ! -f "$FIRST_PUSH" ]; then touch "$FIRST_PUSH"; exit 1; fi\n'
                path = bindir / command
                path.write_text(body + 'exit 0\n')
                path.chmod(0o755)
            log = directory / 'log'
            env = {**os.environ, 'PATH': str(bindir) + os.pathsep + os.environ['PATH'],
                   'COMMAND_LOG': str(log), 'FIRST_PUSH': str(directory / 'first-push')}
            result = subprocess.run(['/bin/bash', '-e', '-o', 'pipefail', '-c', script],
                                    cwd=directory, env=env, capture_output=True, text=True)
            return result.returncode, log.read_text().splitlines()

    def test_retry_publishes_only_receipts_without_resending_or_collecting(self):
        code, commands = self.submission()
        self.assertEqual(code, 0)
        self.assertEqual(sum(command.startswith('git push ') for command in commands), 2)
        self.assertEqual([c for c in commands if c.startswith('git add ')],
                         ['git add data/data.json'] * 2)
        self.assertEqual(sum('notify_snapshot.py apply ' in c for c in commands), 2)
        self.assertFalse(any('prepare' in c or 'fetch_data.py' in c for c in commands))

    def test_changed_snapshot_guard_stops_before_commit_or_push(self):
        code, commands = self.submission(reject_apply=True)
        self.assertEqual(code, 42)
        self.assertFalse(any(c.startswith(('git add ', 'git commit ', 'git push ')) for c in commands))
