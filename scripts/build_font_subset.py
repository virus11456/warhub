"""Rebuild fonts/cubic11-subset.woff2: Cubic 11 pixel font cut down to the characters the site uses.

The full font is ~400 KB and only styles headings, badges and numbers, so the page ships a
subset (~85 KB). Needs `pip install fonttools brotli` and the full font file:
  python scripts/build_font_subset.py path/to/Cubic_11.woff2
tests/test_font_subset.py fails when page text uses a character missing from the subset;
characters outside it fall back to the next font in the stack, they never disappear.
"""
import glob
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "fonts" / "cubic11-subset.woff2"
CHARS = ROOT / "fonts" / "cubic11-subset.chars.txt"
EXTRA = "，。、：；！？「」『』（）《》〈〉…—–·．％＋－／～｜０１２３４５６７８９"


def site_chars() -> set[str]:
    chars = {chr(c) for c in range(0x20, 0x7F)} | set(EXTRA)
    for path in [ROOT / "index.html", *map(Path, glob.glob(str(ROOT / "guides" / "*.html")))]:
        chars |= set(path.read_text(encoding="utf-8"))
    chars |= set("".join(json.loads((ROOT / "locales" / "source.json").read_text(encoding="utf-8"))))
    return {c for c in chars if ord(c) >= 0x20}


def main(full_font: str) -> None:
    CHARS.write_text("".join(sorted(site_chars())), encoding="utf-8")
    subprocess.run(["pyftsubset", full_font, f"--text-file={CHARS}", "--flavor=woff2",
                    f"--output-file={OUT}", "--layout-features=*"], check=True)
    print(f"{OUT.name}: {OUT.stat().st_size // 1024} KB, {len(CHARS.read_text(encoding='utf-8'))} characters")


if __name__ == "__main__":
    main(sys.argv[1])
