import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock
from collect_gdelt_events import due, sample, save_batch, restore

class Tests(unittest.TestCase):
    def test_cadence_and_failure_preserves_old_index(self):
        now=datetime(2026,9,12,tzinfo=timezone.utc)
        previous={'attempted_at':now.isoformat(),'index':{'event_ids':7},'last_success_at':now.isoformat()}
        snap={'gdelt_events_sampling':previous.copy()}
        collector=Mock(side_effect=TimeoutError())
        self.assertFalse(due(previous,now+timedelta(hours=2)))
        sample(snap,Path('/unused'),Path('/unused'),now+timedelta(hours=2),collector)
        collector.assert_not_called()
        sample(snap,Path('/unused'),Path('/unused'),now+timedelta(hours=6),collector)
        self.assertEqual(snap['gdelt_events_sampling']['index'],{'event_ids':7})
        self.assertTrue(snap['gdelt_events_sampling']['stale'])
        self.assertEqual(snap['gdelt_events_sampling']['last_success_at'],now.isoformat())
    def test_zip_archive_roundtrip_and_persistent_rebuild(self):
        import hashlib,io,zipfile
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);folder=root/'20260912141500';folder.mkdir()
            lines=[]
            for kind in ('export','mentions'):
                name=folder.name+'.'+kind+'.CSV'
                stream=io.BytesIO()
                with zipfile.ZipFile(stream,'w') as z: z.writestr(name,'')
                blob=stream.getvalue();(folder/(name+'.zip')).write_bytes(blob)
                lines.append(f'{len(blob)} {hashlib.md5(blob).hexdigest()} http://data.gdeltproject.org/gdeltv2/{name}.zip')
            (folder/'manifest.txt').write_text('\n'.join(lines))
            archived=save_batch(folder,root/'archives')
            restored=restore(archived,root/'restored')
            self.assertEqual((restored/'manifest.txt').read_text(),(folder/'manifest.txt').read_text())
            snap={}
            sample(snap,root/'archives',root/'new',collector=lambda work:folder)
            self.assertEqual(snap['gdelt_events_sampling']['status'],'sampled')
            self.assertEqual(snap['gdelt_events_sampling']['index']['processed_batches'],[folder.name])
