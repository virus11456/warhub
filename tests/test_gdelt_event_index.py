import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from gdelt_event_index import open_index, ingest, report


def event(id='1'):
    row=['']*61
    for k,v in {0:id,1:'20260912',26:'190',28:'19',59:'20260912141500'}.items(): row[k]=v
    return row

def mention(id='1'):
    row=['']*16
    for k,v in {0:id,2:'20260912141500',5:'https://example.com/a',6:'1',11:'80'}.items(): row[k]=v
    return row

class Tests(unittest.TestCase):
    def setUp(self): self.db=open_index(':memory:')
    def tearDown(self): self.db.close()
    def test_orphans_resolve_when_earlier_batch_arrives(self):
        ingest(self.db,'20260912143000',[],[mention()],'b')
        self.assertEqual(report(self.db)['unresolved_mentions'],1)
        ingest(self.db,'20260912141500',[event()],[],'a')
        self.assertEqual(report(self.db)['unresolved_mentions'],0)
    def test_repeated_batch_and_mentions_do_not_inflate(self):
        ingest(self.db,'20260912141500',[event()],[mention(),mention()],'a')
        self.assertFalse(ingest(self.db,'20260912141500',[event()],[mention(),mention()],'a'))
        ingest(self.db,'20260912143000',[],[mention()],'b')
        self.assertEqual(report(self.db)['unique_mentions'],1)
        self.assertEqual(report(self.db)['event_ids'],1)
    def test_revisions_preserved_and_gap_explicit(self):
        ingest(self.db,'20260912141500',[event()],[],'a')
        revised=event();revised[6]='UPDATED'
        ingest(self.db,'20260912144500',[revised],[],'c')
        result=report(self.db)
        self.assertEqual(result['event_ids'],1)
        self.assertEqual(result['event_versions'],2)
        self.assertEqual(result['gaps_between_saved_batches'][0]['missing_batches'],1)
        with self.assertRaises(ValueError): ingest(self.db,'20260912141500',[revised],[],'changed')
        self.assertEqual(report(self.db),result)
    def test_bad_input_does_not_write_batch(self):
        with self.assertRaises(ValueError): ingest(self.db,'20260912141600',[event()],[],'a')
        self.assertEqual(report(self.db)['processed_batches'],[])
