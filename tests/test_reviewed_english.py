import unittest
from scripts.reviewed_english import REVIEWED, valid_english

class ReviewedEnglish(unittest.TestCase):
    def test_aircraft_and_vessels_cannot_become_carriers(self):
        source='中國出動17機艦擾台 國軍嚴密監控應處'
        self.assertFalse(valid_english(source, 'China deploys 17 aircraft carriers'))
        self.assertTrue(valid_english(source, REVIEWED[source]))
        self.assertTrue(valid_english('中國航空母艦', 'Chinese aircraft carrier'))

    def test_named_entities_and_political_metaphor(self):
        self.assertFalse(valid_english('陸委會表示', 'National Security Council says'))
        self.assertFalse(valid_english('高市陣營', 'High City camp'))
        self.assertFalse(valid_english('沖繩變天', 'Weather changes in Okinawa'))
        for source, english in REVIEWED.items():
            self.assertTrue(valid_english(source, english))
