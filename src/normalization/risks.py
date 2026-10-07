"""Controlled risk vocabulary and the deterministic keyword rules that map native labels onto it."""

from __future__ import annotations

import re
from collections.abc import Iterable

RISK_CATEGORIES: tuple[str, ...] = (
    "crime",
    "terrorism",
    "kidnapping",
    "civil_unrest",
    "armed_conflict",
    "arbitrary_detention",
    "health",
    "natural_disaster",
    "border_security",
    "maritime",
    "landmines",
    "wrongful_detention",
    "other",
)

# Ordered: the first matching rule wins, so specific rules precede general ones.
_RULES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (category, re.compile(pattern, re.IGNORECASE))
    for category, pattern in (
        ("wrongful_detention", r"\bwrongful(?:ly)? detain|\bwrongful detention"),
        ("arbitrary_detention", r"\barbitrary (?:detention|arrest|enforcement)|\bexit bans?\b|\bdetention"),
        ("kidnapping", r"\bkidnap|\bhostage"),
        ("terrorism", r"\bterroris"),
        ("landmines", r"\bland ?mines?\b|\bunexploded\b|\bexplosive remnants\b"),
        ("armed_conflict", r"\barmed conflict\b|\bwar\b|\bmilitary\b|\bmissiles?\b|\bdrones?\b|\bconflict\b"),
        (
            "civil_unrest",
            r"\bunrest\b|\bdemonstrations?\b|\bprotests?\b|\bpolitical (?:situation|violence|tension)|\briots?\b",
        ),
        ("maritime", r"\bpiracy\b|\bmaritime\b|\bsea travel\b"),
        ("border_security", r"\bborder"),
        ("health", r"\bhealth\b|\bdiseases?\b|\boutbreaks?\b|\bepidemic|\bcholera\b|\bebola\b"),
        (
            "natural_disaster",
            r"\bnatural disasters?\b|\bearthquakes?\b|\bhurricanes?\b|\btyphoons?\b|\bcyclones?\b|"
            r"\bvolcan|\bfloods?\b|\bflooding\b|\btsunamis?\b|\bwildfires?\b|\bextreme weather\b",
        ),
        ("crime", r"\bcrimes?\b|\bcriminal|\bfraud\b|\bscams?\b|\brobbery\b|\btheft\b|\bgangs?\b"),
    )
)


def categorize(label: str) -> str | None:
    for category, pattern in _RULES:
        if pattern.search(label):
            return category
    return None


def map_labels(labels: Iterable[str], *, unmatched_as_other: bool) -> tuple[list[str], list[str]]:
    """Return (categories in vocabulary order, native labels that contributed)."""
    categories: set[str] = set()
    native: list[str] = []
    for label in labels:
        category = categorize(label)
        if category is None and unmatched_as_other:
            category = "other"
        if category is None:
            continue
        categories.add(category)
        if label not in native:
            native.append(label)
    return [c for c in RISK_CATEGORIES if c in categories], native
