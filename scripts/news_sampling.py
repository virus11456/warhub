"""Regional RSS samples, not global news volume or verified independent events."""
import hashlib
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

QUERIES = {
    'ukraine': '(Ukraine OR Russia OR Kyiv) (war OR military OR ceasefire OR missile)',
    'mideast': '(Iran OR Israel OR Gaza OR Lebanon) (war OR military OR ceasefire OR missile)',
    # 2026-10-08: widened after live RSS gave ~5 items/24h; place names plus drills/warship/coast guard (~21/24h).
    'taiwan': ('(Taiwan OR "Taiwan Strait" OR Taipei OR Kinmen OR Matsu) '
               '(military OR exercise OR drills OR blockade OR aircraft OR warship OR "coast guard" OR invasion OR defense)'),
    'korea': '("North Korea" OR "South Korea") (military OR missile OR nuclear OR exercise)',
    'southsea': '("South China Sea" OR Philippines OR Scarborough) (military OR coast guard OR clash)',
}
TOPICS = dict(zip(QUERIES, ('俄烏', '中東', '台海', '朝鮮', '南海')))


def stamp(value):
    try:
        d = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return d if d.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def title_key(title):
    return re.sub(r'[^\w]', '', title.casefold())


def parse_rss(raw, region, now):
    from email.utils import parsedate_to_datetime
    root = ET.fromstring(raw)
    if root.tag != 'rss' or root.find('channel') is None:
        raise ValueError('invalid_rss')
    items, valid_items = [], 0
    nodes = root.findall('./channel/item')
    for node in nodes:
        title, url = (node.findtext('title') or '').strip(), (node.findtext('link') or '').strip()
        source = (node.findtext('source') or '').strip()
        if not title or urlsplit(url).scheme not in ('http', 'https') or not urlsplit(url).netloc:
            continue
        try:
            published = parsedate_to_datetime(node.findtext('pubDate'))
            if published.tzinfo is None:
                continue
            published = published.astimezone(timezone.utc)
        except (ValueError, TypeError, AttributeError, OverflowError):
            continue
        valid_items += 1
        if not now - timedelta(days=7) <= published <= now + timedelta(minutes=5):
            continue
        if source and title.endswith(' - ' + source):
            title = title[:-(len(source) + 3)].strip()
        items.append({'title': title, 'url': url, 'domain': source, 'ts': published.isoformat(),
                      'topic': TOPICS[region], 'region': region})
    if nodes and not valid_items:
        raise ValueError('no_valid_items')
    result, links, titles = [], set(), set()
    for item in sorted(items, key=lambda r: r['ts'], reverse=True):
        key = title_key(item['title'])
        if item['url'] in links or key in titles:
            continue
        links.add(item['url']); titles.add(key); result.append(item)
        if len(result) == 50:
            break
    return result


def merge_samples(previous, batches, now):
    """Keep original first-seen/publication times; failed queries are not zero."""
    result = {'version': 1, 'method': 'regional-rss-v1', 'by_region': {}}
    for key in QUERIES:
        old = (previous.get('by_region') or {}).get(key) or {}
        batch = batches.get(key) or {'status': 'unavailable', 'items': []}
        rows = {}
        for item in old.get('records') or []:
            published = stamp(item.get('ts'))
            if published and now - timedelta(days=90) <= published <= now:
                rows[item['sample_id']] = dict(item)
        for item in batch['items']:
            identity = hashlib.sha256(item['url'].encode()).hexdigest()
            existing = rows.get(identity)
            if existing:
                continue
            rows[identity] = {**item, 'sample_id': identity, 'first_seen_at': now.isoformat()}
        records = sorted(rows.values(), key=lambda r: (r['ts'], r['sample_id']), reverse=True)
        recent = [r for r in records if stamp(r['ts']) >= now - timedelta(hours=24)]
        success = batch['status'] == 'available'
        result['by_region'][key] = {
            'status': batch['status'], 'attempted_at': now.isoformat(),
            'observed_at': now.isoformat() if success else old.get('observed_at'),
            'records': records, 'sample_24h': len(recent) if success else None,
            'source_names_24h': len({r['domain'] for r in recent if r.get('domain')}) if success else None,
            'baseline_status': 'not_scored',
        }
    return result


def headlines(sampling, now):
    """Balanced small display; archived originals are never mutated by translation."""
    selected, urls, titles = [], set(), set()
    for key in QUERIES:
        region = sampling['by_region'][key]
        count = 0
        for row in region['records']:
            if stamp(row['ts']) < now - timedelta(days=7):
                continue
            identity = title_key(row['title'])
            if row['url'] in urls or identity in titles:
                continue
            selected.append({**row, 'stale': region['status'] != 'available'})
            urls.add(row['url']); titles.add(identity); count += 1
            if count >= 3:
                break
    return sorted(selected, key=lambda r: r['ts'], reverse=True)
