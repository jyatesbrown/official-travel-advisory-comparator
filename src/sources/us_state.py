"""U.S. Department of State adapter.

travel.state.gov destination pages block non-browser clients (HTTP 403), so this adapter reads the
Department's official RSS feed, which carries each advisory's level, link, date and full text.
Feed <category> codes are not ISO codes (e.g. "UK" = United Kingdom, "MO" = Morocco), so items are
matched by resolving the destination name in the item title.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import ClassVar

import httpx
from bs4 import BeautifulSoup, Tag

from ..destinations.resolver import Destination, DestinationResolver, get_resolver
from ..models.input import SourceCode
from ..models.output import RegionalWarning, SourceAdvisory
from ..normalization.risks import map_labels
from ..normalization.severity import US_PHRASES, match_phrase, summarize, us_level_to_severity
from ..utils.dates import parse_rss_date, to_iso, utc_now
from ..utils.errors import ErrorCode, SourceError
from ..utils.http import FetchTrace, fetch
from ..utils.text import clean, element_text, normalize_key
from .base import SourceAdapter, log, regional_output

FEED_URL = "https://travel.state.gov/_res/rss/TAsTWs.xml"
MIN_FEED_ITEMS = 100
FEED_ONLY_ALIASES = {"french saint martin": "MF"}

_TITLE = re.compile(
    r"^(?P<name>.+?)\s+-\s+Level\s+(?P<level>[1-4])\s*:\s*(?P<advice>.+?)(?:\s+-\s+Level\s+[1-4]\s*:.*)?$"
)
_TITLE_SUFFIX = re.compile(r"\s+Travel Advisory$", re.IGNORECASE)
_DUE_TO = re.compile(r"\bdue to\b(?P<rest>.+?)(?:\.\s|\.$|\bSome areas\b|\bRead the entire\b|$)", re.IGNORECASE)
_LABEL_SPLIT = re.compile(r",\s*(?:and\s+)?|\s+and\s+")
_LABEL_PREFIX = re.compile(r"^(?:the\s+)?(?:active\s+)?(?:risks?\s+of\s+)?(?:the\s+)?", re.IGNORECASE)
_SOME_AREAS = re.compile(r"\bSome areas have (?:an )?increased risk", re.IGNORECASE)
_REGIONAL = re.compile(
    r"^(?P<advice>Do not travel|Reconsider travel|Exercise increased caution|Exercise normal precautions)\b"
    r"\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
_PREPOSITION = re.compile(r"^(?:to|in|near|within|along|throughout|on)\b\s*", re.IGNORECASE)
_NO_REGION = re.compile(r"^(?:due to|when|while|if|and|because)\b", re.IGNORECASE)
_MAX_REGION_CHARS = 250


@dataclass(frozen=True)
class FeedItem:
    name: str
    level: int
    advice: str
    link: str
    pub_date: str | None
    description: str


def parse_feed(xml_text: str) -> list[FeedItem]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise SourceError(ErrorCode.UNEXPECTED_SOURCE_FORMAT, f"US feed is not valid XML: {exc}") from exc
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise SourceError(ErrorCode.UNEXPECTED_SOURCE_FORMAT, f"US feed root is <{root.tag}>, expected RSS")
    raw_items = channel.findall("item")
    if len(raw_items) < MIN_FEED_ITEMS:
        raise SourceError(ErrorCode.UNEXPECTED_SOURCE_FORMAT, f"US feed has only {len(raw_items)} items")
    items: list[FeedItem] = []
    for raw in raw_items:
        match = _TITLE.match(clean(raw.findtext("title")))
        if not match:
            continue
        items.append(
            FeedItem(
                name=_TITLE_SUFFIX.sub("", match["name"]).strip(),
                level=int(match["level"]),
                advice=match["advice"].strip(),
                link=clean(raw.findtext("link")),
                pub_date=parse_rss_date(raw.findtext("pubDate")),
                description=raw.findtext("description") or "",
            )
        )
    if len(items) < len(raw_items) // 2:
        raise SourceError(
            ErrorCode.UNEXPECTED_SOURCE_FORMAT,
            f"US feed titles no longer match 'Name - Level N: Advice' ({len(items)}/{len(raw_items)} parsed)",
        )
    return items


def _item_iso2(name: str, resolver: DestinationResolver) -> str | None:
    key = normalize_key(name)
    if key in FEED_ONLY_ALIASES:
        return FEED_ONLY_ALIASES[key]
    resolution = resolver.resolve(name)
    if resolution.destination is None or resolution.method == "fuzzy":
        return None
    return resolution.destination.iso2


def select_item(items: list[FeedItem], destination: Destination, resolver: DestinationResolver) -> FeedItem:
    matches = [item for item in items if _item_iso2(item.name, resolver) == destination.iso2]
    if not matches:
        raise SourceError(ErrorCode.DESTINATION_NOT_FOUND, f"no US feed item for {destination.iso2}")
    return max(matches, key=lambda item: item.pub_date or "")


def _lead_text(soup: BeautifulSoup) -> tuple[str, Tag | None]:
    first_p = soup.find("p")
    parts: list[str] = []
    for node in soup.children:
        parts.append(element_text(node) if isinstance(node, Tag) else str(node))
        if node is first_p:
            break
    return clean(" ".join(parts)), first_p if isinstance(first_p, Tag) else None


def extract_risk_labels(lead: str) -> list[str]:
    match = _DUE_TO.search(lead)
    if not match:
        return []
    labels: list[str] = []
    for chunk in _LABEL_SPLIT.split(match["rest"]):
        label = _LABEL_PREFIX.sub("", chunk.strip(" .;:")).strip(" .;:")
        if label and label not in labels:
            labels.append(label)
    return labels


def extract_regional(soup: BeautifulSoup, lead_p: Tag | None, own_names: set[str]) -> list[RegionalWarning]:
    warnings: list[RegionalWarning] = []
    captured: list[Tag] = []
    for element in soup.find_all(["p", "li"]):
        if element is lead_p or any(parent in captured for parent in element.parents):
            continue
        text = element_text(element)
        match = _REGIONAL.match(text)
        if not match:
            continue
        rest = match["rest"].strip()
        if not _PREPOSITION.match(rest) or _NO_REGION.match(_PREPOSITION.sub("", rest)):
            continue
        rest = _PREPOSITION.sub("", rest)
        region = re.split(r"\s+due to\b", rest, maxsplit=1, flags=re.IGNORECASE)[0].strip(" .:;")
        if not region or len(region) > _MAX_REGION_CHARS or normalize_key(region) in own_names:
            continue
        captured.append(element)
        warnings.append(
            RegionalWarning(
                region=region,
                native_advice=match["advice"],
                normalized_severity=match_phrase(match["advice"], US_PHRASES),
                native_details=[text],
            )
        )
    return warnings


def build_advisory(item: FeedItem, destination: Destination, *, include_regional: bool) -> SourceAdvisory:
    soup = BeautifulSoup(item.description, "html.parser")
    lead, lead_p = _lead_text(soup)
    if not lead:
        raise SourceError(ErrorCode.UNEXPECTED_SOURCE_FORMAT, f"US advisory for {item.name} has no summary text")
    overall = us_level_to_severity(item.level)
    labels = extract_risk_labels(lead)
    categories, native_labels = map_labels(labels, unmatched_as_other=True)
    regional = extract_regional(soup, lead_p, {normalize_key(item.name), normalize_key(destination.name)})
    severity = summarize(
        overall,
        [w.normalized_severity for w in regional],
        regional_indicated=bool(_SOME_AREAS.search(lead)) or bool(regional),
        basis=f"Mapped from U.S. Department of State Level {item.level} ({item.advice})",
    )
    return SourceAdvisory(
        source_code="US",
        source_name=UsStateAdapter.name,
        source_url=item.link or FEED_URL,
        retrieval_url=FEED_URL,
        retrieved_at=to_iso(utc_now()),
        source_updated_at=item.pub_date,
        native_level=f"Level {item.level}",
        native_advice=item.advice,
        normalized_severity=severity,
        risk_categories=categories,
        native_risk_labels=native_labels,
        risk_categories_basis="Risk factors named in the advisory summary sentence ('... due to ...').",
        regional_warnings=regional_output(include_regional, regional),
    )


class UsStateAdapter(SourceAdapter):
    code: ClassVar[SourceCode] = "US"
    name: ClassVar[str] = "U.S. Department of State"

    def __init__(self, resolver: DestinationResolver | None = None) -> None:
        self._resolver = resolver or get_resolver()

    async def fetch_advisory(
        self,
        destination: Destination,
        client: httpx.AsyncClient,
        *,
        include_regional: bool = True,
        trace: FetchTrace | None = None,
    ) -> SourceAdvisory:
        response = await fetch(
            client,
            FEED_URL,
            accept="application/rss+xml, application/xml;q=0.9, */*;q=0.1",
            trace=trace,
            not_found_code=ErrorCode.UPSTREAM_UNAVAILABLE,
        )
        items = parse_feed(response.text)
        item = select_item(items, destination, self._resolver)
        advisory = build_advisory(item, destination, include_regional=include_regional)
        log.debug("US matched feed item %r for %s", item.name, destination.iso2)
        return advisory
