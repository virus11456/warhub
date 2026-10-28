import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_font_subset as subset


class FontSubsetTests(unittest.TestCase):
    def test_subset_covers_every_character_the_site_uses(self):
        covered = set(subset.CHARS.read_text(encoding='utf-8'))
        missing = sorted(subset.site_chars() - covered)
        self.assertEqual(missing, [], 'run scripts/build_font_subset.py to add: ' + ''.join(missing[:40]))
        self.assertTrue(subset.OUT.exists())
        self.assertLess(subset.OUT.stat().st_size, 150_000)


if __name__ == '__main__':
    unittest.main()
