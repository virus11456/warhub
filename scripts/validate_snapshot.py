"""Run the production collector against isolated files, with notifications disabled."""
import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
import fetch_data as f

async def main():
    logging.disable(logging.CRITICAL)
    os.environ['WARHUB_NO_NOTIFY']='1'
    start=time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp)
        for name in ['DATA_FILE','HISTORY_FILE','FOOD_HISTORY_FILE','STRAT_HISTORY_FILE','PLA_HISTORY_FILE','METRICS_DAILY_FILE']:
            original=getattr(f,name)
            target=tmp/original.name
            if original.exists(): shutil.copyfile(original,target)
            setattr(f,name,target)
        f.DATA_DIR=tmp
        # Exercise live current sources. Preserve historical baselines, but avoid a
        # multi-year backfill in this bounded integration run.
        old=json.loads(f.DATA_FILE.read_text())
        for key in ['food','strat','usda']:
            if isinstance(old.get(key),dict): old[key]['updated_at']='2000-01-01T00:00:00+00:00'
        f.DATA_FILE.write_text(json.dumps(old))
        for name in ['HIST_MIRROR_BUDGET','HIST_CHINA_BUDGET','STRAT_HIST_MIRROR_BUDGET','STRAT_HIST_CHINA_BUDGET']:
            setattr(f,name,0)
        try:
            await asyncio.wait_for(f.main(),timeout=660)
            data=json.loads(f.DATA_FILE.read_text())
            assert data['score']['model_version']=='wpi-4.0'
            assert '_notify' not in data
            report={'status':'completed','seconds':round(time.monotonic()-start),
                    'updated_at':data['updated_at'],'score':data['score'],
                    'sources':data['source_health'],
                    'food':data.get('food'),'strat':data.get('strat'),'usda':data.get('usda',{}).get('items') if data.get('usda') else None}
            Path('validated-snapshot.json').write_text(json.dumps(data,ensure_ascii=False))
        except Exception as exc:
            report={'status':'failed','failure_type':type(exc).__name__,'seconds':round(time.monotonic()-start)}
        Path('snapshot-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps(report,ensure_ascii=False,indent=2))
        if report['status']!='completed': raise SystemExit(1)
if __name__=='__main__': asyncio.run(main())
