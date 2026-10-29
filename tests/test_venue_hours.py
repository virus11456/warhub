import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fetch_data as collector
import venue_hours as vh


class ParseTests(unittest.TestCase):
    def test_ranges(self):
        self.assertEqual(vh.parse_range('10:30 AM–9:30 PM'), [[630, 1290]])
        self.assertEqual(vh.parse_range('11 AM–2 AM'), [[660, 1560]])            # past midnight
        self.assertEqual(vh.parse_range('11 AM–2 PM, 5–10 PM'), [[660, 840], [1020, 1320]])
        self.assertEqual(vh.parse_range('12 PM–12 AM'), [[720, 1440]])
        self.assertEqual(vh.parse_range('Closed'), [])                          # a real closed day, not missing
        self.assertEqual(vh.parse_range('Open 24 hours'), [[0, 1440]])
        self.assertIsNone(vh.parse_range('Hours might differ'))
        self.assertIsNone(vh.parse_range(''))

    def test_week_needs_all_days_and_accepts_both_shapes(self):
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        week = vh.parse_hours([{d: '11 AM–10 PM'} for d in days])
        self.assertEqual(sorted(week), list('0123456'))
        self.assertEqual(vh.parse_hours({d: '11 AM–10 PM' for d in days}), week)
        self.assertIsNone(vh.parse_hours([{d: '11 AM–10 PM'} for d in days[:6]]))

    def test_branch_match(self):
        self.assertTrue(vh.same_branch('2100 Crystal Dr, Arlington', '2110 Crystal Dr, Arlington, VA'))
        self.assertTrue(vh.same_branch('1301 S Joyce St', '1301 S Joyce St, Arlington'))
        self.assertFalse(vh.same_branch('2602 Columbia Pike', '3400 Columbia Pike'))
        self.assertFalse(vh.same_branch('2602 Columbia Pike', '2602 Wilson Blvd'))


class LookupTests(unittest.TestCase):
    def fake(self, payload):
        class R:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def read(s): return json.dumps(payload).encode()
        return patch.object(vh.urllib.request, 'urlopen', lambda *a, **k: R())

    def test_picks_matching_branch_and_flags_permanent_closure(self):
        venue = {'name': 'X', 'kind': 'pizza', 'query': 'X', 'address': '1014 S Glebe Rd, Arlington'}
        local = [{'title': 'X', 'address': '5860 Columbia Pike', 'operating_hours': {}},
                 {'title': 'X', 'address': '1014 S Glebe Rd Ste A', 'place_id': 'p',
                  'operating_hours': {d: 'Closed' for d in vh.DAYS}}]
        with self.fake({'local_results': local}):
            got = vh.lookup('k', venue)
        self.assertEqual((got['place_id'], got['hours']['3']), ('p', []))
        with self.fake({'place_results': {'address': '1014 S Glebe Rd', 'open_state': 'Permanently closed'}}):
            self.assertTrue(vh.lookup('k', venue)['permanently_closed'])
        with self.fake({'local_results': local[:1]}):
            self.assertIn('different branch', vh.lookup('k', venue)['error'])


class SnapshotTests(unittest.TestCase):
    def test_data_json_gets_hours_without_raw_text(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'h.json'
            path.write_text(json.dumps({'fetched_at': 't', 'venues': {'A': {'kind': 'bar', 'hours': {'0': []}, 'raw': {'x': 1}},
                                                                     'B': {'kind': 'bar'}}}))
            with patch.object(vh, 'HOURS_FILE', path):
                out = collector.stored_venue_hours()
            self.assertEqual(out['venues'], {'A': {'kind': 'bar', 'hours': {'0': []}}})
            path.write_text('{}')
            with patch.object(vh, 'HOURS_FILE', path):
                self.assertIsNone(collector.stored_venue_hours())


if __name__ == '__main__':
    unittest.main()
