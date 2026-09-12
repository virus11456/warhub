import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from backup_scheduler import check, WORKFLOW

NOW = datetime(2026, 9, 12, 16, tzinfo=timezone.utc)


class Client:
    def __init__(self, age=131, busy=None, fail=False, enabled=True):
        self.age, self.busy, self.fail, self.enabled = age, busy, fail, enabled
        self.calls = []

    def request(self, path, payload=None, raw=False):
        self.calls.append((path, payload))
        if path.startswith('/contents/'):
            return {'updated_at': (NOW - timedelta(minutes=self.age)).isoformat()}
        if path == WORKFLOW:
            return {'state': 'active' if self.enabled else 'disabled_manually'}
        if payload is not None:
            if self.fail:
                raise TimeoutError('ambiguous response')
            return {'workflow_run_id': 123}
        return {'total_count': int(path.endswith('status=' + str(self.busy)))}


class BackupSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / 'state.json'

    def test_recent_snapshot_avoids_even_run_queries(self):
        for age in (0, 110, 129.99):
            client = Client(age=age)
            self.assertEqual(check(client, self.state, NOW, True), 'fresh')
            self.assertEqual(len(client.calls), 1)

    def test_disabled_or_active_run_never_dispatches(self):
        for status in ('queued', 'in_progress', 'waiting', 'pending', 'requested'):
            client = Client(busy=status)
            self.assertEqual(check(client, self.state, NOW, True), 'workflow_busy')
            self.assertFalse(any(payload for _, payload in client.calls))
        self.assertEqual(check(Client(enabled=False), self.state, NOW, True), 'workflow_disabled')

    def test_dry_run_does_not_write_or_send(self):
        client = Client(age=130)
        self.assertEqual(check(client, self.state, NOW), 'would_dispatch')
        self.assertFalse(self.state.exists())
        self.assertFalse(any(payload for _, payload in client.calls))

    def test_dispatch_quiet_auto_and_restart_cooldown(self):
        client = Client()
        self.assertEqual(check(client, self.state, NOW, True), 'dispatch_accepted')
        self.assertEqual(client.calls[-1][1], {'ref': 'main', 'inputs': {
            'collection_mode': 'auto', 'force_refresh': 'false', 'test_push': 'false', 'quiet': 'true'}})
        next_client = Client()
        self.assertEqual(check(next_client, self.state, NOW + timedelta(minutes=119), True), 'cooldown')
        self.assertEqual(next_client.calls, [])
        self.assertEqual(json.loads(self.state.read_text())['outcome'], 'accepted')

    def test_ambiguous_failure_persists_cooldown_before_retry(self):
        with self.assertRaises(TimeoutError):
            check(Client(fail=True), self.state, NOW, True)
        self.assertEqual(json.loads(self.state.read_text())['outcome'], 'unknown_or_failed')
        client = Client()
        self.assertEqual(check(client, self.state, NOW + timedelta(minutes=30), True), 'cooldown')
        self.assertEqual(client.calls, [])

    def test_corrupt_or_future_state_and_snapshot_fail_closed(self):
        self.state.write_text('{bad json')
        with self.assertRaises(ValueError):
            check(Client(), self.state, NOW, True)
        self.state.write_text(json.dumps({'attempted_at': (NOW + timedelta(hours=1)).isoformat()}))
        with self.assertRaises(ValueError):
            check(Client(), self.state, NOW, True)
        self.state.unlink()
        with self.assertRaises(ValueError):
            check(Client(age=-1), self.state, NOW, True)

    def test_cooldown_expires_without_forcing_collection(self):
        self.state.write_text(json.dumps({'attempted_at': (NOW - timedelta(minutes=120)).isoformat()}))
        self.assertEqual(check(Client(age=2), self.state, NOW, True), 'fresh')
