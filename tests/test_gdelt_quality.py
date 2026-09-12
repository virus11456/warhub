import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from datetime import datetime, timezone, timedelta
from gdelt_quality import timeline_metrics, cooldown_active, cooldown_deadline

class Tests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,9,12,12,tzinfo=timezone.utc)
        self.points=[{'date':(self.now-timedelta(minutes=15*i)).strftime('%Y%m%dT%H%M%SZ'),'value':0} for i in range(6)]
    def test_observation_time_and_zero(self):
        result=timeline_metrics({'timeline':[{'data':self.points}]},self.now+timedelta(hours=1))
        self.assertEqual(result['observed_at'],self.now.isoformat())
        self.assertEqual(result['latest'],0)
        self.assertFalse(result['stale'])
        self.assertTrue(timeline_metrics({'timeline':[{'data':self.points}]},self.now+timedelta(hours=7))['stale'])
    def test_reject_invalid_or_duplicate_points(self):
        for points in ([{'value':1}],self.points+[self.points[0]], [{**p,'value':float('nan')} for p in self.points]):
            with self.assertRaises((ValueError,KeyError)): timeline_metrics({'timeline':[{'data':points}]},self.now)
    def test_persisted_cooldown_expires(self):
        row={'cooldown_until':cooldown_deadline({},self.now)}
        self.assertTrue(cooldown_active({'a':row},self.now+timedelta(hours=2)))
        self.assertFalse(cooldown_active({'a':row},self.now+timedelta(hours=7)))
