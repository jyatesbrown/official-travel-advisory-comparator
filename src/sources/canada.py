"""Government of Canada adapter using the official travel.gc.ca JSON data feed."""

from __future__ import annotations

import re
from typing import Any, ClassVar

import httpx
from bs4 import BeautifulSoup, NavigableString, Tag

from ..destinations.resolver import Destination
from ..models.input import SourceCode
from ..models.output import NativeScale, RegionalWarning, SourceAdvisory
from ..normalization.risks import map_labels
from ..normalization.severity import CA_PHRASES, canada_state_to_severity, match_phrase, summarize
from ..utils.dates import parse_canada_friendly_date, to_iso, utc_now
from ..utils.errors import ErrorCode, SourceError
from ..utils.http import FetchTrace, fetch, parse_json_body
from ..utils.text import clean, element_text
from .base import SourceAdapter, log, regional_output

API_URL = "https://data.international.gc.ca/travel-voyage/cta-cap-{code}.json"
WEB_URL = "https://travel.gc.ca/destinations/{slug}"
_REGIONAL_SUFFIX = re.compile(r"\s*\(with regional advisor(?:y|ies)\)\s*$", re.IGNORECASE)


def _own_text(li: Tag) -> str:
    """Text of a list item excluding nested sub-lists (which are emitted separately)."""
    pieces = [
        str(s)
        for s in li.find_all(string=True)
        if isinstance(s, NavigableString) and s.find_parent(["ul", "ol"]) is li.parent
    ]
    return clean("".join(pieces))


def extract_regional(advisories_html: str, *, iso2: str) -> list[RegionalWarning] | None:
    """Return regional warnings, or None when the expected container structure is absent."""
    soup = BeautifulSoup(advisories_html, "lxml")
    containers = soup.select("div.AdvisoryContainer")
    if not containers:
        return None
    warnings: list[RegionalWarning] = []
    for container in containers[1:]:
        heading = container.find("h3")
        head_text = element_text(heading) if heading else ""
        region, separator, advice = head_text.rpartition(" - ")
        severity = match_phrase(advice, CA_PHRASES) if separator else None
        if severity is None:
            log.warning("Canada %s: unrecognised regional heading %r", iso2, head_text)
            continue
        details = [t for p in container.find_all("p") if (t := element_text(p))]
        details += [t for li in container.find_all("li") if (t := _own_text(li))]
        warnings.append(
            RegionalWarning(
                region=region.strip(),
                native_advice=advice.strip(),
                normalized_severity=severity,
                native_details=list(dict.fromkeys(details)),
            )
        )
    return warnings


def extract_risk_labels(security_html: str) -> list[str]:
    soup = BeautifulSoup(security_html or "", "lxml")
    return [t for h in soup.find_all(["h2", "h3", "h4"]) if (t := element_text(h))]


NATIVE_SCALE = NativeScale(
    type="categorical",
    description=(
        "Government of Canada uses named advisory categories rather than numbered levels: 'Take normal "
        "security precautions', 'Exercise a high degree of caution', 'Avoid non-essential travel', "
        "'Avoid all travel'. nativeLevel 'advisory-state N' is an internal feed code, not a public level."
    ),
)
REGIONAL_UNAVAILABLE_NOTE = (
    "Regional advisory detail could not be read from the Government of Canada data for this destination."
)


def build_advisory(doc: Any, *, destination: Destination, include_regional: bool) -> SourceAdvisory:
    data = doc.get("data") if isinstance(doc, dict) else None
    eng = data.get("eng") if isinstance(data, dict) else None
    if not isinstance(data, dict) or not isinstance(eng, dict):
        raise SourceError(ErrorCode.UNEXPECTED_SOURCE_FORMAT, f"Canada {destination.iso2}: data/eng missing")
    if str(data.get("country-iso", "")).upper() != destination.iso2:
        raise SourceError(
            ErrorCode.UNEXPECTED_SOURCE_FORMAT,
            f"Canada {destination.iso2}: document is for {data.get('country-iso')!r}",
        )
    state = data.get("advisory-state")
    advisory_text = clean(eng.get("advisory-text"))
    if not isinstance(state, int) or canada_state_to_severity(state) is None or not advisory_text:
        raise SourceError(
            ErrorCode.UNEXPECTED_SOURCE_FORMAT,
            f"Canada {destination.iso2}: advisory-state={state!r} advisory-text={advisory_text!r}",
        )
    native_advice = _REGIONAL_SUFFIX.sub("", advisory_text)
    from_state = canada_state_to_severity(state)
    from_text = match_phrase(native_advice, CA_PHRASES)
    if from_text is not None and from_text != from_state:
        raise SourceError(
            ErrorCode.UNEXPECTED_SOURCE_FORMAT,
            f"Canada {destination.iso2}: advisory-state {state} contradicts text {native_advice!r}",
        )
    if from_text is None:
        log.warning("Canada %s: unrecognised advisory text %r; using advisory-state", destination.iso2, native_advice)

    has_regional = data.get("has-regional-advisory")
    parsed = extract_regional(str(eng.get("advisories") or ""), iso2=destination.iso2)
    regional = parsed or []
    coverage = "available"
    if parsed is None:
        log.warning("Canada %s: advisories HTML has no AdvisoryContainer blocks", destination.iso2)
        coverage = "unavailable"
    elif not regional and has_regional != 0:
        if has_regional == 1:
            log.warning("Canada %s: has-regional-advisory=1 but no regional blocks parsed", destination.iso2)
        coverage = "unavailable"

    categories, native_labels = map_labels(
        extract_risk_labels(str(eng.get("security") or "")), unmatched_as_other=False
    )
    severity = summarize(
        from_state,
        [w.normalized_severity for w in regional],
        regional_indicated=has_regional == 1 if has_regional in (0, 1) and coverage == "available" else None,
        basis=f"Mapped from Government of Canada risk level '{native_advice}' (advisory-state {state})",
    )
    slug = clean(eng.get("url-slug"))
    return SourceAdvisory(
        source_code="CA",
        source_name=CanadaAdapter.name,
        source_url=WEB_URL.format(slug=slug) if slug else "https://travel.gc.ca/travelling/advisories",
        retrieval_url=API_URL.format(code=destination.iso2.lower()),
        retrieved_at=to_iso(utc_now()),
        source_updated_at=parse_canada_friendly_date(eng.get("friendly-date")),
        native_level=f"advisory-state {state}",
        native_advice=native_advice,
        native_scale=NATIVE_SCALE,
        normalized_severity=severity,
        risk_categories=categories,
        native_risk_labels=native_labels,
        risk_categories_basis=(
            "Section headings of the travel.gc.ca 'Safety and security' section that match the vocabulary."
        ),
        **regional_output(
            include_regional, coverage, regional, REGIONAL_UNAVAILABLE_NOTE if coverage != "available" else None
        ),
    )


class CanadaAdapter(SourceAdapter):
    code: ClassVar[SourceCode] = "CA"
    name: ClassVar[str] = "Government of Canada"

    async def fetch_advisory(
        self,
        destination: Destination,
        client: httpx.AsyncClient,
        *,
        include_regional: bool = True,
        trace: FetchTrace | None = None,
    ) -> SourceAdvisory:
        url = API_URL.format(code=destination.iso2.lower())
        response = await fetch(client, url, accept="application/json", trace=trace)
        doc = parse_json_body(response.text, url=url)
        return build_advisory(doc, destination=destination, include_regional=include_regional)
