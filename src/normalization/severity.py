"""Deterministic mapping of each government's native advisory wording to a shared 1-4 scale.

1 = normal precautions, 2 = increased caution, 3 = avoid non-essential travel / reconsider travel,
4 = avoid all travel. `None` means the native value could not be mapped confidently.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from ..models.output import NormalizedSeverity

US_LEVEL_ADVICE: dict[int, str] = {
    1: "Exercise Normal Precautions",
    2: "Exercise Increased Caution",
    3: "Reconsider Travel",
    4: "Do Not Travel",
}
US_PHRASES: tuple[tuple[str, int], ...] = (
    ("do not travel", 4),
    ("reconsider travel", 3),
    ("exercise increased caution", 2),
    ("exercise normal precautions", 1),
)
CA_PHRASES: tuple[tuple[str, int], ...] = (
    ("avoid all travel", 4),
    ("avoid non-essential travel", 3),
    ("exercise a high degree of caution", 2),
    ("take normal security precautions", 1),
    ("exercise normal security precautions", 1),
)
UK_PHRASES: tuple[tuple[str, int], ...] = (
    ("advises against all but essential travel", 3),
    ("advises against all travel", 4),
)
UK_WHOLE_COUNTRY_STATUSES: dict[str, int] = {
    "avoid_all_travel_to_whole_country": 4,
    "avoid_all_but_essential_travel_to_whole_country": 3,
}
UK_PARTS_STATUSES: dict[str, int] = {
    "avoid_all_travel_to_parts": 4,
    "avoid_all_but_essential_travel_to_parts": 3,
}


def us_level_to_severity(level: int) -> int | None:
    return level if level in US_LEVEL_ADVICE else None


def canada_state_to_severity(state: int) -> int | None:
    return state + 1 if 0 <= state <= 3 else None


def match_phrase(text: str | None, table: Sequence[tuple[str, int]]) -> int | None:
    """Return the severity of the first phrase in `table` found in `text` (case/dash-insensitive)."""
    if not text:
        return None
    haystack = text.casefold().replace("\u2011", "-").replace("\u2013", "-").replace("\u2010", "-")
    for phrase, severity in table:
        if phrase in haystack:
            return severity
    return None


def uk_overall_from_alert_status(statuses: Iterable[str]) -> int | None:
    statuses = list(statuses)
    whole = [UK_WHOLE_COUNTRY_STATUSES[s] for s in statuses if s in UK_WHOLE_COUNTRY_STATUSES]
    if whole:
        return max(whole)
    if any("whole_country" in s for s in statuses):
        return None
    return 1


def uk_parts_from_alert_status(statuses: Iterable[str]) -> list[int]:
    return [UK_PARTS_STATUSES[s] for s in statuses if s in UK_PARTS_STATUSES]


def summarize(
    overall: int | None,
    regional_values: Iterable[int | None],
    *,
    regional_indicated: bool | None,
    basis: str,
) -> NormalizedSeverity:
    """Combine national and regional severities without letting a regional value overwrite national."""
    values = [v for v in regional_values if v is not None]
    regional_max = max(values) if values else None
    if regional_max is not None and overall is not None:
        escalation: bool | None = regional_max > overall
    elif regional_indicated is False:
        escalation = False
    else:
        escalation = None
    return NormalizedSeverity(
        overall=overall,
        regional_max=regional_max,
        has_regional_escalation=escalation,
        basis=basis,
    )
