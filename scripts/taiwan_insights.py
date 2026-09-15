"""Bounded Taiwan observation history and descriptive cross-source views; no I/O."""
from datetime import datetime, timedelta, timezone
import json
import math
import re
import statistics
from urllib.parse import urlparse
from pla_official import is_official
from scoring import number, market_risk


def timestamp(value):
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except (AttributeError, TypeError, ValueError):
        return None


def safe_url(value):
    try:
        parsed = urlparse(value or '')
        return value if parsed.scheme == 'https' and parsed.netloc and not parsed.username else None
    except ValueError:
        return None


def market_key(row):
    return json.dumps([row['id'], row['question'], row['end_date']], ensure_ascii=False)


def build(snapshot, previous=None):
    now = timestamp(snapshot.get('updated_at'))
    if now is None:
        raise ValueError('insight snapshot timestamp required')
    cutoff = now - timedelta(days=7)
    previous = previous or {}
    observations = []
    for row in previous.get('market_observations', []):
        at = timestamp(row.get('at')) if isinstance(row, dict) else None
        if at and cutoff <= at < now and isinstance(row.get('markets'), list):
            observations.append(row)
    current_markets = []
    for market in snapshot.get('polymarket') or []:
        end = timestamp(market.get('end_date'))
        if (market.get('stale') or not market.get('id') or not market.get('slug') or
                not re.search(r'\b(taiwan|taipei)\b', market.get('question', ''), re.I) or
                end is None or end <= now or market_risk({**market, "end_date": None}) is None):
            continue
        current_markets.append({k: market.get(k) for k in
            ('id', 'question', 'question_zh', 'end_date', 'yes_price', 'volume', 'slug')})
    current_markets.sort(key=lambda m: -(m['volume'] if number(m['volume']) else 0))
    current_markets = current_markets[:8]
    observations.append({'at': now.isoformat(), 'markets': current_markets})
    observations = sorted({row['at']: row for row in observations}.values(), key=lambda r: r['at'])[-100:]
    market_views = []
    for market in current_markets[:3]:
        candidates = []
        for observation in observations:
            at = timestamp(observation['at'])
            distance = abs((at - (now - timedelta(hours=24))).total_seconds())
            if distance > 4 * 3600:
                continue
            for old in observation['markets']:
                if (all(k in old for k in ('id', 'question', 'end_date')) and market_key(old) == market_key(market)
                        and number(old.get('yes_price')) and 0 <= old['yes_price'] <= 1):
                    candidates.append((distance, at, old))
        best = min(candidates, key=lambda x: x[0]) if candidates else None
        market_views.append({**market, 'yes_percent': round(market['yes_price'] * 100, 2),
            'delta_pp': round((market['yes_price'] - best[2]['yes_price']) * 100, 2) if best else None,
            'comparison_at': best[1].isoformat() if best else None,
            'comparison_hours': round((now - best[1]).total_seconds() / 3600, 1) if best else None})

    days = []
    for row in (snapshot.get('pla') or {}).get('days', []):
        end = timestamp(row.get('period_end'))
        if is_official(row) and end and end <= now:
            days.append(row)
    days = sorted({row['date']: row for row in days}.values(), key=lambda r: r['date'])
    latest = days[-1] if days else None
    activity = {'status': 'missing', 'latest': latest, 'baseline_days': 0}
    if latest:
        end = timestamp(latest['period_end'])
        prior = [r['aircraft'] for r in days if end - timedelta(days=28) <= timestamp(r['period_end']) < end]
        activity.update(baseline_days=len(prior), median=statistics.median(prior) if prior else None)
        if now - end > timedelta(hours=48):
            activity['status'] = 'stale'
        elif len(prior) < 14:
            activity['status'] = 'baseline_pending'
        else:
            p90 = sorted(prior)[math.ceil(.9 * len(prior)) - 1]
            activity.update(status='elevated' if latest['aircraft'] > p90 else 'within_baseline',
                            p90=p90, difference=latest['aircraft'] - statistics.median(prior))

    def valid_news(row):
        if not isinstance(row, dict) or not isinstance(row.get('title'), str) or not row['title'].strip():
            return False
        at = timestamp(row.get('ts'))
        return bool(at and cutoff <= at <= now and isinstance(row.get('url'), str) and safe_url(row['url']))

    current_news = snapshot.get('tw_news')
    current_news = current_news if isinstance(current_news, list) else []
    usable_news = [row for row in current_news if valid_news(row)]
    fresh_news = [row for row in usable_news if not row.get('stale')]
    # Describes this input batch, not completeness of the news universe or a new event.
    input_status = ('unavailable' if not usable_news else 'stale' if not fresh_news
                    else 'available' if len(fresh_news) == len(current_news) else 'partial')
    news = {}
    for row in [*(previous.get('news_observations') or []), *current_news]:
        if not valid_news(row):
            continue
        key = re.sub(r'\s+', '', row['title']).casefold()
        if key not in news:
            news[key] = {k: row.get(k) for k in ('title', 'title_zh', 'url', 'domain', 'ts')}
            news[key].update({k: row[k] for k in ('title_en', 'title_english') if k in row})
    news = sorted(news.values(), key=lambda r: timestamp(r['ts']), reverse=True)[:120]
    recent = [r for r in news if timestamp(r['ts']) >= now - timedelta(hours=24)]
    timeline = [{'kind': 'official', 'at': r['period_end'], 'title': f"官方日報：共機 {r['aircraft']} 架次",
                 'title_english': f"Official daily report: {r['aircraft']} PLA aircraft sorties",
                 'url': r['source_url'], 'time_label': '統計截止時間'} for r in days if timestamp(r['period_end']) >= cutoff]
    timeline.extend({'kind': 'news', 'at': r['ts'], 'title': r.get('title_zh') or r['title'],
                     'title_english': r.get('title_english') or r.get('title_en'),
                     'url': r['url'], 'time_label': '新聞發稿時間'} for r in news)
    timeline.sort(key=lambda r: timestamp(r['at']), reverse=True)
    return {'version': 1, 'as_of': now.isoformat(), 'activity': activity, 'markets': market_views,
            'news': {'input_status': input_status,
                     'sample_24h': len(recent), 'publishers_24h': len({r['domain'] for r in recent if r.get('domain')}),
                     'latest_at': news[0]['ts'] if news else None},
            'timeline': timeline[:20], 'market_observations': observations, 'news_observations': news}
