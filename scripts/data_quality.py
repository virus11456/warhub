"""Public source status. Fetch time is not a claim about observation freshness."""
from datetime import datetime, timezone

LABELS = {'kalshi':'Kalshi', 'pizza':'BestTime 披薩', 'polymarket':'Polymarket', 'aviation':'ADS-B', 'firms':'NASA FIRMS',
          'gdelt':'GDELT', 'notams':'FAA NOTAM', 'wikipedia':'Wikipedia', 'news':'Google News',
          'tw_news':'台海新聞', 'nuclear_seismic':'USGS', 'eonet':'NASA EONET', 'finance':'Yahoo Finance',
          'food':'Comtrade 糧食', 'strat':'Comtrade 物資', 'usda':'USDA ESR', 'bars':'BestTime', 'fred':'FRED'}

def _oldest_observed(records):
    """Oldest observation among fresh records: the conservative age of a multi-region source."""
    stamps = []
    for r in records:
        if not isinstance(r, dict) or r.get('stale') or r.get('available') is False:
            continue
        try:
            at = datetime.fromisoformat(str(r.get('observed_at')).replace('Z', '+00:00'))
            stamps.append((at if at.tzinfo else at.replace(tzinfo=timezone.utc), r['observed_at']))
        except (ValueError, KeyError):
            continue
    return min(stamps)[1] if stamps else None


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
                if key == 'gdelt':
                    events = (data.get('gdelt_events') or {}).get('regions') or {}
                    doc_fresh = {k for k, r in v.items() if isinstance(r, dict) and not r.get('stale')}
                    backup = [k for k, r in events.items() if k not in doc_fresh and isinstance(r, dict)
                              and not r.get('stale') and r.get('score') is not None]
                    n = len(doc_fresh) + len(backup)
                    status = 'available' if n == 5 else ('partial' if n else status)
                    note = f'{n}/5 地區有新聞強度'
                    if backup:
                        label = 'GDELT（事件檔備援）'
                        note += f'；{len(backup)} 區用事件檔，與原 API 定義不同'
                    elif any(r.get('reason') == 'baseline_accumulating' for r in events.values() if isinstance(r, dict) and not r.get('stale')):
                        note += '；原 API 限流，事件檔基準累積中'
                    else:
                        note += '；舊值不計分'
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
        reused = key in (data.get('collection') or {}).get('reused_sources', [])
        if key in ('food', 'strat') and isinstance(v, dict) and v.get('cache_reused_at') and not reused:
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
            summary = data.get('pizza_summary') or {}
            state = summary.get('state')
            n = summary.get('live_count') or 0
            if state == 'setup_needed':
                # A known configuration step, not an outage: keeps the owner outage alert quiet.
                status, note = 'not_configured', '尚未建檔（需手動執行 BestTime 建檔）'
            elif state == 'off_hours':
                status, note = 'waiting', '非下班時段（僅美東 16–24 時查詢）'
            else:
                status = 'available' if n else 'unavailable'
                note = f'{n}/{summary.get("total") or len(v or [])} 店有即時人流；未觀測不等同已打烊'
            observed = summary.get('queried_at') if n else None
        if key == 'news' and isinstance(data.get('news_sampling'), dict):
            samples = data['news_sampling'].get('by_region') or {}
            fresh = sum(r.get('status') == 'available' for r in samples.values() if isinstance(r, dict))
            status = 'available' if fresh == 5 else 'partial' if fresh else 'stale' if v else 'unavailable'
            note = f'{fresh}/5 地區取得新資料；舊值不計分'
        if key == 'bars' and isinstance(v, dict) and v.get('available') is False and v.get('off_hours'):
            status = 'waiting'  # 尚未到美東 16–24 時查詢窗口：排程內等待，不是故障
        if reused:
            note += '；本輪沿用慢資料，未重新查詢，原觀測時間不變'
            from collection_policy import elapsed_hours
            age = elapsed_hours((data.get('collection') or {}).get('slow_attempted_at'), datetime.now(timezone.utc))
            if status in ('available', 'partial') and (age is None or age >= 6):
                status = 'stale'
        if observed is None and isinstance(v, dict) and key in ('gdelt', 'notams', 'finance'):
            observed = _oldest_observed(v.values())
        fetched = None
        if status not in ('unavailable', 'waiting') and not reused:
            fetched = (v.get('fetched_at') if key == 'kalshi' and isinstance(v, dict) else None) or data.get('updated_at')
        out[key] = {'label':label, 'status':status, 'observed_at':observed, 'fetched_at':fetched, 'note':note}
    return out

