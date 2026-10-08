"""Comparison-level regional coverage and conclusion semantics (schema 1.2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.models.output import NativeScale, NormalizedSeverity, SourceAdvisory
from src.normalization.comparison import compare

ROOT = Path(__file__).resolve().parent.parent


def _adv(code: str, coverage: str, regional_max: int | None = None) -> SourceAdvisory:
    known = coverage != "unavailable"
    return SourceAdvisory(
        source_code=code,
        source_name=code,
        source_url="https://example.gov",
        retrieval_url="https://example.gov",
        retrieved_at="2026-01-01T00:00:00Z",
        source_updated_at=None,
        native_level=None,
        native_advice=None,
        native_scale=NativeScale(type="numbered", description="test"),
        normalized_severity=NormalizedSeverity(
            overall=2,
            regional_max=regional_max,
            has_regional_escalation=(regional_max is not None and regional_max > 2) if known else None,
            basis="test",
        ),
        risk_categories=[],
        native_risk_labels=[],
        risk_categories_basis="test",
        regional_coverage=coverage,
        regional_coverage_note=None if known else "unavailable",
        regional_warnings=[] if known and regional_max is None else None if not known else [],
    )


def _regional(advisories: list[SourceAdvisory], requested: list[str] | None = None) -> dict:
    record = compare(advisories, requested).to_record()
    return {k: record[k] for k in ("regionalCoverage", "regionalWarningConclusion", "highestRegionalSeverity")}


ALL = ["US", "UK", "CA"]

CASES = {
    "A_complete_warnings": (
        [_adv("US", "available"), _adv("UK", "available", 4), _adv("CA", "available", 3)],
        {
            "regionalCoverage": {
                "status": "complete",
                "sourcesAvailable": ALL,
                "sourcesUnavailable": [],
                "allRequestedSourcesKnown": True,
            },
            "regionalWarningConclusion": "warnings_reported",
            "highestRegionalSeverity": 4,
        },
    ),
    "B_complete_none": (
        [_adv("US", "available"), _adv("UK", "available"), _adv("CA", "available")],
        {
            "regionalCoverage": {
                "status": "complete",
                "sourcesAvailable": ALL,
                "sourcesUnavailable": [],
                "allRequestedSourcesKnown": True,
            },
            "regionalWarningConclusion": "none_reported",
            "highestRegionalSeverity": None,
        },
    ),
    "C_partial_none_known": (
        [_adv("US", "unavailable"), _adv("UK", "available"), _adv("CA", "available")],
        {
            "regionalCoverage": {
                "status": "partial",
                "sourcesAvailable": ["UK", "CA"],
                "sourcesUnavailable": ["US"],
                "allRequestedSourcesKnown": False,
            },
            "regionalWarningConclusion": "unknown_due_to_incomplete_coverage",
            "highestRegionalSeverity": None,
        },
    ),
    "D_partial_warnings": (
        [_adv("US", "unavailable"), _adv("UK", "available", 4), _adv("CA", "available", 3)],
        {
            "regionalCoverage": {
                "status": "partial",
                "sourcesAvailable": ["UK", "CA"],
                "sourcesUnavailable": ["US"],
                "allRequestedSourcesKnown": False,
            },
            "regionalWarningConclusion": "warnings_reported",
            "highestRegionalSeverity": 4,
        },
    ),
    "E_none_available": (
        [_adv("US", "unavailable"), _adv("UK", "unavailable"), _adv("CA", "unavailable")],
        {
            "regionalCoverage": {
                "status": "unavailable",
                "sourcesAvailable": [],
                "sourcesUnavailable": ALL,
                "allRequestedSourcesKnown": False,
            },
            "regionalWarningConclusion": "unknown_due_to_incomplete_coverage",
            "highestRegionalSeverity": None,
        },
    ),
}


@pytest.mark.parametrize("case", CASES)
def test_comparison_regional_cases(case: str) -> None:
    advisories, expected = CASES[case]
    assert _regional(advisories, ALL) == expected


def test_sources_with_regional_warnings_lists_only_known_warned_sources() -> None:
    record = compare([_adv("US", "unavailable"), _adv("UK", "available", 4), _adv("CA", "available")]).to_record()
    assert record["sourcesWithRegionalWarnings"] == ["UK"]


def test_failed_source_is_not_regional_unavailability() -> None:
    result = _regional([_adv("UK", "available"), _adv("CA", "available")], ALL)
    assert result["regionalCoverage"]["status"] == "complete"
    assert result["regionalCoverage"]["sourcesUnavailable"] == []
    assert result["regionalCoverage"]["allRequestedSourcesKnown"] is False
    assert result["regionalWarningConclusion"] == "none_reported"


def test_not_applicable_counts_as_known() -> None:
    result = _regional([_adv("US", "not_applicable"), _adv("CA", "available")], ["US", "CA"])
    assert result["regionalCoverage"]["status"] == "complete"
    assert result["regionalWarningConclusion"] == "none_reported"


def test_no_advisories_is_unavailable() -> None:
    result = _regional([], ALL)
    assert result["regionalCoverage"]["status"] == "unavailable"
    assert result["regionalWarningConclusion"] == "unknown_due_to_incomplete_coverage"


def test_dataset_schema_documents_regional_conclusion() -> None:
    text = json.dumps(json.loads((ROOT / ".actor" / "dataset_schema.json").read_text()))
    assert "so the Actor cannot conclude that no regional warnings exist" in text
    assert "Null does not by itself mean that no regional warnings exist" in text
    assert "none_reported is used only when regional coverage is complete" in text
