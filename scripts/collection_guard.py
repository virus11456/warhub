"""Skip closely spaced source collection; scheduled saved-snapshot digests run separately."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

MIN_INTERVAL_SECONDS = 110 * 60  # Ten-minute tolerance around the two-hour schedule.


def should_collect(snapshot, now, force=False):
    if force:
        return True, 'explicit_manual_refresh'
    try:
        observed = datetime.fromisoformat(snapshot['updated_at'].replace('Z', '+00:00'))
        if observed.tzinfo is None:
            raise ValueError('timezone required')
        age = (now - observed).total_seconds()
    except (KeyError, TypeError, ValueError, AttributeError):
        return True, 'missing_or_invalid_timestamp'
    if age < 0:
        return True, 'future_timestamp'
    if age < MIN_INTERVAL_SECONDS:
        return False, 'recent_snapshot'
    return True, 'refresh_due'


def workflow_plan(snapshot, now, event, notify_only=False, quiet=False, force=False):
    manual_digest = event == 'workflow_dispatch' and notify_only
    if manual_digest:
        collect, reason = False, 'explicit_digest_only'
    else:
        collect, reason = should_collect(snapshot, now, event == 'workflow_dispatch' and force)
    notify_saved = not collect and not quiet and (event == 'schedule' or manual_digest)
    return collect, reason, notify_saved


if __name__ == '__main__':
    try:
        snapshot = json.loads(Path('data/data.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        snapshot = {}
    manual = os.getenv('GITHUB_EVENT_NAME') == 'workflow_dispatch'
    force = manual and (os.getenv('FORCE_REFRESH') == 'true' or os.getenv('TEST_PUSH') == 'true')
    collect, reason, notify_saved = workflow_plan(
        snapshot, datetime.now(timezone.utc), os.getenv('GITHUB_EVENT_NAME'),
        notify_only=os.getenv('NOTIFY_ONLY') == 'true',
        quiet=os.getenv('QUIET') == 'true', force=force)
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
        stream.write(f'collect={str(collect).lower()}\nnotify_saved={str(notify_saved).lower()}\n')
    summary = f'Collection {"due" if collect else "skipped"}: {reason}. Minimum spacing: 110 minutes.'
    print(summary)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as stream:
            stream.write(summary + '\n')
