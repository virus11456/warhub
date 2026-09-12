"""Bounded manual GDELT Events/Mentions probe; never changes scores or sends messages."""
import argparse
import csv
import hashlib
import io
import json
import re
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BASE = 'https://data.gdeltproject.org/gdeltv2/'
LIMIT = 5_000_000


def read_url(url):
    with urllib.request.urlopen(url, timeout=20) as response:
        data = response.read(LIMIT + 1)
    if len(data) > LIMIT: raise ValueError('download_limit')
    return data


def manifest_entries(text):
    entries = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) != 3: raise ValueError('invalid_manifest')
        size, md5, url = fields
        match = re.fullmatch(r'https?://data\.gdeltproject\.org/gdeltv2/(\d{14})\.(export|mentions)\.CSV\.zip',url)
        if not match: continue
        if not size.isdigit() or not 0 < int(size) <= LIMIT or not re.fullmatch('[a-f0-9]{32}',md5):
            raise ValueError('invalid_manifest_integrity')
        stamp, kind = match.groups()
        if kind in entries: raise ValueError('duplicate_manifest_entry')
        entries[kind] = {'batch':stamp, 'bytes':int(size), 'md5':md5,
                         'url':BASE + f'{stamp}.{kind}.CSV.zip'}
    if set(entries) != {'export','mentions'} or entries['export']['batch'] != entries['mentions']['batch']:
        raise ValueError('unpaired_batches')
    return entries


def rows_from_zip(blob, entry, columns):
    if len(blob) != entry['bytes'] or hashlib.md5(blob).hexdigest() != entry['md5']:
        raise ValueError('download_integrity_mismatch')
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names = archive.infolist()
        expected = entry['url'].rsplit('/',1)[1][:-4]
        if len(names) != 1 or names[0].filename != expected or names[0].file_size > 50_000_000:
            raise ValueError('invalid_archive_layout')
        text = archive.read(names[0]).decode('utf-8')
    rows = list(csv.reader(io.StringIO(text), delimiter='\t', quoting=csv.QUOTE_NONE))
    if any(len(row) != columns for row in rows): raise ValueError('invalid_column_count')
    return rows


def summarize(events, mentions, batch):
    # GDELT 2.0 codebook: Events 61 columns; Mentions 16 columns.
    by_id = {}
    for r in events:
        if not r[0].isdigit() or r[0] in by_id: raise ValueError('invalid_event_id')
        datetime.strptime(r[1],'%Y%m%d')
        datetime.strptime(r[59],'%Y%m%d%H%M%S')
        by_id[r[0]] = r
    linked = {}; unlinked = 0; seen = set()
    for r in mentions:
        if not r[0].isdigit(): raise ValueError('invalid_mention_id')
        datetime.strptime(r[2],'%Y%m%d%H%M%S')
        confidence = int(r[11])
        if not 0 <= confidence <= 100: raise ValueError('invalid_confidence')
        identity = (r[0], r[2], r[5], r[6])
        if identity in seen: continue
        seen.add(identity)
        if r[0] not in by_id:
            unlinked += 1; continue
        linked.setdefault(r[0],[]).append({'source':r[4], 'url':r[5],
            'mention_time':r[2], 'confidence':confidence})
    candidates = []
    for event_id, r in by_id.items():
        if r[28] not in {'13','15','18','19','20'}: continue
        candidates.append({'event_id':event_id, 'event_date':r[1], 'date_added':r[59],
            'actor1':r[6], 'actor2':r[16], 'event_code':r[26], 'root_code':r[28],
            'action_country_fips':r[53], 'action_location':r[52], 'source_url':r[60],
            'mentions_in_this_batch':linked.get(event_id,[])})
    return {'schema_version':1, 'source':'GDELT 2.0 Events/Mentions', 'batch':batch,
        'event_rows':len(events), 'mention_rows':len(mentions),
        'unique_mentions':len(seen), 'mentions_for_earlier_events':unlinked,
        'events_with_linked_mentions':len(linked), 'candidate_count':len(candidates),
        'root_code_counts':dict(Counter(r[28] for r in events)),
        'candidates':candidates,
        'limitations':['One batch is a sample, not full-day coverage.',
            'Automated classifications are not verified military incidents.',
            'Mention confidence is extraction confidence, not truth probability.',
            'Mentions can refer to events created in earlier batches; not all join locally.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--manifest',type=Path)
    args=parser.parse_args()
    text=args.manifest.read_text() if args.manifest else read_url(BASE+'lastupdate.txt').decode()
    entries=manifest_entries(text)
    batch=entries['export']['batch']
    now=datetime.now(timezone.utc)
    batch_time=datetime.strptime(batch,'%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
    age=(now-batch_time).total_seconds()
    if not -900 <= age <= 21600: raise ValueError('batch_not_recent')
    folder=args.output/batch
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'manifest.txt').write_text(text)
    parsed={}; digests={}
    for kind, columns in [('export',61),('mentions',16)]:
        entry=entries[kind]
        file=folder/entry['url'].rsplit('/',1)[1]
        blob=file.read_bytes() if file.exists() else read_url(entry['url'])
        parsed[kind]=rows_from_zip(blob,entry,columns)
        if not file.exists(): file.write_bytes(blob)
        digests[kind]=hashlib.sha256(blob).hexdigest()
    report=summarize(parsed['export'],parsed['mentions'],batch)
    report.update(fetched_at=now.isoformat(),sha256=digests)
    # Unique timestamp avoids replacing previous verification metadata.
    path=folder/('report-'+now.strftime('%Y%m%dT%H%M%S%f')+'.json')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='candidates'},ensure_ascii=False))
    print('Saved report:',path)

if __name__=='__main__': main()
