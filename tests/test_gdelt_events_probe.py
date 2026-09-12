import hashlib
import io
import sys
import unittest
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from probe_gdelt_events import manifest_entries, rows_from_zip, summarize

class Tests(unittest.TestCase):
    def test_manifest_rejects_unpaired_and_foreign_hosts(self):
        md5='a'*32
        good='\n'.join(f'10 {md5} http://data.gdeltproject.org/gdeltv2/20260912141500.{kind}.CSV.zip' for kind in ('export','mentions'))
        self.assertTrue(manifest_entries(good)['export']['url'].startswith('https://'))
        for bad in (good.splitlines()[0],good.replace('data.gdeltproject.org','example.com'),good+ '\n'+good.splitlines()[0]):
            with self.assertRaises(ValueError): manifest_entries(bad)
    def test_zip_integrity_and_layout(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z: z.writestr('20260912141500.export.CSV','a\tb\n')
        blob=stream.getvalue();entry={'url':'https://data.gdeltproject.org/gdeltv2/20260912141500.export.CSV.zip','bytes':len(blob),'md5':hashlib.md5(blob).hexdigest()}
        self.assertEqual(rows_from_zip(blob,entry,2),[['a','b']])
        with self.assertRaises(ValueError): rows_from_zip(blob+b'x',entry,2)
        with self.assertRaises(ValueError): rows_from_zip(blob,entry,61)
    def test_mentions_dedup_and_earlier_event_are_explicit(self):
        event=['']*61
        for i,v in {0:'10',1:'20260912',26:'190',28:'19',59:'20260912141500'}.items(): event[i]=v
        mention=['']*16
        for i,v in {0:'10',2:'20260912141500',5:'https://example.com/story',6:'1',11:'80'}.items(): mention[i]=v
        earlier=mention.copy();earlier[0]='9'
        report=summarize([event],[mention,mention,earlier],'20260912141500')
        self.assertEqual(report['unique_mentions'],2)
        self.assertEqual(report['mentions_for_earlier_events'],1)
        self.assertEqual(len(report['candidates'][0]['mentions_in_this_batch']),1)
