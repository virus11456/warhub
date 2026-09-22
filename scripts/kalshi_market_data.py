"""Offline adapter preparation. Not connected to collection or public display.

Actual API use, storage and redistribution await written data-use authorization.
All tests use synthetic fixtures. No network or account access exists here.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import re


def number(value, maximum=None):
    if value is None or isinstance(value, bool):
        return None
    try:
        d=Decimal(str(value))
        if not d.is_finite() or d < 0 or (maximum is not None and d > maximum):
            return None
        result = float(d)
        return result if math.isfinite(result) else None
    except (InvalidOperation, ValueError):
        return None


def timestamp(value):
    try:
        dt=datetime.fromisoformat(value.replace('Z','+00:00'))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except (ValueError, AttributeError, TypeError):
        return None


def normalize(market, fetched_at):
    fetched=timestamp(fetched_at)
    if fetched is None:
        raise ValueError('Timezone-aware retrieval time required')
    ticker=market.get('ticker')
    if not isinstance(ticker,str) or not re.fullmatch(r'[A-Z0-9_.-]+',ticker):
        raise ValueError('Invalid ticker')
    if market.get('market_type') != 'binary':
        raise ValueError('Only binary contracts are supported')
    end=timestamp(market.get('close_time'))
    bid,ask=(number(market.get(key),1) for key in ('yes_bid_dollars','yes_ask_dollars'))
    bid_size,ask_size=(number(market.get(key)) for key in ('yes_bid_size_fp','yes_ask_size_fp'))
    # Preserve all prices including zero, but zero/missing book size is no quote.
    two_sided=bid is not None and ask is not None and bid<=ask and bid_size is not None and ask_size is not None and bid_size>0 and ask_size>0
    active=market.get('status')=='active' and end is not None and end>fetched
    rules={k:market.get(k) for k in ('title','subtitle','yes_sub_title','no_sub_title','rules_primary','rules_secondary','close_time','expected_expiration_time','latest_expiration_time','can_close_early')}
    fingerprint=hashlib.sha256(json.dumps(rules,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return {'provider':'kalshi','id':f'kalshi:{ticker}','ticker':ticker,
            'event_ticker':market.get('event_ticker'),'question':market.get('title'),
            'question_zh':None,'question_en':market.get('title'),
            'fetched_at':fetched.isoformat(),'source_updated_at':market.get('updated_time'),
            'quote_observed_at':None, # updated_time is not proven to be last quote time.
            'end_date':market.get('close_time'),'rules':rules,'rules_fingerprint':fingerprint,
            'status':market.get('status'),'yes_bid':bid,'yes_ask':ask,
            'yes_bid_size':bid_size,'yes_ask_size':ask_size,
            'last_price':number(market.get('last_price_dollars'),1),
            'volume_contracts':number(market.get('volume_fp')),
            'volume_24h_contracts':number(market.get('volume_24h_fp')),
            'quote_status':'two_sided' if active and two_sided else 'unavailable',
            'display_midpoint':round((bid+ask)/2,6) if active and two_sided else None,
            'spread':round(ask-bid,6) if active and two_sided else None,
            'price_basis':'bid_ask_midpoint' if active and two_sided else None}


def reviewed_pair(left, right, review):
    """Require explicit equivalent-contract review; matching titles are insufficient."""
    if left.get('provider')==right.get('provider'):
        return False
    if review.get('status')!='equivalent' or not review.get('evidence') or not timestamp(review.get('reviewed_at')):
        return False
    expected=review.get('contracts',{})
    for market in (left,right):
        if not market.get('id') or not market.get('rules_fingerprint') or expected.get(market['id'])!=market['rules_fingerprint']:
            return False
    # Semantic event deadline is adjudicated separately from exchange close time.
    return bool(review.get('event_definition') and timestamp(review.get('event_deadline'))
                and review.get('same_resolution_criteria') is True and review.get('same_yes_direction') is True)



def select_markets(markets, fetched_at):
    """Offline equivalent of Polymarket topic selection on normalized binary data.

    No cross-platform pairing is required. Kalshi quote validity remains separate
    because its bid/ask fields are not Polymarket outcomePrices.
    """
    from market_selection import selected_market_risk
    from scoring import PEACE
    selected = []
    seen = set()
    for raw in markets:
        if not isinstance(raw, dict):
            continue
        try:
            item = normalize(raw, fetched_at)
        except (ValueError, TypeError):
            continue
        if item['id'] in seen or item['display_midpoint'] is None:
            continue
        candidate = {'question': item['question'],
                     'yes_price': item['display_midpoint'], 'end_date': item['end_date']}
        if selected_market_risk(candidate) is None:
            continue
        seen.add(item['id'])
        item['event_direction'] = 'deescalation' if PEACE.search(item['question']) else 'escalation'
        selected.append(item)
    return selected
