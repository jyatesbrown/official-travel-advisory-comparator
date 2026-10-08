"""Regional-coverage, native-scale and source-alias semantics (schema 1.1)."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.destinations.resolver import get_resolver
from src.models.input import ActorInput
from src.models.output import NORMALIZED_SCALE_NOTE
from src.sources import canada, uk_fcdo, us_state
from src.sources.base import REGIONAL_OMITTED_NOTE
from src.sources.uk_slugs import UK_SLUGS

from .conftest import dest, load_json

resolver = get_resolver()
ACTOR_DIR = Path(__file__).resolve().parents[1] / ".actor"
US_UNAVAILABLE = "Regional advisory detail is unavailable from the U.S. State Department RSS source used by this Actor."


def _us(us_items, query: str, include_regional: bool = True):
    d = dest(query)
    return us_state.build_advisory(us_state.select_item(us_items, d, resolver), d, include_regional=include_regional)


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


# --- Regional coverage -------------------------------------------------------


@pytest.mark.parametrize("query", ["Mexico", "Trinidad and Tobago", "Kenya"])
def test_us_unavailable_regional_detail_is_null_not_empty(us_items, query: str) -> None:
    advisory = _us(us_items, query)
    record = advisory.to_record()
    assert record["regionalCoverage"] == "unavailable"
    assert record["regionalWarnings"] is None
    assert record["normalizedSeverity"]["regionalMax"] is None
    assert record["normalizedSeverity"]["hasRegionalEscalation"] is None
    assert record["regionalCoverageNote"] == US_UNAVAILABLE


def test_us_named_regions_are_available(us_items) -> None:
    advisory = _us(us_items, "Turkey")
    assert advisory.regional_coverage == "available"
    assert advisory.regional_warnings
    assert advisory.normalized_severity.regional_max == 4
    assert advisory.regional_coverage_note == us_state.REGIONAL_PARTIAL_NOTE


@pytest.mark.parametrize(
    "advisory_factory",
    [lambda: _uk("France"), lambda: _uk("Hong Kong"), lambda: _uk("Trinidad and Tobago"), lambda: _ca("France")],
)
def test_known_empty_regional_is_empty_list(advisory_factory) -> None:
    advisory = advisory_factory()
    assert advisory.regional_coverage == "available"
    assert advisory.regional_warnings == []
    assert advisory.regional_coverage_note is None
    assert advisory.normalized_severity.has_regional_escalation is False


@pytest.mark.parametrize(
    ("advisory_factory", "regional_max"),
    [(lambda: _uk("Ukraine"), 4), (lambda: _uk("Mexico"), 3), (lambda: _ca("Kenya"), 4), (lambda: _ca("Mexico"), 3)],
)
def test_known_regional_warnings_are_listed(advisory_factory, regional_max: int) -> None:
    advisory = advisory_factory()
    assert advisory.regional_coverage == "available"
    assert advisory.regional_warnings
    assert advisory.normalized_severity.regional_max == regional_max


def test_include_regional_false_keeps_coverage_and_explains_null() -> None:
    advisory = _ca("Kenya", include_regional=False)
    assert advisory.regional_coverage == "available"
    assert advisory.regional_warnings is None
    assert advisory.regional_coverage_note == REGIONAL_OMITTED_NOTE
    assert advisory.normalized_severity.regional_max == 4


def test_us_include_regional_false_keeps_unavailable_note(us_items) -> None:
    advisory = _us(us_items, "Mexico", include_regional=False)
    assert advisory.regional_coverage == "unavailable"
    assert advisory.regional_coverage_note == US_UNAVAILABLE


def test_ca_flagged_regions_without_parsed_blocks_is_unavailable() -> None:
    doc = load_json("ca/cta-cap-ke.json")
    doc["data"]["eng"]["advisories"] = "<p>Restructured</p>"
    advisory = canada.build_advisory(doc, destination=dest("Kenya"), include_regional=True)
    assert advisory.regional_coverage == "unavailable"
    assert advisory.regional_warnings is None
    assert advisory.normalized_severity.regional_max is None
    assert advisory.normalized_severity.has_regional_escalation is None
    assert advisory.regional_coverage_note == canada.REGIONAL_UNAVAILABLE_NOTE


# --- Native scales -----------------------------------------------------------


def test_us_native_scale_is_numbered(us_items) -> None:
    scale = _us(us_items, "Mexico").to_record()["nativeScale"]
    assert scale["type"] == "numbered"
    assert "Levels 1 through 4" in scale["description"]


def test_ca_native_scale_is_categorical() -> None:
    scale = _ca("Mexico").to_record()["nativeScale"]
    assert scale["type"] == "categorical"
    assert "named advisory categories rather than numbered levels" in scale["description"]
    assert "Level 1" not in scale["description"]


def test_uk_native_scale_is_categorical() -> None:
    scale = _uk("Mexico").to_record()["nativeScale"]
    assert scale["type"] == "categorical"
    assert "against all but essential travel" in scale["description"]
    assert "rather than a numbered national scale" in scale["description"]


def test_normalized_severity_is_labelled_internal(us_items) -> None:
    assert _us(us_items, "Mexico").to_record()["normalizedSeverity"]["scaleNote"] == NORMALIZED_SCALE_NOTE
    assert "not necessarily the source government's native advisory level" in NORMALIZED_SCALE_NOTE.lower()
    fields = json.loads((ACTOR_DIR / "dataset_schema.json").read_text("utf-8"))["fields"]
    advisory = fields["properties"]["advisories"]["items"]["properties"]
    overall = advisory["normalizedSeverity"]["properties"]["overall"]["description"]
    assert "internal cross-source" in overall
    assert "Not necessarily the government's native level" in overall
    assert set(advisory["regionalCoverage"]["enum"]) == {"available", "unavailable", "not_applicable"}


# --- Source aliases ----------------------------------------------------------

ALIASES = {
    "US": ["US", "us", "USA", "usa", "United States", "united states", "State Department", "state department"],
    "UK": ["UK", "uk", "FCDO", "fcdo", "United Kingdom", "united kingdom", "GOV.UK", "gov.uk"],
    "CA": ["CA", "ca", "CAN", "can", "Canada", "canada", "travel.gc.ca"],
}


@pytest.mark.parametrize(("code", "alias"), [(c, a) for c, aliases in ALIASES.items() for a in aliases])
def test_source_alias_normalizes(code: str, alias: str) -> None:
    other = "CA" if code != "CA" else "US"
    parsed = ActorInput.model_validate({"destination": "Kenya", "sources": [alias, other]})
    assert code in parsed.sources
    assert set(parsed.sources) <= {"US", "UK", "CA"}


def test_aliases_dedupe_to_canonical_order() -> None:
    parsed = ActorInput.model_validate(
        {"destination": "Kenya", "sources": ["canada", "usa", "US", " State  Department "]}
    )
    assert parsed.sources == ["US", "CA"]


@pytest.mark.parametrize("sources", [["us", "USA"], ["fcdo", "France"], ["us", 3]])
def test_alias_errors_still_rejected(sources: list) -> None:
    with pytest.raises(ValidationError):
        ActorInput.model_validate({"destination": "Kenya", "sources": sources})
