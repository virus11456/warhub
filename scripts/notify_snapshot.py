"""Scheduled digest of a fresh saved snapshot, without collecting any sources.

prepare sends real normal notifications; tests must mock run_notifications.
apply only merges receipts into the matching snapshot after publication retries.
"""
import argparse
import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from alerts import run_notifications
from collection_guard import MIN_INTERVAL_SECONDS


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed if parsed.tzinfo is not None else None
    except (AttributeError, ValueError, TypeError):
        return None


def eligible(snapshot, now):
    if not isinstance(snapshot, dict):
        return False
    observed = timestamp(snapshot.get('updated_at'))
    if observed is None or not 0 <= (now - observed).total_seconds() < MIN_INTERVAL_SECONDS:
        return False
    previous = snapshot.get('_notify') or {}
    if not isinstance(previous, dict):
        return False
    delivered = timestamp(previous.get('digest_snapshot_at'))
    # Legacy successful delivery provides a conservative no-replay boundary.
    if delivered is None:
        delivery = previous.get('delivery') or {}
        if not isinstance(delivery, dict):
            return False
        results = delivery.get('digest') or {}
        if not isinstance(results, dict):
            return False
        if results and all(value is True for value in results.values()):
            delivered = timestamp(delivery.get('checked_at'))
    return delivered is None or observed > delivered


def fingerprint(snapshot):
    # Include every observation field, excluding only notification bookkeeping.
    content = {key: value for key, value in snapshot.items() if key != '_notify'}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


async def prepare(snapshot, now):
    event = os.environ.get('GITHUB_EVENT_NAME')
    enabled = event == 'schedule' or (event == 'workflow_dispatch'
                                    and os.environ.get('WARHUB_NOTIFY_ONLY') == 'true')
    if not enabled or os.environ.get('WARHUB_NO_NOTIFY') == '1':
        return None
    if not eligible(snapshot, now):
        return None
    previous = snapshot.get('_notify') or {}
    observed_hash = fingerprint(snapshot)
    notify = await run_notifications(snapshot, previous, digest_only=True)
    if notify == previous:
        return None
    return {'snapshot_hash': observed_hash, 'previous_notify': previous, 'notify': notify}


def apply(snapshot, pending):
    # Push retries may encounter newer data or another notification writer.
    # Never transplant receipts to another snapshot or overwrite newer receipts.
    if fingerprint(snapshot) != pending['snapshot_hash']:
        raise ValueError('snapshot changed; retain receipt artifact for reconciliation')
    current = snapshot.get('_notify') or {}
    if current == pending['notify']:
        return snapshot  # Previous push succeeded despite an ambiguous response.
    if current != pending['previous_notify']:
        raise ValueError('notification state changed; retain receipt artifact for reconciliation')
    return {**snapshot, '_notify': pending['notify']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'apply'])
    parser.add_argument('--state', required=True)
    parser.add_argument('--data', default='data/data.json')
    args = parser.parse_args()
    path, state = Path(args.data), Path(args.state)
    snapshot = json.loads(path.read_text(encoding='utf-8'))
    if args.action == 'prepare':
        # Reject a stale state file; do not accidentally publish an older attempt.
        if state.exists():
            raise FileExistsError('notification state file already exists')
        pending = asyncio.run(prepare(snapshot, datetime.now(timezone.utc)))
        if pending is not None:
            state.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Saved-snapshot notification checked; receipt state saved.' if pending else
              'Saved-snapshot notification skipped: quiet, non-scheduled, stale, or already delivered.')
    else:
        pending = json.loads(state.read_text(encoding='utf-8'))
        updated = apply(snapshot, pending)
        if updated != snapshot:
            path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
