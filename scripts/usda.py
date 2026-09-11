"""Normalize ESR records without mixing marketing years or inventing zeroes."""
import math
from datetime import datetime, timezone

FIELDS = {'net': 'currentMYNetSales', 'next_net': 'nextMYNetSales',
          'commit': 'currentMYTotalCommitment', 'outs': 'outstandingSales',
          'exp': 'accumulatedExports'}

def normalize(record, market_year):
    out = {'w': record['weekEndingDate'][:10], 'market_year': market_year}
    for name, field in FIELDS.items():
        value = record.get(field)
        out[name] = round(value / 1000, 1) if record.get('unitId') == 1 and isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value) else None
    return out

def assemble(name, commodity_code, release, records):
    my = release.get('marketYear') if release else None
    rows = sorted([normalize(r, my) for r in records or [] if r.get('weekEndingDate')], key=lambda r:r['w'])
    latest = rows[-1] if rows else {}
    week = latest.get('w')
    stale = not week or (datetime.now(timezone.utc).date() - datetime.fromisoformat(week).date()).days > 14
    item = {'name': name, 'commodity_code': commodity_code, 'market_year': my,
            'week': week, 'market_year_start': (release or {}).get('marketYearStart'),
            'market_year_end': (release or {}).get('marketYearEnd'),
            'release_at': (release or {}).get('releaseTimeStamp'),
            'week_net_kt': latest.get('net'), 'next_year_net_kt': latest.get('next_net'),
            'outstanding_kt': latest.get('outs'), 'commit_kt': latest.get('commit'),
            'incomplete': not latest or any(latest.get(k) is None for k in FIELDS), 'stale': stale}
    return item, rows
