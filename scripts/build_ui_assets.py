"""Compile reviewed UI translations into a static asset; no network or keys."""
import json
import re
from pathlib import Path


def build(root=Path('.')):
    source = json.loads((root/'locales/source.json').read_text())
    catalog = json.loads((root/'locales/en.json').read_text())
    override = root/'locales/overrides.json'
    if override.exists():
        catalog.update(json.loads(override.read_text()))
    missing = [s for s in source if not isinstance(catalog.get(s), str) or not catalog[s].strip()
               or re.search(r'[\u3400-\u9fff]', catalog[s])]
    if missing:
        raise ValueError(f'{len(missing)} untranslated UI entries; build refused')
    # Text is applied using DOM text nodes, never as HTML or executable strings.
    output = 'window.WARHUB_EN = '+json.dumps(catalog, ensure_ascii=False, sort_keys=True)+';\n'
    (root/'locales/en.js').write_text(output)
    print(f'Compiled {len(catalog)} English display strings')


if __name__ == '__main__':
    build()
