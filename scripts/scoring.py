"""Versioned, deterministic observation index. Not a calibrated war probability."""
import math
import re
from datetime import datetime, timezone

MODEL_VERSION = 'wpi-4.0'
WEIGHTS = {'p': .28, 'a': .18, 'g': .10, 'z': .14, 'f': .10, 's': .12, 'w': .08}
ACTION = re.compile(r'\b(war|wars|ceasefire|truce|peace (?:deal|agreement)|airstrikes?|strikes?|attacks?|invad\w*|invasion|blockad\w*|military|missiles?|nuclear (?:test|weapon|strike)|troops?|offensive|clashes?|conflicts?|annex\w*)\b', re.I)
EXCLUDE = re.compile(r'\b(fifa|nba|nfl|mlb|nhl|esports|counter.strike|box office|grammy|oscar|world cup|super bowl|fed|interest rate|rate cuts?|election|president|prime minister)\b', re.I)
PEACE = re.compile(r'\b(ceasefire|truce|peace (?:deal|agreement)|normalization)\b', re.I)

def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

def clamp(value):
    return max(0., min(100., value))

def market_risk(market):
    """Conservative title-only relevance and binary outcomes; unknown semantics excluded."""
    q = market.get('question') or ''
    yes = market.get('yes_price')
    if not ACTION.search(q) or EXCLUDE.search(q) or not number(yes) or not 0 <= yes <= 1:
        return None
    # Negated questions need manual interpretation, never invert them heuristically.
    if re.search(r"\b(not|no|avoid|prevent|end|ends|ending|lift|lifts|lifting|withdraw|withdrawal|resume|resumes|break|breaks|violate|violation)\b", q, re.I):
        return None
    end = market.get('end_date')
    if end:
        try:
            if datetime.fromisoformat(end.replace('Z', '+00:00')) <= datetime.now(timezone.utc):
                return None
        except (ValueError, TypeError):
            return None
    return (1 - yes if PEACE.search(q) else yes) * 100

def market_average(markets):
    points = [(market_risk(m), m.get('volume', 0)) for m in markets]
    points = [(v, w) for v, w in points if v is not None and number(w) and w > 0]
    return sum(v*w for v,w in points)/sum(w for _,w in points) if points else None

def aggregate(factors, weights=WEIGHTS, min_coverage=.60, min_factors=3):
    valid = {k: clamp(v) for k,v in factors.items() if k in weights and number(v)}
    coverage = sum(weights[k] for k in valid)
    score = round(sum(valid[k]*weights[k] for k in valid)/coverage, 1) if coverage >= min_coverage and len(valid) >= min_factors else None
    return score, round(coverage, 2)

def calculate_wpi(pizza_index, markets, aviation=None, firms=None, gdelt=None, wikipedia=None, finance=None):
    a, f, g, w, fin = aviation or {}, firms or {}, gdelt or {}, wikipedia or {}, finance or {}
    factors = dict.fromkeys(WEIGHTS)
    factors['p'] = market_average(markets)
    factors['z'] = pizza_index if number(pizza_index) else None
    # A is a measured 7-day change, never the composition of the current fleet.
    ap = (a.get('summary') or {}).get('anomaly_pct')
    if not a.get('error') and number(ap): factors['a'] = clamp(ap / 2)
    # Global fires do not identify conflict. Keep F unavailable until a validated regional baseline exists.
    gv = [clamp(v['latest']*25) for v in g.values() if not v.get('stale') and number(v.get('latest'))]
    factors['g'] = sum(gv)/len(gv) if gv else None
    factors['w'] = w.get('score') if not w.get('stale') else None
    sv = []
    for ticker, mult in [('^VIX',1), ('GC=F',2), ('BZ=F',1.5), ('USDCHF=X',-3), ('ZW=F',1.5)]:
        dev = (fin.get(ticker) or {}).get('dev')
        if number(dev): sv.append(clamp(50+dev*mult))
    factors['s'] = sum(sv)/len(sv) if len(sv) >= 3 else None
    score, coverage = aggregate(factors)
    level = 'INSUFFICIENT_DATA' if score is None else ('CRITICAL' if score>=80 else 'HIGH' if score>=65 else 'ELEVATED' if score>=45 else 'MODERATE' if score>=25 else 'LOW')
    return {'model_version': MODEL_VERSION, 'combined_score': score, 'alert_level': level,
            'pizza_score': factors['z'], 'polymarket_score': factors['p'],
            'factors': {k: round(v,2) if number(v) else None for k,v in factors.items()},
            'coverage': coverage, 'is_probability': False, 'experimental': True}


def risk_off_cluster(finance):
    """Six observed price-deviation signals; missing inputs never mean inactive."""
    def signal(symbol, direction=1):
        value = (finance.get(symbol) or {}).get('dev')
        return value * direction >= 5 if number(value) else None
    signals = {key: signal(symbol, direction) for key, symbol, direction in (
        ('gold', 'GC=F', 1), ('oil', 'BZ=F', 1), ('vix', '^VIX', 1),
        ('chf', 'USDCHF=X', -1), ('treasury', '^TNX', -1))}
    defense = [signal(symbol) for symbol in ('LMT', 'RTX', 'NOC', 'GD')]
    signals['defense'] = True if any(value is True for value in defense) else (
        False if all(value is False for value in defense) else None)
    observed = sum(value is not None for value in signals.values())
    return {'risk_off_cluster': sum(value is True for value in signals.values()) if observed == 6 else None,
            'risk_off_observed': observed, 'risk_off_signals': signals}
