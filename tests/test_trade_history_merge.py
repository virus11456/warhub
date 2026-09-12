import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from merge_history import _union_months


def row(value=12, reporters=('76','842')):
    return {'schema_version':2, 'src':'mirror', 'soy':value, 'us_soy':4,
            'coverage':{'1201':list(reporters)}, 'observed_at':'saved-time'}


class HistoryMergeTests(unittest.TestCase):
    def merge(self, new, old):
        return _union_months({'months':{'2026-07':new}}, {'months':{'2026-07':old}})['2026-07']

    def test_subset_and_equal_count_different_reporters_keep_whole_saved_row(self):
        old=row()
        for new in (row(3,('842',)),row(30,('842','36'))):
            new['observed_at']='new-time'
            new['wheat']=999
            result=self.merge(new,old)
            self.assertEqual(result,old)
            self.assertNotIn('wheat',result)

    def test_equal_and_superset_coverage_accept_downward_revision_and_zero(self):
        for new in (row(0),row(1,('76','842','36'))):
            self.assertEqual(self.merge(new,row()),new)

    def test_missing_weight_cannot_replace_known_zero(self):
        self.assertEqual(self.merge(row(None),row(0)),row(0))
        self.assertEqual(self.merge(row(float('nan')),row(0)),row(0))

    def test_strategic_commodity_and_absent_coverage(self):
        old={'schema_version':2,'src':'mirror','2601':90,'coverage':{'2601':['36','76']}}
        new={'schema_version':2,'src':'mirror','2601':50,'coverage':{}}
        self.assertEqual(self.merge(new,old),old)

    def test_direct_reporting_does_not_mix_with_mirror_and_legacy_upgrades(self):
        direct=dict(row(),src='china')
        self.assertEqual(self.merge(direct,row()),direct)
        self.assertEqual(self.merge({'soy':99},row()),row())

    def test_month_union_and_inputs_unchanged(self):
        local={'months':{'2026-07':row(1,('842',)), '2026-08':row()}}
        remote={'months':{'2026-07':row(), '2026-06':row()}}
        before=copy.deepcopy((local,remote))
        result=_union_months(local,remote)
        self.assertEqual(set(result),{'2026-06','2026-07','2026-08'})
        self.assertEqual((local,remote),before)
