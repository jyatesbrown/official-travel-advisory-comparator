import pytest

from src.models.output import NormalizedSeverity, SourceAdvisory
from src.normalization.comparison import compare
from src.normalization.risks import RISK_CATEGORIES, categorize, map_labels
from src.normalization.severity import (
    CA_PHRASES,
    UK_PHRASES,
    US_PHRASES,
    canada_state_to_severity,
    match_phrase,
    summarize,
    uk_overall_from_alert_status,
    uk_parts_from_alert_status,
    us_level_to_severity,
)


@pytest.mark.parametrize(("level", "expected"), [(1, 1), (2, 2), (3, 3), (4, 4), (0, None), (5, None)])
def test_us_levels(level: int, expected: int | None) -> None:
    assert us_level_to_severity(level) == expected


@pytest.mark.parametrize(("state", "expected"), [(0, 1), (1, 2), (2, 3), (3, 4), (4, None), (-1, None)])
def test_canada_states(state: int, expected: int | None) -> None:
    assert canada_state_to_severity(state) == expected


@pytest.mark.parametrize(
    ("text", "table", "expected"),
    [
        ("Take normal security precautions", CA_PHRASES, 1),
        ("Exercise normal security precautions", CA_PHRASES, 1),
        ("Exercise a high degree of caution", CA_PHRASES, 2),
        ("Avoid non\u2011essential travel", CA_PHRASES, 3),
        ("Avoid all travel", CA_PHRASES, 4),
        ("FCDO advises against all but essential travel to:", UK_PHRASES, 3),
        ("FCDO advises against all travel to Crimea.", UK_PHRASES, 4),
        ("Do Not Travel", US_PHRASES, 4),
        ("Reconsider Travel", US_PHRASES, 3),
        ("Exercise Increased Caution", US_PHRASES, 2),
        ("Something else entirely", CA_PHRASES, None),
        ("", US_PHRASES, None),
    ],
)
def test_match_phrase(text: str, table, expected: int | None) -> None:
    assert match_phrase(text, table) == expected


@pytest.mark.parametrize(
    ("statuses", "overall", "parts"),
    [
        ([], 1, []),
        (["avoid_all_but_essential_travel_to_parts"], 1, [3]),
        (["avoid_all_travel_to_parts", "avoid_all_but_essential_travel_to_parts"], 1, [4, 3]),
        (["avoid_all_but_essential_travel_to_whole_country"], 3, []),
        (["avoid_all_travel_to_whole_country"], 4, []),
        (["avoid_all_travel_to_whole_country", "avoid_all_travel_to_parts"], 4, [4]),
        (["some_new_status_whole_country"], None, []),
    ],
)
def test_uk_alert_status(statuses: list[str], overall: int | None, parts: list[int]) -> None:
    assert uk_overall_from_alert_status(statuses) == overall
    assert uk_parts_from_alert_status(statuses) == parts


def test_regional_does_not_overwrite_national() -> None:
    severity = summarize(2, [4, 3], regional_indicated=True, basis="x")
    assert (severity.overall, severity.regional_max, severity.has_regional_escalation) == (2, 4, True)


def test_regional_not_more_severe() -> None:
    severity = summarize(3, [2], regional_indicated=True, basis="x")
    assert (severity.regional_max, severity.has_regional_escalation) == (2, False)


def test_regional_indicated_but_unparsed_is_unknown() -> None:
    severity = summarize(2, [], regional_indicated=True, basis="x")
    assert severity.regional_max is None
    assert severity.has_regional_escalation is None


def test_no_regional() -> None:
    assert summarize(1, [], regional_indicated=False, basis="x").has_regional_escalation is False


@pytest.mark.parametrize(
    ("label", "category"),
    [
        ("crime", "crime"),
        ("Violent crime", "crime"),
        ("terrorism", "terrorism"),
        ("Terrorist kidnap", "kidnapping"),
        ("civil unrest", "civil_unrest"),
        ("Demonstrations", "civil_unrest"),
        ("Political situation", "civil_unrest"),
        ("armed conflict", "armed_conflict"),
        ("Russia-Ukraine war", "armed_conflict"),
        ("arbitrary detentions", "arbitrary_detention"),
        ("exit bans", "arbitrary_detention"),
        ("wrongful detention", "wrongful_detention"),
        ("risk of wrongful detention", "wrongful_detention"),
        ("health", "health"),
        ("natural disasters", "natural_disaster"),
        ("Earthquakes", "natural_disaster"),
        ("Border areas", "border_security"),
        ("piracy in nearby waters", "maritime"),
        ("Landmines", "landmines"),
        ("Unexploded weapons", "landmines"),
        ("Road safety", None),
        ("Laws and cultural differences", None),
        ("Warnings", None),
    ],
)
def test_categorize(label: str, category: str | None) -> None:
    assert categorize(label) == category


def test_map_labels_unmatched_as_other() -> None:
    assert map_labels(["crime", "traffic safety"], unmatched_as_other=True) == (
        ["crime", "other"],
        ["crime", "traffic safety"],
    )
    assert map_labels(["Road safety", "Terrorism"], unmatched_as_other=False) == (["terrorism"], ["Terrorism"])


def test_vocabulary_is_fixed() -> None:
    assert len(RISK_CATEGORIES) == 13
    assert RISK_CATEGORIES[-1] == "other"


def _adv(code: str, overall: int | None, regional_max: int | None = None) -> SourceAdvisory:
    return SourceAdvisory(
        source_code=code,
        source_name=code,
        source_url="https://example.gov",
        retrieval_url="https://example.gov",
        retrieved_at="2026-01-01T00:00:00Z",
        source_updated_at=None,
        native_level=None,
        native_advice=None,
        normalized_severity=NormalizedSeverity(
            overall=overall, regional_max=regional_max, has_regional_escalation=None, basis="test"
        ),
        risk_categories=[],
        native_risk_labels=[],
        risk_categories_basis="test",
        regional_warnings=[],
    )


def test_comparison_spread_and_disagreement() -> None:
    result = compare([_adv("US", 3), _adv("UK", 1, 3), _adv("CA", 2, 4)])
    assert result.available_severity_values == [3, 1, 2]
    assert (result.lowest_overall_severity, result.highest_overall_severity) == (1, 3)
    assert result.severity_spread == 2
    assert result.material_disagreement is True
    assert result.highest_regional_severity == 4
    assert result.sources_at_highest_overall_severity == ["US"]


def test_comparison_small_spread() -> None:
    result = compare([_adv("US", 3), _adv("UK", 2), _adv("CA", 2)])
    assert (result.severity_spread, result.material_disagreement) == (1, False)


def test_comparison_ties_at_highest() -> None:
    assert compare([_adv("US", 4), _adv("UK", 4), _adv("CA", 4)]).sources_at_highest_overall_severity == [
        "US",
        "UK",
        "CA",
    ]


def test_comparison_needs_two_values() -> None:
    result = compare([_adv("US", 2), _adv("UK", None)])
    assert result.available_severity_values == [2]
    assert result.severity_spread is None
    assert result.material_disagreement is None
    assert result.lowest_overall_severity == result.highest_overall_severity == 2


def test_comparison_empty() -> None:
    result = compare([])
    assert result.available_severity_values == []
    assert result.highest_overall_severity is None
    assert result.highest_regional_severity is None
