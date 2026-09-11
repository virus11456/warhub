import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from pla_counts import sortie_count, usable_days
from merge_history import _union_days


class PlaCountsTests(unittest.TestCase):
    def test_combined_air_and_ship_totals_are_not_aircraft(self):
        for title in ['中共21機艦擾台', '中共21機艦船台海周邊活動',
                      '共軍21機、艦活動', '共軍21機與艦活動', '共軍21機 艦船']:
            with self.subTest(title=title):
                self.assertIsNone(sortie_count(title))

    def test_separate_counts_and_explicit_aircraft_units(self):
        for title, expected in [('共軍6機10艦船',6),('共機21架次 其中10架越線',21),
                                ('21機艦中有9架共機',9),('6機、10艦',6),('共軍 7 架軍機',7)]:
            self.assertEqual(sortie_count(title),expected)

    def test_model_ids_and_large_counts_are_not_truncated(self):
        for title in ['F-16機', '共機1200架次', '共機1,200架次', '共機1.5架', '共機400架次']:
            self.assertIsNone(sortie_count(title))

    def test_invalid_history_cannot_return_or_displace_valid_day(self):
        bad = {'aircraft':21,'source_title':'共軍21機艦擾台','verified':False}
        good = {'aircraft':6,'source_title':'共軍6機10艦船','verified':False}
        for local, remote in [(bad,good),(good,bad)]:
            self.assertEqual(_union_days({'days':{'day':local}}, {'days':{'day':remote}})['day'],good)
        self.assertEqual(_union_days({'days':{'day':bad}}, {'days':{'day':bad}}),{})
        verified = {**bad,'verified':True}
        self.assertEqual(usable_days({'day':verified}),{'day':verified})
        legacy = {'aircraft':21}
        self.assertEqual(usable_days({'day':legacy}),{'day':legacy})
