"""Public source status. Fetch time is not a claim about observation freshness."""
from datetime import datetime, timezone

LABELS = {'kalshi':'Kalshi', 'pizza':'PizzINT', 'polymarket':'Polymarket', 'aviation':'ADS-B', 'firms':'NASA FIRMS',
          'gdelt':'GDELT', 'notams':'FAA NOTAM', 'wikipedia':'Wikipedia', 'news':'Google News',
          'tw_news':'台海新聞', 'nuclear_seismic':'USGS', 'eonet':'NASA EONET', 'finance':'Yahoo Finance',
          'food':'Comtrade 糧食', 'strat':'Comtrade 物資', 'usda':'USDA ESR', 'bars':'BestTime', 'fred':'FRED'}

def source_health(data):
    out = {}
    for key,label in LABELS.items():
        v = data.get(key)
        status, note, observed = 'available', '', None
        if v is None or v == {} or v == []:
            status, note = 'unavailable', '未取得有效資料；不等同零事件'
        elif isinstance(v,list) and all(isinstance(r,dict) and r.get('stale') for r in v):
            status, note = 'stale', '沿用舊資料'
        elif isinstance(v,dict):
            observed = v.get('observed_at') or v.get('updated_at')
            if v.get('error') or v.get('available') is False:
                status, note = 'unavailable', v.get('reason') or '來源回應失敗'
            elif v.get('stale'):
                status, note = 'stale', '沿用舊資料，未納入即時評分'
            if key in ('gdelt','notams'):
                fresh = [r for r in v.values() if isinstance(r,dict) and not r.get('stale') and not r.get('partial') and r.get('available') is not False]
                status = 'available' if len(fresh)==5 else ('partial' if fresh else 'stale')
                note = f'{len(fresh)}/5 地區取得新資料；舊值不計分'
                if key == 'notams' and any(r.get('provider') == 'NOTAC' for r in v.values() if isinstance(r,dict)):
                    label = 'NOTAC / FAA NOTAM'
                    note += '；僅查詢範圍，部分頁面不計分'
            if key == 'nuclear_seismic':
                n = sum(s.get('count') is not None for s in v.get('sites',[]))
                status = 'available' if n==5 else 'partial' if n else 'unavailable'
                note = f'{n}/5 測區查詢成功；地震不等於核試驗'
            if key in ('food','strat','usda'):
                items=v.get('items') or []
                if items and not v.get("stale"):
                    fresh=sum(not r.get('incomplete') and not r.get('stale') for r in items)
                    measured=[r for r in items if any(r.get(k) is not None for k in ('wan_ton','week_net_kt','commit_kt'))]
                    status='available' if fresh==len(items) else 'partial' if measured else 'unavailable'
                    if measured and all(r.get('stale') for r in measured): status='stale'
                note = '觀測期間：' + str(v.get('ref_month') or v.get('week_ending') or '未知') + '；與抓取時間不同'
        if key in ('food', 'strat') and isinstance(v, dict) and v.get('cache_reused_at'):
            note += '；沿用22小時來源快取，未重新查詢，原取得時間不變'
        if key == 'fred' and isinstance(v, dict):
            records = v.get('observations') or {}
            valid = [records.get(k, {}) for k in ('em_oas', 'hy_oas')
                     if v.get(k) is not None and records.get(k, {}).get('observation_date')]
            status = 'available' if len(valid) == 2 else 'partial' if valid else 'unavailable'
            dates = sorted({r['observation_date'] for r in valid})
            observed = dates[0] if dates else None
            note = '官方觀測日：' + '、'.join(dates) if dates else '缺少可核實的官方觀測日期'
        if key == 'kalshi' and isinstance(v, dict):
            status = v.get('status') if v.get('status') in ('available','partial','stale','unavailable') else 'unavailable'
            note = '選定地緣政治系列；僅參考、不計入分數；取得時間不是報價發生時間'
            observed = None
        if key == 'pizza':
            n = sum(1 for s in v or [] if s.get('busyness') is not None and s.get('is_open'))
            status = 'available' if n else 'unavailable'
            note = f'{n} 店有即時人流；未觀測不等同已打烊'
            observed = (data.get('defcon_details') or {}).get('at_time')
        if key == 'news' and isinstance(data.get('news_sampling'), dict):
            samples = data['news_sampling'].get('by_region') or {}
            fresh = sum(r.get('status') == 'available' for r in samples.values() if isinstance(r, dict))
            status = 'available' if fresh == 5 else 'partial' if fresh else 'stale' if v else 'unavailable'
            note = f'{fresh}/5 地區取得新資料；舊值不計分'
        if key in (data.get('collection') or {}).get('reused_sources', []):
            note += '；本輪沿用慢資料，未重新查詢，原觀測時間不變'
            from collection_policy import elapsed_hours
            age = elapsed_hours((data.get('collection') or {}).get('slow_attempted_at'), datetime.now(timezone.utc))
            if status in ('available', 'partial') and (age is None or age >= 6):
                status = 'stale'
        out[key] = {'label':label, 'status':status, 'observed_at':observed, 'note':note}
    return out

