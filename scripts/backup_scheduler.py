"""External, bounded recovery trigger. No collection or notification code here."""
import argparse
import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler

BASE = 'https://api.github.com/repos/virus11456/warhub'
WORKFLOW = '/actions/workflows/update-data.yml'
MAX_BYTES = 4 * 1024 * 1024
STALE_SECONDS = 130 * 60
COOLDOWN_SECONDS = 120 * 60


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward the private repository credential elsewhere.


class GitHub:
    def __init__(self, token):
        if not token or not token.strip():
            raise ValueError('missing credential')
        self.token = token.strip()
        self.opener = build_opener(NoRedirect())

    def request(self, path, payload=None, raw=False):
        headers = {'Authorization': 'Bearer ' + self.token,
                   'Accept': 'application/vnd.github.raw+json' if raw else 'application/vnd.github+json',
                   'X-GitHub-Api-Version': '2026-03-10',
                   'User-Agent': 'warhub-backup-scheduler'}
        data = None if payload is None else json.dumps(payload).encode()
        if data is not None:
            headers['Content-Type'] = 'application/json'
        request = Request(BASE + path, data=data, headers=headers)
        with self.opener.open(request, timeout=15) as response:
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError('response too large')
            return json.loads(body) if body else None


def age_seconds(value, now):
    observed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if observed.tzinfo is None:
        raise ValueError('timezone missing')
    age = (now - observed).total_seconds()
    if age < 0:
        raise ValueError('future timestamp')
    return age


def save_state(path, state):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state), encoding='utf-8')
    temporary.replace(path)


def check(client, state_path, now, apply=False):
    # Invalid state fails closed: don't turn corruption into repeated triggers.
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if not isinstance(state, dict):
        raise ValueError('invalid local state')
    if state.get('attempted_at') and age_seconds(state['attempted_at'], now) < COOLDOWN_SECONDS:
        return 'cooldown'
    snapshot = client.request('/contents/data/data.json?ref=main', raw=True)
    if age_seconds(snapshot['updated_at'], now) < STALE_SECONDS:
        return 'fresh'
    workflow = client.request(WORKFLOW)
    if workflow.get('state') != 'active':
        return 'workflow_disabled'
    # Query unfinished runs explicitly, including old queued/waiting runs.
    for status in ('queued', 'in_progress', 'waiting', 'pending', 'requested'):
        result = client.request(WORKFLOW + '/runs?per_page=1&status=' + status)
        if not isinstance(result.get('total_count'), int) or result['total_count'] < 0:
            raise ValueError('invalid workflow response')
        if result['total_count']:
            return 'workflow_busy'
    if not apply:
        return 'would_dispatch'
    # Persist before POST: an ambiguous timeout must not cause a trigger storm.
    state = {'attempted_at': now.isoformat(), 'outcome': 'attempting'}
    save_state(state_path, state)
    try:
        client.request(WORKFLOW + '/dispatches', {
            'ref': 'main', 'inputs': {'collection_mode': 'auto', 'force_refresh': 'false',
                                     'test_push': 'false', 'quiet': 'true'}})
    except Exception:
        state['outcome'] = 'unknown_or_failed'
        save_state(state_path, state)
        raise
    state['outcome'] = 'accepted'  # Accepted is not a successful collection.
    save_state(state_path, state)
    return 'dispatch_accepted'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--apply', action='store_true', help='Actually dispatch; default is read-only')
    args = parser.parse_args()
    args.state.parent.mkdir(parents=True, exist_ok=True)
    with args.state.with_suffix('.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('local_check_busy')
            return 0
        try:
            directory = os.getenv('CREDENTIALS_DIRECTORY')
            token = (Path(directory) / 'github-token').read_text() if directory else os.getenv('WARHUB_DISPATCH_TOKEN')
            print(check(GitHub(token), args.state, datetime.now(timezone.utc), args.apply))
            return 0
        except Exception as exc:
            # Never log response bodies, headers or exception text containing credentials.
            print('check_failed:' + type(exc).__name__)
            return 1


if __name__ == '__main__':
    raise SystemExit(main())
