"""FRED observation dates remain distinct from collection timestamps."""
import math
from datetime import date, datetime, timezone


def parse_observation(payload, now=None):
    now = now or datetime.now(timezone.utc)
    rows = payload.get('observations') or []
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError('missing observation')
    row = rows[0]
    observed = date.fromisoformat(row['date'])
    if observed > now.date():
        raise ValueError('future observation')
    raw = row.get('value')
    if raw in (None, '', '.'):
        value = None
    elif isinstance(raw, bool):
        raise ValueError('invalid observation')
    else:
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError('nonfinite observation')
    return {'value': value, 'observation_date': observed.isoformat(),
            'fetched_at': now.isoformat(), 'status': 'available' if value is not None else 'missing'}
