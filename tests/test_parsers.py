"""Parser tests against official-source fixtures captured 2026-10-07."""

import pytest

from src.destinations.resolver import get_resolver
from src.sources import canada, uk_fcdo, us_state
from src.sources.uk_slugs import UK_SLUGS
from src.utils.errors import ErrorCode, SourceError

from .conftest import dest, load_json

resolver = get_resolver()


def _us(us_items, query: str):
    d = dest(query)
    return us_state.build_advisory(us_state.select_item(us_items, d, resolver), d, include_regional=True)


def _uk(query: str, include_regional: bool = True):
    d = dest(query)
    slug = UK_SLUGS[d.iso2]
    return uk_fcdo.build_advisory(
        load_json(f"uk/{slug}.json"), slug=slug, destination=d, include_regional=include_regional
    )


def _ca(query: str, include_regional: bool = True):
    d = dest(query)
    return canada.build_advisory(
        load_json(f"ca/cta-cap-{d.iso2.lower()}.json"), destination=d, include_regional=include_regional
    )


# --- U.S. Department of State RSS ---


def test_us_feed_parses(us_items) -> None:
    assert len(us_items) >= us_state.MIN_FEED_ITEMS
    assert all(1 <= item.level <= 4 for item in us_items)


@pytest.mark.parametrize(
    ("query", "level", "advice"),
    [
        ("Trinidad and Tobago", 3, "Reconsider Travel"),
        ("Mexico", 2, "Exercise Increased Caution"),
        ("Ukraine", 4, "Do Not Travel"),
        ("Haiti", 4, "Do Not Travel"),
        ("Thailand", 1, "Exercise Normal Precautions"),
        ("Turkey", 2, "Exercise Increased Caution"),
        ("Côte d'Ivoire", 2, "Exercise Increased Caution"),
    ],
)
def test_us_levels(us_items, query: str, level: int, advice: str) -> None:
    advisory = _us(us_items, query)
    assert advisory.native_level == f"Level {level}"
    assert advisory.native_advice == advice
    assert advisory.normalized_severity.overall == level
    assert advisory.source_url.startswith("https://travel.state.gov/")
    assert advisory.source_updated_at


def test_us_risk_labels(us_items) -> None:
    advisory = _us(us_items, "Colombia")
    assert advisory.risk_categories == ["crime", "terrorism", "kidnapping", "civil_unrest", "natural_disaster"]
    assert "civil unrest" in advisory.native_risk_labels


def test_us_inline_markup_does_not_split_words(us_items) -> None:
    assert _us(us_items, "Hong Kong").native_risk_labels == ["arbitrary enforcement of local laws"]


def test_us_regional_escalation(us_items) -> None:
    advisory = _us(us_items, "Turkey")
    assert advisory.normalized_severity.overall == 2
    assert advisory.normalized_severity.regional_max == 4
    assert advisory.normalized_severity.has_regional_escalation is True
    assert advisory.regional_warnings[0].region == "the border region with Syria and Iraq"


def test_us_regional_text_is_clean(us_items) -> None:
    regions = [w.region for w in _us(us_items, "Thailand").regional_warnings]
    assert regions == ["the Thai-Cambodian border", "the Yala, Pattani, and Narathiwat provinces"]


def test_us_restated_national_advice_is_not_a_region(us_items) -> None:
    advisory = _us(us_items, "Trinidad and Tobago")
    assert advisory.regional_warnings == []
    assert advisory.normalized_severity.regional_max is None


def test_us_some_areas_without_parsed_regions_is_unknown(us_items) -> None:
    assert _us(us_items, "Mexico").normalized_severity.has_regional_escalation is None


def test_us_newest_duplicate_wins() -> None:
    item = """<item><title>Testland - Level {level}: {advice}</title><link>https://travel.state.gov/x</link>
    <pubDate>{date}</pubDate><description>&lt;p&gt;Exercise caution.&lt;/p&gt;</description></item>"""
    items = "".join(
        item.format(level=1, advice="Exercise Normal Precautions", date="Mon, 01 Jan 2024 00:00:00 GMT")
        if i % 2
        else item.format(level=2, advice="Exercise Increased Caution", date="Tue, 01 Oct 2024 00:00:00 GMT")
        for i in range(120)
    ).replace("Testland", "France")
    parsed = us_state.parse_feed(f"<rss><channel>{items}</channel></rss>")
    chosen = us_state.select_item(parsed, dest("France"), resolver)
    assert chosen.level == 2


@pytest.mark.parametrize(
    "xml",
    ["not xml", "<html><body>blocked</body></html>", "<rss><channel><item><title>x</title></item></channel></rss>"],
)
def test_us_bad_feed_is_format_error(xml: str) -> None:
    with pytest.raises(SourceError) as info:
        us_state.parse_feed(xml)
    assert info.value.code is ErrorCode.UNEXPECTED_SOURCE_FORMAT


def test_us_title_drift_is_format_error(us_feed_text: str) -> None:
    drifted = us_feed_text.replace(" - Level ", " | Tier ")
    with pytest.raises(SourceError) as info:
        us_state.parse_feed(drifted)
    assert info.value.code is ErrorCode.UNEXPECTED_SOURCE_FORMAT


def test_us_missing_destination(us_items) -> None:
    with pytest.raises(SourceError) as info:
        us_state.select_item(us_items, dest("United States"), resolver)
    assert info.value.code is ErrorCode.DESTINATION_NOT_FOUND


# --- U.K. FCDO (GOV.UK Content API) ---


@pytest.mark.parametrize(
    ("query", "overall", "regional_max", "count"),
    [
        ("Trinidad and Tobago", 1, None, 0),
        ("France", 1, None, 0),
        ("Haiti", 4, None, 0),
        ("Cuba", 3, None, 0),
        ("Mexico", 1, 3, 14),
        ("Colombia", 1, 3, 5),
        ("Ukraine", 1, 4, 4),
        ("Kenya", 1, 4, 2),
        ("Thailand", 1, 3, 3),
        ("Turkey", 1, 4, 1),
        ("Côte d'Ivoire", 1, 4, 2),
    ],
)
def test_uk_severity(query: str, overall: int, regional_max: int | None, count: int) -> None:
    advisory = _uk(query)
    assert advisory.normalized_severity.overall == overall
    assert advisory.normalized_severity.regional_max == regional_max
    assert len(advisory.regional_warnings) == count
    assert advisory.source_url.startswith("https://www.gov.uk/foreign-travel-advice/")


def test_uk_whole_country_native_advice() -> None:
    advisory = _uk("Haiti")
    assert advisory.native_level == "avoid_all_travel_to_whole_country"
    assert advisory.native_advice == "FCDO advises against all travel to Haiti"


def test_uk_no_national_statement_is_null_not_invented() -> None:
    advisory = _uk("France")
    assert advisory.native_level == "none"
    assert advisory.native_advice is None


def test_uk_regions_and_details() -> None:
    warnings = _uk("Ukraine").regional_warnings
    assert [(w.region, w.normalized_severity) for w in warnings[:3]] == [
        ("Crimea", 4),
        ("Border with Belarus", 4),
        ("All other regions of Ukraine", 4),
    ]
    assert warnings[3].normalized_severity == 3
    assert "Lviv" in " ".join(warnings[3].native_details)


def test_uk_h2_region_headings() -> None:
    assert {w.region for w in _uk("Thailand").regional_warnings} == {
        "Thailand-Malaysia border",
        "Thailand-Cambodia border",
    }


def test_uk_neighbouring_country_advice_excluded() -> None:
    advice = " ".join(w.native_advice for w in _uk("Colombia").regional_warnings)
    assert "Venezuela’s border regions" not in advice


def test_uk_risk_labels() -> None:
    advisory = _uk("Kenya")
    assert {"terrorism", "kidnapping", "crime"} <= set(advisory.risk_categories)
    assert "Terrorist kidnap" in advisory.native_risk_labels


def test_uk_regional_flag_off_keeps_regional_max() -> None:
    advisory = _uk("Mexico", include_regional=False)
    assert advisory.regional_warnings is None
    assert advisory.normalized_severity.regional_max == 3


def test_uk_alert_without_parsable_regions_is_unknown() -> None:
    doc = load_json("uk/mexico.json")
    for part in doc["details"]["parts"]:
        if part["slug"] == "warnings-and-insurance":
            part["body"] = "<p>Restructured page</p>"
    advisory = uk_fcdo.build_advisory(doc, slug="mexico", destination=dest("Mexico"), include_regional=True)
    assert advisory.normalized_severity.regional_max == 3
    assert advisory.normalized_severity.has_regional_escalation is True
    assert advisory.regional_warnings == []


@pytest.mark.parametrize(
    "doc",
    [{"schema_name": "guide"}, {"schema_name": "travel_advice", "details": {}}, [], "x"],
)
def test_uk_unexpected_document(doc) -> None:
    with pytest.raises(SourceError) as info:
        uk_fcdo.build_advisory(doc, slug="mexico", destination=dest("Mexico"), include_regional=True)
    assert info.value.code is ErrorCode.UNEXPECTED_SOURCE_FORMAT


def test_uk_slug_table() -> None:
    assert UK_SLUGS["CI"] == "cote-d-ivoire"
    assert UK_SLUGS["TR"] == "turkey"
    assert len(UK_SLUGS) >= 220


# --- Government of Canada ---


@pytest.mark.parametrize(
    ("query", "state", "overall", "regional_max"),
    [
        ("Trinidad and Tobago", 1, 2, 3),
        ("France", 1, 2, None),
        ("Ukraine", 3, 4, None),
        ("Haiti", 3, 4, None),
        ("Colombia", 1, 2, 4),
        ("Kenya", 1, 2, 4),
        ("Turkey", 1, 2, 4),
        ("Côte d'Ivoire", 1, 2, 4),
        ("Hong Kong", 1, 2, None),
    ],
)
def test_ca_severity(query: str, state: int, overall: int, regional_max: int | None) -> None:
    advisory = _ca(query)
    assert advisory.native_level == f"advisory-state {state}"
    assert advisory.normalized_severity.overall == overall
    assert advisory.normalized_severity.regional_max == regional_max
    assert advisory.source_url.startswith("https://travel.gc.ca/destinations/")


def test_ca_native_advice_wording() -> None:
    assert _ca("Mexico").native_advice == "Exercise a high degree of caution"
    assert _ca("Ukraine").native_advice == "Avoid all travel"


def test_ca_regions() -> None:
    warnings = _ca("Kenya").regional_warnings
    assert ("Border with Somalia", 4) in [(w.region, w.normalized_severity) for w in warnings]
    assert ("Kibera neighbourhood of Nairobi", 3) in [(w.region, w.normalized_severity) for w in warnings]


def test_ca_regional_flag_off() -> None:
    advisory = _ca("Colombia", include_regional=False)
    assert advisory.regional_warnings is None
    assert advisory.normalized_severity.regional_max == 4


def test_ca_iso_mismatch_is_format_error() -> None:
    with pytest.raises(SourceError) as info:
        canada.build_advisory(load_json("ca/cta-cap-mx.json"), destination=dest("Kenya"), include_regional=True)
    assert info.value.code is ErrorCode.UNEXPECTED_SOURCE_FORMAT


def test_ca_unknown_state_is_format_error() -> None:
    doc = load_json("ca/cta-cap-fr.json")
    doc["data"]["advisory-state"] = 9
    with pytest.raises(SourceError) as info:
        canada.build_advisory(doc, destination=dest("France"), include_regional=True)
    assert info.value.code is ErrorCode.UNEXPECTED_SOURCE_FORMAT
