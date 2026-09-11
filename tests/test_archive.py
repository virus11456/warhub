import gzip
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from archive_snapshot import archive_snapshot, FILES


class ArchiveTests(unittest.TestCase):
    def fixture(self, source):
        for name in FILES:
            data = {'months': {}} if name != 'history.json' else []
            if name == 'data.json':
                data = {'updated_at': '2026-09-11T06:02:11+00:00',
                        'source': {'value': None, 'stale': True, 'observed_at': '2025-01-01'},
                        '_notify': {'private_delivery': 'excluded'}}
            (source / name).write_text(json.dumps(data))

    def test_roundtrip_content_hash_and_idempotent_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);source = root / 'data';source.mkdir();self.fixture(source)
            output = root / 'archives'
            path = archive_snapshot(source, output, 'a' * 40)
            original = path.read_bytes()
            raw = gzip.decompress(original);payload = json.loads(raw)
            self.assertEqual(set(payload['files']), set(FILES))
            self.assertEqual(payload['files']['data.json']['source'],
                             {'value': None, 'stale': True, 'observed_at': '2025-01-01'})
            self.assertNotIn('_notify', payload['files']['data.json'])
            self.assertIn('_notify', json.loads((source / 'data.json').read_text()))
            self.assertIn(hashlib.sha256(raw).hexdigest(), path.name)
            self.assertEqual(archive_snapshot(source, output, 'a' * 40), path)
            self.assertEqual(path.read_bytes(), original)
            # A revision at the same observation time must preserve the prior file.
            (source / 'history.json').write_text('[{"score": 4}]')
            revised = archive_snapshot(source, output, 'a' * 40)
            self.assertNotEqual(revised, path)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(len(list(output.rglob('*.gz'))), 2)

    def test_missing_or_invalid_source_fails_without_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp);self.fixture(source);out = source / 'out'
            (source / 'history.json').write_text('broken')
            with self.assertRaises(ValueError):
                archive_snapshot(source, out, 'a' * 40)
            self.assertFalse(out.exists())
            self.fixture(source);(source / 'strat_history.json').unlink()
            with self.assertRaises(FileNotFoundError):
                archive_snapshot(source, out, 'a' * 40)
            self.assertFalse(out.exists())

    def test_corrupted_existing_archive_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp);self.fixture(source);out = source / 'out'
            path = archive_snapshot(source, out, 'a' * 40)
            path.write_bytes(gzip.compress(b'wrong'))
            with self.assertRaises(ValueError):
                archive_snapshot(source, out, 'a' * 40)
            self.assertEqual(gzip.decompress(path.read_bytes()), b'wrong')
