import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from scoring import risk_off_cluster

class RiskOffClusterTests(unittest.TestCase):
    def full(self):
        return {symbol: {'dev': 0} for symbol in ('GC=F','BZ=F','^VIX','USDCHF=X','^TNX','LMT','RTX','NOC','GD')}

    def test_missing_inputs_do_not_become_zero(self):
        result = risk_off_cluster({})
        self.assertIsNone(result['risk_off_cluster'])
        self.assertEqual(result['risk_off_observed'], 0)

    def test_real_zero_requires_complete_observation(self):
        result = risk_off_cluster(self.full())
        self.assertEqual(result['risk_off_cluster'], 0)
        self.assertEqual(result['risk_off_observed'], 6)

    def test_direction_and_inclusive_threshold(self):
        data = self.full()
        for symbol in ('GC=F','BZ=F','^VIX','LMT'): data[symbol]['dev'] = 5
        for symbol in ('USDCHF=X','^TNX'): data[symbol]['dev'] = -5
        self.assertEqual(risk_off_cluster(data)['risk_off_cluster'], 6)

    def test_partial_defense_is_unknown_unless_positive_signal_observed(self):
        data = self.full(); del data['GD']
        self.assertIsNone(risk_off_cluster(data)['risk_off_cluster'])
        data['LMT']['dev'] = 6
        self.assertEqual(risk_off_cluster(data)['risk_off_cluster'], 1)

    def test_invalid_deviations_are_missing(self):
        for value in (None, '0', True, float('nan'), float('inf')):
            data = self.full(); data['GC=F']['dev'] = value
            result = risk_off_cluster(data)
            self.assertIsNone(result['risk_off_cluster'])
            self.assertEqual(result['risk_off_observed'], 5)

if __name__ == '__main__':
    unittest.main()
