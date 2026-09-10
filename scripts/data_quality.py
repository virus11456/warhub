"""Public source status. Fetch time is not a claim about observation freshness."""
from datetime import datetime, timezone

LABELS = {'pizza':'PizzINT', 'polymarket':'Polymarket', 'aviation':'ADS-B', 'firms':'NASA FIRMS',
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
                fresh = [r for r in v.values() if not r.get('stale')]
                status = 'available' if len(fresh)==5 else ('partial' if fresh else 'stale')
                note = f'{len(fresh)}/5 地區取得新資料；舊值不計分'
            if key == 'nuclear_seismic':
                n = sum(s.get('count') is not None for s in v.get('sites',[]))
                status = 'available' if n==5 else 'partial' if n else 'unavailable'
                note = f'{n}/5 測區查詢成功；地震不等於核試驗'
            if key in ('food','strat','usda'):
                items=v.get('items') or []
                if items and not v.get("stale"):
                    fresh=sum(not r.get('incomplete') and not r.get('stale') for r in items)
                    status='available' if fresh==len(items) else 'partial' if fresh else 'unavailable'
                note = '觀測期間：' + str(v.get('ref_month') or v.get('week_ending') or '未知') + '；與抓取時間不同'
        if key == 'pizza':
            n = sum(1 for s in v or [] if s.get('busyness') is not None and s.get('is_open'))
            status = 'available' if n else 'unavailable'
            note = f'{n} 店有即時人流；未觀測不等同已打烊'
            observed = (data.get('defcon_details') or {}).get('at_time')
        out[key] = {'label':label, 'status':status, 'observed_at':observed, 'note':note}
    return out
