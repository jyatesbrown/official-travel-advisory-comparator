"""U.K. FCDO adapter using the GOV.UK Content API (structured JSON for each travel-advice page)."""

from __future__ import annotations

import re
from typing import Any, ClassVar

import httpx
from bs4 import BeautifulSoup, Tag

from ..destinations.resolver import Destination
from ..models.input import SourceCode
from ..models.output import NativeScale, RegionalWarning, SourceAdvisory
from ..normalization.risks import map_labels
from ..normalization.severity import (
    UK_PARTS_STATUSES,
    UK_PHRASES,
    UK_WHOLE_COUNTRY_STATUSES,
    match_phrase,
    summarize,
    uk_overall_from_alert_status,
    uk_parts_from_alert_status,
)
from ..utils.dates import normalize_iso, to_iso, utc_now
from ..utils.errors import ErrorCode, SourceError
from ..utils.http import FetchTrace, fetch, parse_json_body
from ..utils.text import clean, element_text, normalize_key
from .base import SourceAdapter, log, regional_output
from .uk_slugs import UK_SLUGS

API_URL = "https://www.gov.uk/api/content/foreign-travel-advice/{slug}"
WEB_URL = "https://www.gov.uk/foreign-travel-advice/{slug}"
_OTHER_PAGE = re.compile(r"/foreign-travel-advice/(?P<slug>[a-z0-9-]+)")
_ADVICE_TARGET = re.compile(r"\btravel (?:to|in|on)\s+(?P<target>.+)", re.IGNORECASE)
# An advice statement, not a passing reference such as "areas where FCDO advises against all travel".
_ADVICE_STATEMENT = re.compile(
    r"(?<!where )(?<!which )\bFCDO (?:also |currently |now |continues to )?advises? against all", re.IGNORECASE
)
_SENTENCE_REGION = re.compile(r"advises against all (?:but essential )?travel to (?P<region>.+?)[.:]?$", re.IGNORECASE)


def _parts(doc: dict[str, Any]) -> dict[str, str]:
    return {p.get("slug", ""): p.get("body", "") or "" for p in doc["details"]["parts"] if isinstance(p, dict)}


def _targets_other_destination(element: Tag, text: str, own_slug: str) -> bool:
    """True when an advice sentence is about a linked neighbouring destination (e.g. Venezuela's border)."""
    others = {
        match["slug"]
        for link in element.find_all("a", href=True)
        if (match := _OTHER_PAGE.search(str(link["href"]))) and match["slug"] != own_slug
    }
    target = _ADVICE_TARGET.search(text)
    if not others or not target:
        return False
    target_key = normalize_key(target["target"])
    return any(target_key.startswith(normalize_key(slug.replace("-", " "))) for slug in others)


def _region_from_sentence(text: str) -> str | None:
    match = _SENTENCE_REGION.search(text)
    if not match:
        return None
    region = match["region"].strip().removesuffix(" due to")
    if not region or region.casefold().startswith("the following") or len(region) > 200:
        return None
    return region


def _is_areas_heading(element: Tag) -> bool:
    return str(element.get("id", "")).startswith("areas-where") or element_text(element).casefold().startswith(
        "areas where"
    )


def _section_has_advice(h2: Tag) -> bool:
    for following in h2.find_all_next(["h2", "p"]):
        if following.name == "h2":
            return False
        if _ADVICE_STATEMENT.search(element_text(following)):
            return True
    return False


def extract_regional(body_html: str, *, own_slug: str, country_name: str) -> list[RegionalWarning]:
    """Parse the 'Areas where FCDO advises against travel' section of the warnings page.

    Region headings are the h3 (or, on some pages, h2) headings inside that section.
    """
    soup = BeautifulSoup(body_html, "lxml")
    elements = [
        e for e in soup.find_all(["h2", "h3", "p", "ul", "ol"]) if e.find_parent(["li", "p", "ul", "ol"]) is None
    ]
    warnings: list[RegionalWarning] = []
    in_section = False
    heading: str | None = None
    current: RegionalWarning | None = None
    for element in elements:
        text = element_text(element)
        if element.name == "h2":
            current = None
            if _is_areas_heading(element):
                in_section, heading = True, None
            elif in_section and _section_has_advice(element):
                heading = text.rstrip(":").strip() or None
            else:
                in_section = False
            continue
        if not in_section:
            continue
        if element.name == "h3":
            heading = text.rstrip(":").strip() or None
            continue
        if element.name == "p":
            severity = match_phrase(text, UK_PHRASES) if _ADVICE_STATEMENT.search(text) else None
            if severity is not None and not _targets_other_destination(element, text, own_slug):
                current = RegionalWarning(
                    region=heading or _region_from_sentence(text) or country_name,
                    native_advice=text,
                    normalized_severity=severity,
                )
                warnings.append(current)
            elif text.casefold().startswith("find out more"):
                current = None
            continue
        if current is not None:
            current.native_details.extend(t for li in element.find_all("li") if (t := element_text(li)))
    return warnings


def extract_risk_labels(safety_html: str) -> list[str]:
    soup = BeautifulSoup(safety_html, "lxml")
    return [t for h in soup.find_all(["h2", "h3"]) if (t := element_text(h))]


NATIVE_SCALE = NativeScale(
    type="categorical",
    description=(
        "UK FCDO uses advisory wording such as 'against all travel' or 'against all but essential travel' "
        "(to the whole country or to parts of it) rather than a numbered national scale; "
        "nativeLevel lists the GOV.UK alert_status codes."
    ),
)
REGIONAL_UNAVAILABLE_NOTE = (
    "GOV.UK alert_status indicates FCDO warnings for parts of this country, but their details could not be read."
)


def build_advisory(doc: Any, *, slug: str, destination: Destination, include_regional: bool) -> SourceAdvisory:
    if (
        not isinstance(doc, dict)
        or doc.get("schema_name") != "travel_advice"
        or not isinstance(doc.get("details"), dict)
    ):
        raise SourceError(ErrorCode.UNEXPECTED_SOURCE_FORMAT, f"GOV.UK {slug}: not a travel_advice document")
    details = doc["details"]
    statuses = details.get("alert_status")
    if not isinstance(statuses, list) or not isinstance(details.get("parts"), list) or not details["parts"]:
        raise SourceError(ErrorCode.UNEXPECTED_SOURCE_FORMAT, f"GOV.UK {slug}: alert_status/parts missing")
    statuses = [str(s) for s in statuses]
    unknown = [s for s in statuses if s not in UK_WHOLE_COUNTRY_STATUSES and s not in UK_PARTS_STATUSES]
    if unknown:
        log.warning("GOV.UK %s: unrecognised alert_status values %s", slug, unknown)
    country_name = clean((details.get("country") or {}).get("name")) or destination.name
    parts = _parts(doc)

    overall = uk_overall_from_alert_status(statuses)
    native_advice = (
        {
            4: f"FCDO advises against all travel to {country_name}",
            3: f"FCDO advises against all but essential travel to {country_name}",
        }.get(overall or 0)
        if any(s in UK_WHOLE_COUNTRY_STATUSES for s in statuses)
        else None
    )
    if overall == 1:
        basis = (
            f"GOV.UK alert_status={statuses or '[]'}: no FCDO advice against travel to the whole country, "
            "mapped to 1 (the FCDO has no intermediate national levels)"
        )
    elif overall is None:
        basis = f"GOV.UK alert_status={statuses}: unrecognised whole-country status, not mapped"
    else:
        basis = f"Mapped from GOV.UK alert_status={statuses}"

    parts_severities = uk_parts_from_alert_status(statuses)
    warnings_html = parts.get("warnings-and-insurance")
    regional: list[RegionalWarning] = []
    if warnings_html:
        regional = extract_regional(warnings_html, own_slug=slug, country_name=country_name)
    coverage = "available"
    if parts_severities and not regional:
        log.warning("GOV.UK %s: alert_status lists regional warnings but none were parsed", slug)
        coverage = "unavailable"

    categories, native_labels = map_labels(
        extract_risk_labels(parts.get("safety-and-security", "")), unmatched_as_other=False
    )
    severity = summarize(
        overall,
        [*parts_severities, *(w.normalized_severity for w in regional)] if coverage == "available" else [],
        regional_indicated=bool(parts_severities) if coverage == "available" else None,
        basis=basis,
    )
    return SourceAdvisory(
        source_code="UK",
        source_name=UkFcdoAdapter.name,
        source_url=WEB_URL.format(slug=slug),
        retrieval_url=API_URL.format(slug=slug),
        retrieved_at=to_iso(utc_now()),
        source_updated_at=normalize_iso(doc.get("public_updated_at")),
        native_level=", ".join(statuses) if statuses else "none",
        native_advice=native_advice,
        native_scale=NATIVE_SCALE,
        normalized_severity=severity,
        risk_categories=categories,
        native_risk_labels=native_labels,
        risk_categories_basis="Section headings of the GOV.UK 'Safety and security' page that match the vocabulary.",
        **regional_output(
            include_regional, coverage, regional, REGIONAL_UNAVAILABLE_NOTE if coverage != "available" else None
        ),
    )


class UkFcdoAdapter(SourceAdapter):
    code: ClassVar[SourceCode] = "UK"
    name: ClassVar[str] = "U.K. Foreign, Commonwealth & Development Office"

    async def fetch_advisory(
        self,
        destination: Destination,
        client: httpx.AsyncClient,
        *,
        include_regional: bool = True,
        trace: FetchTrace | None = None,
    ) -> SourceAdvisory:
        slug = UK_SLUGS.get(destination.iso2)
        if slug is None:
            raise SourceError(ErrorCode.DESTINATION_NOT_FOUND, f"no GOV.UK slug for {destination.iso2}")
        url = API_URL.format(slug=slug)
        response = await fetch(client, url, accept="application/json", trace=trace)
        doc = parse_json_body(response.text, url=url)
        return build_advisory(doc, slug=slug, destination=destination, include_regional=include_regional)
