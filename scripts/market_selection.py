"""Shared market selection, preserving the existing Polymarket collector policy."""
from scoring import market_risk

EXCLUDE_KEYWORDS = [
    "world cup", "fifa", "olympic", "super bowl", "nba", "nfl", "mlb",
    "premier league", "champions league", "grammy", "oscar", "album",
    "box office", "bitcoin", "ethereum", "eurovision", "tiktok",
    "counter-strike", "esports", "valorant", "dota",
]


def excluded_market_title(question):
    return not isinstance(question, str) or any(word in question.lower() for word in EXCLUDE_KEYWORDS)


def selected_market_risk(candidate):
    """Same exclusion-first selection used by fetch_polymarket.

    This is a topic/validity gate, not evidence of cross-platform equivalence.
    """
    question = candidate.get('question') or ''
    if excluded_market_title(question):
        return None
    return market_risk(candidate)
