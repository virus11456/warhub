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
