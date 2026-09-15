import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from build_ui_assets import build
from translate_ui import masked, restore


class UIAssets(unittest.TestCase):
    def test_missing_translation_cannot_be_published_as_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'locales').mkdir()
            (root/'locales/source.json').write_text(json.dumps(['缺資料']))
            (root/'locales/en.json').write_text('{}')
            with self.assertRaises(ValueError):build(root)
            self.assertFalse((root/'locales/en.js').exists())
            (root/'locales/en.json').write_text(json.dumps({'缺資料':'Missing data'}))
            build(root);self.assertIn('Missing data',(root/'locales/en.js').read_text())

    def test_numeric_placeholders_preserve_values_and_reject_omissions(self):
        text,values=masked('3天、40筆／600筆，日期2026-09-15')
        self.assertEqual(restore(text.replace('天',' days').replace('筆',' notices').replace('日期','date'),values),
                         '3 days、40 notices／600 notices，date2026-09-15')
        with self.assertRaises(ValueError):restore('40 notices',values)
        with self.assertRaises(ValueError):restore('仍是中文',[])
        with self.assertRaises(ValueError):restore('[[N0]] notices, 100 confirmed', ['40'])
        with self.assertRaises(ValueError):restore(' ', [])
