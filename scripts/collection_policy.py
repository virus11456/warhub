"""Collection cadence; cache reuse never changes source observation timestamps."""
from datetime import datetime, timezone

SLOW_SOURCES = ('food', 'usda', 'strat', 'fred')

def elapsed_hours(value, now):
    try:
        age = (now - datetime.fromisoformat(value)).total_seconds() / 3600
        return age if age >= 0 else None
    except (TypeError, ValueError):
        return None

def plan(previous, mode='auto', now=None):
    if mode not in ('auto', 'fast', 'full'):
        raise ValueError('WARHUB_COLLECTION_MODE must be auto, fast or full')
    now = now or datetime.now(timezone.utc)
    meta = previous.get('collection') or {}
    slow_age = elapsed_hours(meta.get('slow_attempted_at'), now)
    history_age = elapsed_hours(meta.get('history_attempted_at'), now)
    # No cadence metadata means bootstrap on the first automatic run.
    slow = mode == 'full' or (mode == 'auto' and (slow_age is None or slow_age >= 6))
    history = mode == 'full' or (mode == 'auto' and (history_age is None or history_age >= 24))
    return {'mode': mode, 'slow_refresh': slow, 'history_refresh': history,
            'slow_attempted_at': now.isoformat() if slow else meta.get('slow_attempted_at'),
            'history_attempted_at': now.isoformat() if history else meta.get('history_attempted_at'),
            'reused_sources': [] if slow else list(SLOW_SOURCES), 'duration_seconds': {}}
