from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone

_CA_TIMEZONES = {"EDT": -4, "EST": -5}
_CA_FRIENDLY = re.compile(r"^(?P<date>[A-Z][a-z]+ \d{1,2}, \d{4}) (?P<time>\d{1,2}:\d{2}) (?P<tz>[A-Z]{3,4})$")


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_iso(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return to_iso(parsed)


def parse_rss_date(value: str | None) -> str | None:
    """Parse an RSS pubDate. A date-only value is returned as a date-only ISO string."""
    if not value:
        return None
    value = value.strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M %z"):
        try:
            return to_iso(datetime.strptime(value, fmt))
        except ValueError:
            continue
    for fmt in ("%a, %d %b %Y", "%d %b %Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_canada_friendly_date(value: str | None) -> str | None:
    """Parse travel.gc.ca dates such as "October 6, 2026 14:51 EDT"."""
    if not value:
        return None
    match = _CA_FRIENDLY.match(value.strip())
    if not match or match["tz"] not in _CA_TIMEZONES:
        return None
    try:
        naive = datetime.strptime(f"{match['date']} {match['time']}", "%B %d, %Y %H:%M")
    except ValueError:
        return None
    offset = timezone(timedelta(hours=_CA_TIMEZONES[match["tz"]]))
    return to_iso(naive.replace(tzinfo=offset))
