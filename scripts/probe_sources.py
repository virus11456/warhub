"""Read-only integration probe. Never writes production data or sends notifications.
Output contains status/counts only, not API keys, raw headers or raw response bodies.
"""
import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import aiohttp
import fetch_data as f

async def main():
    logging.disable(logging.CRITICAL)  # Some upstream exception URLs can include secret query params.
    report = {'checked_at':datetime.now(timezone.utc).isoformat(), 'sources':{}}
    with tempfile.TemporaryDirectory() as tmp:
        f.DATA_FILE = Path(tmp)/'empty.json'  # force live reads; no previous snapshot fallback
        async with aiohttp.ClientSession() as session:
            async def one(name, fn, timeout=90):
                try:
                    value = await asyncio.wait_for(fn(session), timeout)
                    result = {'status':'available' if value else 'unavailable'}
                    if isinstance(value,list):
                        result['count'] = len(value)
                        if name=='polymarket': result['questions']=[m['question'] for m in value[:5]]
                    elif isinstance(value,dict):
                        if value.get('error') or value.get('available') is False: result['status']='unavailable'
                        if name=='usda':
                            result['items']=[{k:it.get(k) for k in ('name','week','market_year','week_net_kt','commit_kt','next_year_net_kt','incomplete','stale')} for it in value.get('items',[])]
                        elif name=='finance': result['count']=len(value)
                        elif name=='fred': result['series']=list(value)
                        elif name=='bars': result['live_count']=value.get('open_count',0); result['reason']=value.get('reason')
                        elif name=='pizzint': result['shops']=len(value.get('data',[]));result['live_count']=sum(s.get('current_popularity') is not None for s in value.get('data',[]))
                    report['sources'][name]=result
                except Exception as e:
                    report['sources'][name]={'status':'unavailable','failure_type':type(e).__name__}
            async def gdelt():
                results={}
                for name,cfg in f.REGIONS.items():
                    try:
                        async with session.get(f.GDELT_API,params={'query':cfg['gdelt_q'],'mode':'timelinevol','timespan':'48h','format':'json'},timeout=aiohttp.ClientTimeout(total=15)) as r:
                            body=await r.text()
                            record={'http':r.status}
                            try:
                                data=json.loads(body);record['points']=len((data.get('timeline') or [{}])[0].get('data',[]))
                            except (ValueError,AttributeError):
                                # Only categorize known public error messages, never emit raw upstream text.
                                record['error']='rate_limit' if 'limit' in body.lower() else 'invalid_query' if 'query' in body.lower() or 'keyword' in body.lower() else 'non_json'
                            results[name]=record
                    except Exception as e: results[name]={'failure_type':type(e).__name__}
                    await asyncio.sleep(5)
                report['sources']['gdelt']=results
            async def notam():
                try:
                    async with session.post(f.NOTAM_API,data={'searchType':'0','designatorsForLocation':'RCAA'},timeout=aiohttp.ClientTimeout(total=20)) as r:
                        body=await r.text(); v={'http':r.status}
                        try:v['has_notam_list']=isinstance(json.loads(body).get('notamList'),list)
                        except (ValueError,AttributeError):v['has_notam_list']=False
                        report['sources']['notam']=v
                except Exception as e: report['sources']['notam']={'failure_type':type(e).__name__}
            await asyncio.gather(one('polymarket',f.fetch_polymarket),one('pizzint',f.fetch_pizzint),one('usda',f.fetch_usda_esr),one('bars',f.fetch_bars),one('fred',f.fetch_fred),one('finance',f.fetch_finance),gdelt(),notam())
    report['configured']={name:bool(os.environ.get(name,'')) for name in ['USDA_FAS_API_KEY','BESTTIME_API_KEY','FRED_API_KEY']}
    output=Path('probe-report.json');output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
    # Upstream outages are findings, not a reason to skip remaining independent probes.
    if not report['sources']: raise SystemExit('No sources probed')
if __name__=='__main__':asyncio.run(main())
