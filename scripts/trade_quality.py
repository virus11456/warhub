"""Coverage-qualified views of saved mirror trade data; no source requests."""
import math

FOOD = {'1201':'soy','1001':'wheat','1005':'corn'}
EXPECTED = {
 'food':{c:['76','842','32','36','124','804','251'] for c in FOOD},
 'strat':{'4001':['764','360','458','704'],'2604':['608','360','36'],
          '2610':['710','792','398'],'2601':['36','76','710','699']}}

def valid(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0

def codes(values):
    return set(map(str,values)) if isinstance(values,list) else set()

def enrich(snapshot):
    for section,expected in EXPECTED.items():
        block=snapshot.get(section) or {}
        history=snapshot.get('food_hist' if section=='food' else 'strat_hist') or []
        for item in block.get('items',[]):
            cmd=str(item.get('cmd')); exp=set(expected.get(cmd,[]))
            if not exp:continue
            current=codes(item.get('reporter_codes')); previous=codes(item.get('reporter_codes_prev'))
            complete=bool(exp) and current==exp and valid(item.get('wan_ton')) and block.get('schema_version')==2
            comparable=(complete and previous==exp and valid(item.get('prev_wan_ton'))
                        and item['prev_wan_ton']>0 and not block.get('stale'))
            # Retain existing percent only when its provenance is comparable.
            # Do not recompute it from rounded display weights.
            if not comparable:item['yoy_pct']=None
            item['incomplete']=not comparable
            item['current_complete']=complete
            item['expected_reporter_codes']=sorted(exp)
            item['missing_reporter_codes']=sorted(exp-current)
            item['comparison_status']='comparable' if comparable else ('current_incomplete' if not complete else 'baseline_unavailable')
            item['latest_complete']=None
            field=FOOD.get(cmd,cmd) if section=='food' else cmd
            candidates=[]
            for row in history:
                if (row.get('schema_version')==2 and row.get('src')=='mirror' and
                    codes((row.get('coverage') or {}).get(cmd))==exp and exp and valid(row.get(field)) and
                    row.get('ym','')<=block.get('ref_month','')):
                    candidates.append({'month':row['ym'],'wan_ton':row[field],'reporter_codes':sorted(exp)})
            if complete:
                candidates.append({'month':block.get('ref_month'),'wan_ton':item['wan_ton'],'reporter_codes':sorted(exp)})
            if candidates:item['latest_complete']=max(candidates,key=lambda r:r['month'] or '')
            if section=='strat' and not comparable:item['anomaly']='partial'
        if section=='food' and any(str(i.get('cmd')) in expected for i in block.get('items',[])):
            block['breadth_up']=sum(1 for i in block.get('items',[]) if i.get('yoy_pct') is not None and i['yoy_pct']>=15)
    return snapshot

def preserve_food_coverage(old,new):
    """Do not replace a better-covered saved commodity with a transient subset."""
    if old.get('schema_version')!=2 or old.get('src')!='mirror':return new
    for cmd,field in FOOD.items():
        old_codes=codes((old.get('coverage') or {}).get(cmd))
        new_codes=codes((new.get('coverage') or {}).get(cmd))
        if old_codes > new_codes and valid(old.get(field)):
            new[field]=old[field]
            new.setdefault('coverage',{})[cmd]=sorted(old_codes)
            if 'us_'+field in old:new['us_'+field]=old['us_'+field]
            else:new.pop('us_'+field,None)
    return new


def preserve_current_coverage(old, new):
    """Keep a coherent previous snapshot when a refresh loses known reporters.

    Do not blend totals from different retrievals. Source archives retain the new
    partial observations; stale snapshots cannot produce a fresh comparison.
    """
    if old.get('schema_version') != 2 or new.get('schema_version') != 2:
        return new
    old_month, new_month = old.get('ref_month'), new.get('ref_month')
    if not old_month or not new_month:
        return new
    reason = None
    if new_month < old_month:
        reason = 'reference_month_regressed'
    elif new_month == old_month:
        current = {str(i.get('cmd')): i for i in new.get('items', [])}
        for item in old.get('items', []):
            replacement = current.get(str(item.get('cmd')), {})
            known = codes(item.get('reporter_codes'))
            if valid(item.get('wan_ton')) and known and (
                    not known <= codes(replacement.get('reporter_codes')) or
                    not valid(replacement.get('wan_ton'))):
                reason = 'reporter_coverage_regressed'
                break
            baseline = codes(item.get('reporter_codes_prev'))
            if (old.get('prev_year_month') == new.get('prev_year_month') and baseline and
                    valid(item.get('prev_wan_ton')) and
                    (not baseline <= codes(replacement.get('reporter_codes_prev')) or
                     not valid(replacement.get('prev_wan_ton')))):
                reason = 'baseline_coverage_regressed'
                break
    if reason is None:
        return new
    return {**old, 'stale': True, 'refresh_status': reason,
            'last_attempted_at': new.get('updated_at')}
