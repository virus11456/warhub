import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from collection_guard import should_collect, MIN_INTERVAL_SECONDS


class CollectionGuardTests(unittest.TestCase):
    def test_spacing_boundary(self):
        now = datetime(2026, 9, 11, 12, tzinfo=timezone.utc)
        for age, expected in [(0,False),(60,False),(MIN_INTERVAL_SECONDS-1,False),
                              (MIN_INTERVAL_SECONDS,True),(7200,True)]:
            with self.subTest(age=age):
                snapshot = {'updated_at': (now-timedelta(seconds=age)).isoformat()}
                self.assertEqual(should_collect(snapshot, now)[0], expected)
                self.assertTrue(should_collect(snapshot, now, force=True)[0])

    def test_bad_or_future_timestamp_does_not_block_recovery(self):
        now = datetime(2026, 9, 11, 12, tzinfo=timezone.utc)
        for snapshot in [None,[],{}, {'updated_at':None}, {'updated_at':'bad'},
                         {'updated_at':'2026-09-11T12:00:00'},
                         {'updated_at':'2099-09-11T12:00:00Z'}]:
            with self.subTest(snapshot=snapshot):
                self.assertTrue(should_collect(snapshot, now)[0])


    def test_hourly_checks_do_not_collect_hourly(self):
        start = datetime(2026, 9, 12, 0, 23, tzinfo=timezone.utc)
        snapshot = {}
        collected = []
        for minute in range(0, 24 * 60, 60):
            now = start + timedelta(minutes=minute)
            if should_collect(snapshot, now)[0]:
                collected.append(minute)
                # A three-minute collector records its completion time.
                snapshot = {'updated_at': (now + timedelta(minutes=3)).isoformat()}
        self.assertEqual(collected, list(range(0, 24 * 60, 120)))

    def test_missed_check_recovers_without_bunched_collections(self):
        start = datetime(2026, 9, 12, 0, 23, tzinfo=timezone.utc)
        snapshot = {'updated_at': (start + timedelta(minutes=3)).isoformat()}
        collected = []
        # The due check at 120 is missing; 181 is a delayed duplicate.
        for minute in [60, 180, 181, 240, 300]:
            now = start + timedelta(minutes=minute)
            if should_collect(snapshot, now)[0]:
                collected.append(minute)
                snapshot = {'updated_at': now.isoformat()}
        self.assertEqual(collected, [180, 300])

    def test_digest_only_never_collects_even_with_force_and_stale_data(self):
        from collection_guard import workflow_plan
        now = datetime(2026, 9, 14, tzinfo=timezone.utc)
        for snapshot in ({}, {'updated_at': '2026-09-01T00:00:00Z'}):
            for force in (False, True):
                self.assertEqual(workflow_plan(snapshot, now, 'workflow_dispatch',
                    notify_only=True, force=force), (False, 'explicit_digest_only', True))
                self.assertEqual(workflow_plan(snapshot, now, 'workflow_dispatch',
                    notify_only=True, quiet=True, force=force), (False, 'explicit_digest_only', False))

    def test_manual_digest_flag_is_not_implicit_or_accepted_on_push(self):
        from collection_guard import workflow_plan
        now = datetime(2026, 9, 14, tzinfo=timezone.utc)
        snapshot = {'updated_at': now.isoformat()}
        self.assertFalse(workflow_plan(snapshot, now, 'workflow_dispatch')[2])
        self.assertFalse(workflow_plan(snapshot, now, 'push', notify_only=True)[2])
        self.assertTrue(workflow_plan(snapshot, now, 'schedule')[2])
