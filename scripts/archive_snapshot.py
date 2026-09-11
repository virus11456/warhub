#!/usr/bin/env python3
"""Immutable, compressed collector snapshots; no network or notification calls."""
import argparse
import gzip
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ('data.json', 'history.json', 'metrics_daily.json', 'pla_adiz.json',
         'food_history.json', 'strat_history.json')


def archive_snapshot(source: Path, output: Path, code_sha: str) -> Path:
    snapshots = {}
    for name in FILES:
        data = json.loads((source / name).read_text(encoding='utf-8'))
        if not isinstance(data, (dict, list)):
            raise ValueError(f'Invalid snapshot: {name}')
        if name == 'data.json':
            if not isinstance(data, dict):
                raise ValueError('data.json must be an object')
            data.pop('_notify', None)  # Delivery bookkeeping is not analysis data.
        snapshots[name] = data
    observed = datetime.fromisoformat(snapshots['data.json']['updated_at'].replace('Z', '+00:00'))
    if observed.tzinfo is None:
        raise ValueError('Snapshot timestamp must include timezone')
    observed = observed.astimezone(timezone.utc)
    payload = {'archive_version': 1, 'collector_code_sha': code_sha,
               'snapshot_at': observed.isoformat(), 'files': snapshots}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                     allow_nan=False).encode('utf-8')
    digest = hashlib.sha256(raw).hexdigest()
    path = output / observed.strftime('%Y/%m') / (observed.strftime('%Y%m%dT%H%M%S') + '_' + digest + '.json.gz')
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if gzip.decompress(path.read_bytes()) != raw:
            raise ValueError('Existing archive does not match its content hash')
    else:
        with path.open('xb') as stream:
            stream.write(compressed)
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'data')
    parser.add_argument('--output', type=Path, default=ROOT / 'archives')
    args = parser.parse_args()
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    path = archive_snapshot(args.source, args.output, sha)
    print(f'Archived snapshot: {path} ({path.stat().st_size} bytes)')
