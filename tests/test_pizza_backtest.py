import sys
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from pizza_backtest import calculate, VERSION

BASE=datetime(2026,9,1,tzinfo=timezone.utc)
def ts(h): return (BASE+timedelta(hours=h)).isoformat()
def row(h, level, source=None): return {'at':ts(h),'source_at':ts(h if source is None else source),'level':level,'archive':'fixture'}

class PizzaBacktestTests(unittest.TestCase):
    def calc(self, rows, cutoff=100, reviews=None): return calculate(rows,reviews or {},ts(cutoff))['groups']
    def test_separate_thresholds_and_sustained(self):
        g=self.calc([row(0,5),row(2,3),row(4,2),row(6,1),row(8,4),row(10,3)])
        self.assertEqual(g['3']['detected_crossings'],2)
        self.assertEqual(g['2']['detected_crossings'],1)
        self.assertEqual(g['3']['events'][0]['at'],ts(2))
        self.assertEqual(g['2']['events'][0]['at'],ts(4))
    def test_pending_and_unreviewed_never_zero_rate(self):
        g=self.calc([row(0,5),row(2,2)],49)['2']
        self.assertEqual(g['counts']['pending'],1);self.assertIsNone(g['rate'])
        g=self.calc([row(0,5),row(2,2)],50)['2']
        self.assertEqual(g['counts']['unreviewed'],1);self.assertIsNone(g['rate'])
    def test_gap_missing_invalid_and_left_censoring(self):
        for rows in ([row(0,2)],[row(0,5),row(7,2)], [row(0,5),row(1,None),row(2,2)], [row(0,5),row(1,True),row(2,2)]):
            g=self.calc(rows)['2'];self.assertEqual(g['counts']['uncertain_start'],1);self.assertEqual(g['detected_crossings'],0)
    def test_repeated_upstream_and_stale(self):
        g=self.calc([row(0,5),row(2,2),row(4,2,2),row(5,2,2)])['2']
        self.assertEqual(g['detected_crossings'],1);self.assertEqual(g['repeated'],2)
        self.assertEqual(self.calc([row(0,5),row(8,2,0)])['2']['invalid'],1)
    def test_reviews_require_time_scope_and_evidence(self):
        event=f'{VERSION}:2:{ts(2)}'
        review={'scope':'major-us-direct-action-v1','sources':['https://example.org/official'],'reviewed_at':ts(60),'outcome':'qualifying_action','action_start':ts(10),'action_end':ts(11)}
        g=self.calc([row(0,5),row(2,2)],reviews={event:review})['2']
        self.assertEqual(g['rate'],1);self.assertLess(g['confidence_interval'][0],1)
        for change in ({'sources':[]},{'action_end':ts(51)},{'reviewed_at':ts(49)},{'scope':'other'}):
            self.assertIsNone(self.calc([row(0,5),row(2,2)],reviews={event:{**review,**change}})['2']['rate'])
    def test_negative_requires_full_window_review(self):
        event=f'{VERSION}:2:{ts(2)}'
        review={'scope':'major-us-direct-action-v1','sources':['https://example.org/official'],'reviewed_at':ts(60),'outcome':'no_qualifying_action'}
        self.assertIsNone(self.calc([row(0,5),row(2,2)],reviews={event:review})['2']['rate'])
        review['complete_window']=True
        self.assertEqual(self.calc([row(0,5),row(2,2)],reviews={event:review})['2']['rate'],0)
    def test_selected_positives_do_not_create_cohort_rate(self):
        rows=[row(0,5),row(2,2),row(4,5),row(6,2)]
        r={f'{VERSION}:2:{ts(2)}':{'scope':'major-us-direct-action-v1','sources':['https://example.org/official'],'reviewed_at':ts(90),'outcome':'qualifying_action','action_start':ts(10),'action_end':ts(11)}}
        g=self.calc(rows,reviews=r)['2'];self.assertEqual(g['reviewed'],1);self.assertIsNone(g['rate']);self.assertEqual(g['mature_bounds'],[.5,1])
    def test_future_and_conflicting_observations(self):
        rows=[row(0,5),row(2,2),row(2,4),row(4,2),row(110,2)]
        g=self.calc(rows)['2'];self.assertEqual(g['detected_crossings'],0);self.assertEqual(g['invalid'],1)
    def test_analysis_does_not_mutate_input(self):
        import copy
        rows=[row(0,5),row(2,2)];old=copy.deepcopy(rows);self.calc(rows);self.assertEqual(rows,old)
    def test_build_uses_archives_and_reports_corruption(self):
        import tempfile, json, gzip
        from pizza_backtest import build
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'research').mkdir();a=root/'archives/2026/09';a.mkdir(parents=True)
            (root/'research/pizza-observations.json').write_text(json.dumps({'observations':[row(0,5)]}))
            (root/'research/pizza-reviews.json').write_text(json.dumps({'reviews':{},'candidates':[]}))
            snapshot={'updated_at':ts(2),'defcon_level':2,'defcon_details':{'at_time':ts(2)}}
            (a/'good.json.gz').write_bytes(gzip.compress(json.dumps({'files':{'data.json':snapshot}}).encode()))
            (a/'source.json.gz').write_bytes(gzip.compress(b'{"kind":"source_observation"}'))
            current={'updated_at':ts(100),'defcon_level':5,'defcon_details':{'at_time':ts(100)}}
            report=build(current,root);self.assertEqual(report['groups']['2']['detected_crossings'],1)
            (a/'broken.json.gz').write_bytes(b'broken')
            report=build(current,root);self.assertEqual(report['unreadable_archives'],1);self.assertIsNone(report['groups']['2']['rate'])
