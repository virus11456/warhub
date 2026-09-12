"""Official ROC Air Force daily reports, keyed by the observation end date."""
import re
import logging
import statistics
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, parse_qs

LIST_URL = 'https://air.mnd.gov.tw/TW/News/News_List.aspx?CID=213'
TZ = timezone(timedelta(hours=8))

class Document(HTMLParser):
    def __init__(self):
        super().__init__(); self.text = []; self.links = []
    def handle_data(self, data):
        self.text.append(data)
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.append(dict(attrs).get('href', ''))

def document(html):
    doc = Document(); doc.feed(html); return doc

def official_url(url):
    p = urlparse(url)
    q = parse_qs(p.query)
    return (p.scheme == 'https' and p.netloc == 'air.mnd.gov.tw' and
            p.path == '/TW/News/News_Detail.aspx' and q.get('CID') == ['213'] and
            len(q.get('ID', [])) == 1 and q['ID'][0].isdigit())

def report_links(html):
    return list(dict.fromkeys(urljoin(LIST_URL, h) for h in document(html).links
                             if official_url(urljoin(LIST_URL, h))))[:12]

def parse_report(html, url, checked_at):
    if not official_url(url):
        raise ValueError('untrusted_report_url')
    text = ''.join(document(html).text)
    text = re.sub(r'\s+', '', text)
    title = re.search(r'中共解放軍臺海周邊海、空域動態[（(](\d{2,3})年(\d{1,2})月(\d{1,2})日[）)]', text)
    period = re.search(r'一、日期：中華民國(\d{2,3})年(\d{1,2})月(\d{1,2})日（[^）]+）(\d{4})時至(\d{2,3})年(\d{1,2})月(\d{1,2})日（[^）]+）(\d{4})時止', text)
    count = re.search(r'二、活動動態：迄0600時止，偵獲共機(\d{1,3})架(?:次)?(?=[（、，。])', text)
    activity_start = re.search(r'二、活動動態：迄0600時止，偵獲', text)
    explicit_zero = '上述期間未偵獲共機' in text
    if not (title and period and activity_start and (count or explicit_zero)):
        raise ValueError('incomplete_daily_report')
    def stamp(g):
        y,m,d,t = g
        return datetime(int(y)+1911,int(m),int(d),int(t[:2]),int(t[2:]),tzinfo=TZ)
    start,end = stamp(period.groups()[:4]),stamp(period.groups()[4:])
    date = end.date().isoformat()
    if (end-start != timedelta(days=1) or start.hour != 6 or start.minute != 0 or
            date != datetime(int(title[1])+1911,int(title[2]),int(title[3])).date().isoformat() or
            end > datetime.fromisoformat(checked_at)):
        raise ValueError('invalid_observation_period')
    activity = text[activity_start.start():].split('國軍運用',1)[0]
    aircraft = int(count[1]) if count else 0
    if aircraft > 300:
        raise ValueError('implausible_aircraft_count')
    def number(pattern):
        m = re.search(pattern,activity); return int(m[1]) if m else None
    subset = number(r'（[^）]*?(\d{1,3})架(?:次)?）')
    if subset is not None and subset > aircraft:
        raise ValueError('subset_exceeds_total')
    return date, dict(aircraft=aircraft, ships=number(r'共艦(\d{1,3})艘'),
        government_ships=number(r'公務船(\d{1,3})艘'), area_aircraft=subset,
        area_description=(re.search(r'（([^）]+)）',activity).group(1)
                          if re.search(r'（([^）]+)）',activity) else None),
        period_start=start.isoformat(), period_end=end.isoformat(),
        source_url=url, source_title=title[0], verified=True,
        source_kind='mnd_daily_report', date_basis='period_end', checked_at=checked_at)

def is_official(row):
    return (row.get('source_kind') == 'mnd_daily_report' and row.get('verified') is True
            and official_url(row.get('source_url','')) and isinstance(row.get('aircraft'),int)
            and not isinstance(row.get('aircraft'),bool) and 0 <= row['aircraft'] <= 300
            and row.get('date_basis') == 'period_end')

def view(days):
    series = [{'date':d,**v} for d,v in sorted(days.items()) if is_official(v)]
    return {'days':series, 'latest':series[-1] if series else None,
            'baseline':statistics.median([v['aircraft'] for v in series]) if series else None,
            'updated_at':max((v['checked_at'] for v in series),default=None),
            'note':'國防部／空軍官方日報；日期為統計截止日，前日06:00至當日06:00（台灣時間）；架次非不同飛機數。缺報不作零。'}

async def collect(session, history, now):
    import aiohttp
    days = dict(history.get('days') or {})
    # Retain old estimates for audit, but never mix them into the official series.
    legacy = dict(history.get('unverified_days') or {})
    for d,row in list(days.items()):
        if not is_official(row):
            legacy.setdefault(d,row); del days[d]
    try:
        async with session.get(LIST_URL,timeout=aiohttp.ClientTimeout(total=20)) as r:
            r.raise_for_status(); links = report_links(await r.text())
        known = {v['source_url']:v for v in days.values()}
        pending = []
        for link in links:
            row = known.get(link)
            if row is None or (link == links[0] and
                (now-datetime.fromisoformat(row['checked_at'])).total_seconds() >= 21600):
                pending.append(link)
        # Latest report first, bounded backfill; existing two-hour collection cadence.
        for link in pending[:3]:
            try:
                async with session.get(link,timeout=aiohttp.ClientTimeout(total=15)) as r:
                    r.raise_for_status(); raw = await r.text()
                date,row = parse_report(raw,link,now.isoformat())
                days[date] = row
            except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
                logging.warning('Official PLA report unavailable: %s', type(exc).__name__)
    except (aiohttp.ClientError, TimeoutError, ValueError, KeyError, TypeError) as exc:
        logging.warning('Official PLA list unavailable: %s', type(exc).__name__)  # Preserve source timestamps and known observations on failure.
    cutoff = (now.astimezone(TZ)-timedelta(days=30)).date().isoformat()
    return {'days':{d:v for d,v in days.items() if d>=cutoff}, 'unverified_days':legacy}
