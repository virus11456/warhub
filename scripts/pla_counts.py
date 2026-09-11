"""Conservative aircraft-count extraction from unverified news headlines."""
import re


def sortie_count(title):
    # Do not truncate 1,200 / 1200 or interpret model IDs such as F-16機 as counts.
    prefix = r'(?<![\d,.，．A-Za-z\-])([0-9]{1,3})\s*'
    explicit = re.findall(prefix + r'架(?:次)?', title)
    # 6機10艦 gives a separate aircraft count; 21機艦 / 21機、艦 does not.
    shorthand = re.findall(prefix + r'機(?!\s*[、，,／/與及和]?\s*[艦舰船])', title)
    values = [int(n) for n in explicit + shorthand if 0 < int(n) <= 300]
    return max(values) if values else None


def usable_days(days):
    """Exclude disproven headline counts, including ones restored from older commits.

    Keep independently verified records and legacy records without source headlines;
    absence of provenance is not evidence that a specific value is incorrect.
    """
    return {date: row for date, row in days.items()
            if row.get('verified') or not row.get('source_title') or
            sortie_count(row['source_title']) == row.get('aircraft')}
