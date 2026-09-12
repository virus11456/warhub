"""Local persistent index of verified saved GDELT batches; no network or scoring."""
import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from probe_gdelt_events import manifest_entries, rows_from_zip, summarize


def open_index(path):
    db = sqlite3.connect(path)
    db.executescript('''
        CREATE TABLE IF NOT EXISTS batches (batch TEXT PRIMARY KEY, digest TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events (id TEXT NOT NULL, batch TEXT NOT NULL,
            payload TEXT NOT NULL, PRIMARY KEY(id,batch));
        CREATE TABLE IF NOT EXISTS mentions (identity TEXT PRIMARY KEY, event_id TEXT NOT NULL,
            mention_time TEXT NOT NULL, url TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS mention_batches (identity TEXT NOT NULL, batch TEXT NOT NULL,
            PRIMARY KEY(identity,batch));
        CREATE INDEX IF NOT EXISTS mentions_event ON mentions(event_id);
    ''')
    return db


def ingest(db, batch, events, mentions, digest):
    stamp = datetime.strptime(batch,'%Y%m%d%H%M%S')
    if stamp.minute % 15 or stamp.second: raise ValueError('invalid_batch_interval')
    summarize(events, mentions, batch)  # Existing codebook/scope validation.
    old = db.execute('SELECT digest FROM batches WHERE batch=?',(batch,)).fetchone()
    if old:
        if old[0] != digest: raise ValueError('batch_content_changed')
        return False
    with db:
        db.execute('INSERT INTO batches VALUES (?,?)',(batch,digest))
        for row in events:
            db.execute('INSERT INTO events VALUES (?,?,?)',(row[0],batch,json.dumps(row)))
        for row in mentions:
            identity = hashlib.sha256(json.dumps([row[0],row[2],row[5],row[6]],ensure_ascii=False).encode()).hexdigest()
            db.execute('INSERT OR IGNORE INTO mentions VALUES (?,?,?,?,?)',
                       (identity,row[0],row[2],row[5],json.dumps(row)))
            db.execute('INSERT OR IGNORE INTO mention_batches VALUES (?,?)',(identity,batch))
    return True


def ingest_folder(db, folder):
    entries = manifest_entries((folder/'manifest.txt').read_text())
    batch = entries['export']['batch']
    if folder.name != batch: raise ValueError('batch_folder_mismatch')
    parsed = {}; hashes = []
    for kind, cols in [('export',61),('mentions',16)]:
        entry=entries[kind]
        blob=(folder/entry['url'].rsplit('/',1)[1]).read_bytes()
        parsed[kind]=rows_from_zip(blob,entry,cols)
        hashes.append(hashlib.sha256(blob).hexdigest())
    return ingest(db,batch,parsed['export'],parsed['mentions'],':'.join(hashes))


def report(db):
    batches=[r[0] for r in db.execute('SELECT batch FROM batches ORDER BY batch')]
    gaps=[]
    for left,right in zip(batches,batches[1:]):
        a=datetime.strptime(left,'%Y%m%d%H%M%S'); b=datetime.strptime(right,'%Y%m%d%H%M%S')
        count=int((b-a).total_seconds()//900)-1
        if count>0: gaps.append({'start':(a+timedelta(minutes=15)).strftime('%Y%m%d%H%M%S'),
                                 'end':(b-timedelta(minutes=15)).strftime('%Y%m%d%H%M%S'), 'missing_batches':count})
    scalar=lambda sql: db.execute(sql).fetchone()[0]
    return {'schema_version':1,'processed_batches':batches,'gaps_between_saved_batches':gaps,
        'event_ids':scalar('SELECT count(DISTINCT id) FROM events'),
        'event_versions':scalar('SELECT count(*) FROM events'),
        'unique_mentions':scalar('SELECT count(*) FROM mentions'),
        'unresolved_mentions':scalar('SELECT count(*) FROM mentions m WHERE NOT EXISTS (SELECT 1 FROM events e WHERE e.id=m.event_id)'),
        'distinct_article_urls':scalar("SELECT count(DISTINCT url) FROM mentions WHERE url!=''"),
        'coverage_note':'Only saved batches are covered; no claim of complete daily coverage or independent sources.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--database',type=Path,required=True)
    args=parser.parse_args()
    args.database.parent.mkdir(parents=True,exist_ok=True)
    db=open_index(args.database)
    try:
        for folder in sorted(args.source.iterdir()):
            if folder.is_dir() and (folder/'manifest.txt').exists(): ingest_folder(db,folder)
        result=report(db)
        print(json.dumps(result,ensure_ascii=False))
        args.database.with_suffix('.summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    finally: db.close()

if __name__=='__main__': main()
