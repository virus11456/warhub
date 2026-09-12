"""Immutable Comtrade observations, separate from derived dashboard snapshots."""
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ('period', 'reporterCode', 'reporterISO', 'partnerCode', 'partnerISO',
          'partner2Code', 'cmdCode', 'cmdDesc', 'flowCode', 'customsCode', 'motCode',
          'netWgt', 'isNetWgtEstimated', 'qty', 'qtyUnitCode', 'isQtyEstimated',
          'primaryValue', 'cifvalue', 'fobvalue', 'isReported', 'isAggregate',
          'classificationCode', 'isOriginalClassification', 'typeCode', 'freqCode')
PARAMS = ('reporterCode', 'period', 'flowCode', 'partnerCode', 'partner2Code',
          'cmdCode', 'motCode', 'customsCode', 'maxRecords')


def save_comtrade(directory, params, rows, weights, mode, fetched_at=None):
    observed = fetched_at or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise ValueError('timezone required')
    observed = observed.astimezone(timezone.utc)
    payload = {'archive_version': 1, 'kind': 'source_observation', 'source': 'comtrade',
               'fetched_at': observed.isoformat(), 'mode': mode,
               'query': {k: params[k] for k in PARAMS if k in params},
               'rows': [{k: row[k] for k in FIELDS if k in row} for row in rows],
               'weights_kg': weights}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     separators=(',', ':'), allow_nan=False).encode()
    digest = hashlib.sha256(raw).hexdigest()
    path = Path(directory) / observed.strftime('%Y/%m') / (observed.strftime('%Y%m%dT%H%M%S') + '_' + digest + '.json.gz')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if gzip.decompress(path.read_bytes()) != raw:
            raise ValueError('archive content mismatch')
    else:
        with path.open('xb') as stream:
            stream.write(gzip.compress(raw, compresslevel=9, mtime=0))
    return path
