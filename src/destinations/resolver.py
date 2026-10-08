from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from functools import lru_cache

import pycountry

from ..utils.text import normalize_key
from .aliases import ALIASES, AMBIGUOUS, DISPLAY_NAME_OVERRIDES, EXTRA_DESTINATIONS

FUZZY_MIN_LENGTH = 6
FUZZY_MIN_RATIO = 0.92
FUZZY_MIN_MARGIN = 0.05
_CODE_LIKE = re.compile(r"^[A-Za-z]{2,3}$")
_PARENTHETICAL = re.compile(r"\s*\([^)]*\)")


@dataclass(frozen=True)
class Destination:
    name: str
    iso2: str
    iso3: str | None


@dataclass(frozen=True)
class Resolution:
    destination: Destination | None
    method: str | None
    reason: str | None = None
    candidates: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.destination is not None


def _name_variants(name: str) -> set[str]:
    variants = {name, _PARENTHETICAL.sub("", name)}
    if ", " in name:
        head, _, tail = name.partition(", ")
        variants.add(f"{tail} {head}")
    return {normalize_key(v) for v in variants if v.strip()}


class DestinationResolver:
    def __init__(self) -> None:
        self._by_code: dict[str, Destination] = {}
        self._alpha3: dict[str, str] = {}
        names: dict[str, set[str]] = {}

        for country in pycountry.countries:
            iso2 = country.alpha_2
            display = DISPLAY_NAME_OVERRIDES.get(iso2) or getattr(country, "common_name", None) or country.name
            self._by_code[iso2] = Destination(display, iso2, country.alpha_3)
            self._alpha3[country.alpha_3] = iso2
            for raw in (country.name, getattr(country, "common_name", None), getattr(country, "official_name", None)):
                if raw:
                    for key in _name_variants(raw):
                        names.setdefault(key, set()).add(iso2)
        for iso2, (display, iso3) in EXTRA_DESTINATIONS.items():
            self._by_code[iso2] = Destination(display, iso2, iso3)
            if iso3:
                self._alpha3[iso3] = iso2
            names.setdefault(normalize_key(display), set()).add(iso2)
        for iso2, display in DISPLAY_NAME_OVERRIDES.items():
            names.setdefault(normalize_key(display), set()).add(iso2)

        self._names = {key: next(iter(codes)) for key, codes in names.items() if len(codes) == 1}
        self._aliases = dict(ALIASES)
        self._fuzzy_keys = {**self._names, **self._aliases}

    def get(self, iso2: str) -> Destination | None:
        return self._by_code.get(iso2.upper())

    def resolve(self, query: str) -> Resolution:
        key = normalize_key(query or "")
        if not key:
            return Resolution(None, None, reason="empty")
        if key in AMBIGUOUS:
            return Resolution(None, None, reason="ambiguous", candidates=self._names_for(AMBIGUOUS[key]))
        if key in self._aliases:
            return Resolution(self._by_code[self._aliases[key]], "alias")
        if key in self._names:
            return Resolution(self._by_code[self._names[key]], "name")
        stripped = query.strip()
        if _CODE_LIKE.match(stripped):
            code = stripped.upper()
            iso2 = code if len(code) == 2 else self._alpha3.get(code)
            if iso2 and iso2 in self._by_code:
                return Resolution(self._by_code[iso2], "iso_code")
        return self._fuzzy(key)

    def _fuzzy(self, key: str) -> Resolution:
        if len(key) < FUZZY_MIN_LENGTH:
            return Resolution(None, None, reason="not_found")
        scored = sorted(
            ((difflib.SequenceMatcher(None, key, cand).ratio(), cand) for cand in self._fuzzy_keys),
            reverse=True,
        )
        best_ratio, best_key = scored[0]
        if best_ratio < FUZZY_MIN_RATIO:
            return Resolution(None, None, reason="not_found")
        best_iso = self._fuzzy_keys[best_key]
        rivals = [r for r, k in scored[1:] if self._fuzzy_keys[k] != best_iso]
        if rivals and rivals[0] > best_ratio - FUZZY_MIN_MARGIN:
            candidates = {best_iso} | {self._fuzzy_keys[k] for r, k in scored[1:4] if r >= rivals[0]}
            return Resolution(None, None, reason="ambiguous", candidates=self._names_for(tuple(candidates)))
        return Resolution(self._by_code[best_iso], "fuzzy")

    def _names_for(self, codes: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(self._by_code[c].name for c in codes if c in self._by_code))


@lru_cache(maxsize=1)
def get_resolver() -> DestinationResolver:
    return DestinationResolver()
