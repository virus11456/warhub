"""Catch machine translations that name a country the English source never mentions.

Seen in production: "US-Iran war fuel inflation" came back as 「俄美伊戰爭…」, adding Russia.
Only additions are rejected: a source may name Moscow while the translation says 俄 (fine),
but a translation saying 俄 with no Russia/Moscow/Kremlin/Putin in the source is wrong.
"""
import re

# Chinese marker → English evidence that must appear in the source title.
ENTITIES = (
    (re.compile(r'(?<!塞)俄'), re.compile(r'russ(ia|o)|moscow|kremlin|putin|soviet|ussr', re.I)),  # 埃塞俄比亞 is Ethiopia
    (re.compile(r'烏克蘭|烏軍|烏國|俄烏'), re.compile(r'ukrain|kyiv|kiev|zelensk|donbas|crimea', re.I)),
    (re.compile(r'伊朗'), re.compile(r'iran|tehran|khamenei|irgc|persian', re.I)),
    (re.compile(r'以色列|以軍'), re.compile(r'israel|idf|netanyahu|jerusalem|tel aviv', re.I)),
    (re.compile(r'北韓|朝鮮'), re.compile(r'korea|pyongyang|kim jong|dprk', re.I)),
    (re.compile(r'菲律賓'), re.compile(r'philippin|manila|marcos|\bPH\b|\bPCG\b', re.I)),
    (re.compile(r'日本|日軍'), re.compile(r'japan|tokyo|takaichi|ishiba|okinawa', re.I)),
)


def added_entities(source: str, translated: str) -> list[str]:
    """Chinese entity markers in the translation with no matching name in the English source."""
    if not isinstance(source, str) or not isinstance(translated, str):
        return []
    return [zh.pattern for zh, en in ENTITIES if zh.search(translated) and not en.search(source)]
