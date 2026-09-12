"""Six-hour batch sampling with durable raw archives and bounded index rebuilds."""
import argparse
import base64
import gzip
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from probe_gdelt_events import collect, manifest_entries, rows_from_zip
from gdelt_event_index import open_index, ingest_folder, report

ROOT=Path(__file__).resolve().parents[1]
MAX_BATCHES=32
MAX_RAW=15_000_000


def due(state, now):
    try:
        age=(now-datetime.fromisoformat(state['attempted_at'])).total_seconds()
        return age < 0 or age >= 21600
    except (KeyError,ValueError,TypeError): return True


def package(folder):
    manifest=(folder/'manifest.txt').read_text()
    entries=manifest_entries(manifest)
    files={}
    for kind, cols in [('export',61),('mentions',16)]:
        entry=entries[kind]; name=entry['url'].rsplit('/',1)[1]
        blob=(folder/name).read_bytes()
        rows_from_zip(blob,entry,cols)
        files[name]=base64.b64encode(blob).decode()
    reports=sorted(folder.glob('report-*.json'))
    fetched_at=json.loads(reports[0].read_text()).get('fetched_at') if reports else None
    return {'fetched_at':fetched_at,'version':1,'kind':'gdelt_event_batch','batch':entries['export']['batch'],
            'manifest':manifest,'zip_files':files}


def save_batch(folder, destination):
    payload=package(folder)
    raw=json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
    digest=hashlib.sha256(raw).hexdigest()
    path=destination/'gdelt-events'/(payload['batch']+'_'+digest+'.json.gz')
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if gzip.decompress(path.read_bytes()) != raw: raise ValueError('archive_collision')
    else:
        with path.open('xb') as stream: stream.write(gzip.compress(raw,mtime=0))
    return path


def restore(path, destination):
    with gzip.open(path,'rb') as stream: raw=stream.read(MAX_RAW+1)
    if len(raw)>MAX_RAW: raise ValueError('archive_size_limit')
    data=json.loads(raw)
    expected=data['batch']+'_'+hashlib.sha256(raw).hexdigest()+'.json.gz'
    if path.name != expected or data.get('kind')!='gdelt_event_batch': raise ValueError('archive_identity')
    entries=manifest_entries(data['manifest'])
    if data['batch'] != entries['export']['batch']: raise ValueError('batch_mismatch')
    folder=destination/data['batch']; folder.mkdir(parents=True,exist_ok=True)
    for kind,cols in [('export',61),('mentions',16)]:
        entry=entries[kind];name=entry['url'].rsplit('/',1)[1]
        blob=base64.b64decode(data['zip_files'][name],validate=True)
        rows_from_zip(blob,entry,cols)
        (folder/name).write_bytes(blob)
    (folder/'manifest.txt').write_text(data['manifest'])
    return folder


def sample(snapshot, archives, destination, now=None, collector=collect):
    now=now or datetime.now(timezone.utc)
    previous=snapshot.get('gdelt_events_sampling') or {}
    if not due(previous,now): return snapshot
    state={**previous,'attempted_at':now.isoformat()}
    try:
        with tempfile.TemporaryDirectory(prefix='warhub-gdelt-') as td:
            work=Path(td)
            folder=collector(work)
            saved=save_batch(folder,destination)
            # Keep all raw archives; rebuild only the newest 32 saved batches.
            paths={p.name:p for p in (archives/'gdelt-events').glob('*.json.gz')}
            paths[saved.name]=saved
            by_batch={p.name[:14]:p for p in sorted(paths.values(),key=lambda p:p.name)}
            selected=[by_batch[k] for k in sorted(by_batch)[-MAX_BATCHES:]]
            db=open_index(':memory:')
            try:
                for path in selected: ingest_folder(db,restore(path,work))
                summary=report(db)
            finally: db.close()
            state.update(status='sampled',stale=False,last_success_at=now.isoformat(),
                         latest_batch=folder.name,index=summary,
                         sampling_interval_hours=6,index_batch_limit=MAX_BATCHES,
                         archive_path='archives/gdelt-events/'+saved.name)
            state.pop('error',None)
    except Exception as exc:
        state.update(status='failed',stale=True,error=type(exc).__name__)
    snapshot['gdelt_events_sampling']=state
    return snapshot


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=ROOT/'data/data.json')
    parser.add_argument('--archives',type=Path,default=ROOT/'archives')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    snapshot=json.loads(args.data.read_text())
    before=json.dumps(snapshot,sort_keys=True)
    sample(snapshot,args.archives,args.output)
    if json.dumps(snapshot,sort_keys=True)!=before:
        args.data.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2))
    print('GDELT batch sampling:',(snapshot.get('gdelt_events_sampling') or {}).get('status','not_due'))

if __name__=='__main__': main()
