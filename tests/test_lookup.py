"""Acceptance cases A-G, run against official-source fixtures with HTTP mocked by respx."""

import asyncio
from typing import ClassVar

import httpx
import pytest

from src.lookup import default_adapters, run_lookup
from src.models.input import ActorInput
from src.sources.base import SourceAdapter
from src.sources.uk_fcdo import API_URL as UK_API


def _input(destination: str, **extra) -> ActorInput:
    return ActorInput.model_validate({"destination": destination, **extra})


async def test_a_trinidad_and_tobago_success(official_sources) -> None:
    record = (await run_lookup(_input("Trinidad and Tobago"))).result.to_record()
    assert record["status"] == "success"
    assert record["query"] == {
        "input": "Trinidad and Tobago",
        "canonicalDestination": "Trinidad and Tobago",
        "iso2": "TT",
        "iso3": "TTO",
        "matchMethod": "name",
        "candidates": [],
    }
    assert record["sourcesSucceeded"] == ["US", "UK", "CA"]
    assert record["sourcesFailed"] == []
    assert record["errors"] == []
    by_source = {a["sourceCode"]: a for a in record["advisories"]}
    assert by_source["US"]["sourceUrl"].startswith("https://travel.state.gov/")
    assert by_source["UK"]["sourceUrl"] == "https://www.gov.uk/foreign-travel-advice/trinidad-and-tobago"
    assert by_source["CA"]["sourceUrl"] == "https://travel.gc.ca/destinations/trinidad-and-tobago"
    assert [by_source[c]["normalizedSeverity"]["overall"] for c in ("US", "UK", "CA")] == [3, 1, 2]
    assert by_source["US"]["nativeLevel"] == "Level 3"
    assert by_source["US"]["nativeAdvice"] == "Reconsider Travel"
    assert by_source["CA"]["normalizedSeverity"]["regionalMax"] == 3
    assert record["comparison"]["severitySpread"] == 2
    assert record["comparison"]["materialDisagreement"] is True
    assert record["comparison"]["sourcesAtHighestOverallSeverity"] == ["US"]
    assert record["billing"] == {
        "billable": True,
        "eventName": "destination-lookup",
        "reason": record["billing"]["reason"],
    }


async def test_b_turkey_resolves_to_turkiye(official_sources) -> None:
    result = (await run_lookup(_input("Turkey"))).result
    assert result.query.input == "Turkey"
    assert result.query.canonical_destination == "Türkiye"
    assert (result.query.iso2, result.query.iso3) == ("TR", "TUR")
    assert result.status == "success"
    assert official_sources.routes["UK"].calls.last.request.url.path.endswith("/turkey")


@pytest.mark.parametrize("query", ["Côte d'Ivoire", "Côte d’Ivoire", "Ivory Coast", "cote d'ivoire"])
async def test_c_cote_divoire_with_accents(official_sources, query: str) -> None:
    result = (await run_lookup(_input(query))).result
    assert result.query.canonical_destination == "Côte d'Ivoire"
    assert result.query.iso2 == "CI"
    assert result.status == "success"
    assert official_sources.routes["UK"].calls.last.request.url.path.endswith("/cote-d-ivoire")


@pytest.mark.parametrize("query", ["Narnia", "Congo"])
async def test_d_unknown_destination_not_guessed(official_sources, query: str) -> None:
    record = (await run_lookup(_input(query))).result.to_record()
    assert record["status"] == "invalid_destination"
    assert record["query"]["canonicalDestination"] is None
    assert record["advisories"] == []
    assert record["errors"][0]["errorCode"] == "INVALID_DESTINATION"
    assert record["billing"]["billable"] is False
    assert official_sources.calls.call_count == 0


async def test_d_ambiguous_lists_candidates(official_sources) -> None:
    record = (await run_lookup(_input("Congo"))).result.to_record()
    assert record["query"]["candidates"] == ["Democratic Republic of the Congo", "Republic of the Congo"]


async def test_e_one_source_times_out_partial_billable(official_sources) -> None:
    official_sources.routes["UK"].mock(side_effect=httpx.ReadTimeout("slow"))
    result = (await run_lookup(_input("Kenya"))).result
    assert result.status == "partial"
    assert result.sources_succeeded == ["US", "CA"]
    assert result.sources_failed == ["UK"]
    assert result.errors[0].error_code == "UPSTREAM_TIMEOUT"
    assert result.errors[0].retryable is True
    assert result.billing.billable is True
    assert result.comparison.available_severity_values == [2, 2]


class _HangingAdapter(SourceAdapter):
    code: ClassVar = "UK"
    name: ClassVar = "U.K. FCDO"

    async def fetch_advisory(self, destination, client, *, include_regional=True, trace=None):
        await asyncio.sleep(10)
        raise AssertionError("unreachable")


async def test_e_hung_source_does_not_block_others(official_sources) -> None:
    adapters = {**default_adapters(), "UK": _HangingAdapter()}
    outcome = await run_lookup(_input("Mexico"), adapters=adapters, deadline=0.2)
    assert outcome.result.status == "partial"
    assert outcome.result.errors[0].error_code == "UPSTREAM_TIMEOUT"
    assert outcome.elapsed_ms < 2000


async def test_f_two_failures_insufficient_not_billable(official_sources) -> None:
    official_sources.routes["UK"].mock(return_value=httpx.Response(503))
    official_sources.routes["CA"].mock(side_effect=httpx.ConnectError("down"))
    record = (await run_lookup(_input("France"))).result.to_record()
    assert record["status"] == "insufficient_sources"
    assert record["sourcesSucceeded"] == ["US"]
    assert {e["sourceCode"]: e["errorCode"] for e in record["errors"]} == {
        "UK": "UPSTREAM_UNAVAILABLE",
        "CA": "UPSTREAM_UNAVAILABLE",
    }
    assert record["billing"]["billable"] is False
    assert record["comparison"]["severitySpread"] is None


@pytest.mark.parametrize(
    ("source", "response"),
    [
        ("UK", httpx.Response(200, text="<!DOCTYPE html><html><body>Just a moment...</body></html>")),
        ("UK", httpx.Response(200, json={"schema_name": "guide", "details": {}})),
        ("CA", httpx.Response(200, json={"data": {"country-iso": "TT", "eng": {}}})),
        ("US", httpx.Response(200, text="<html><body>Access denied</body></html>")),
    ],
)
async def test_g_unexpected_format_is_controlled(official_sources, source: str, response: httpx.Response) -> None:
    official_sources.routes[source].mock(return_value=response)
    record = (await run_lookup(_input("Trinidad and Tobago"))).result.to_record()
    assert record["status"] == "partial"
    assert record["sourcesFailed"] == [source]
    assert record["errors"][0]["errorCode"] in {"UNEXPECTED_SOURCE_FORMAT", "PARSER_FAILED"}
    assert source not in [a["sourceCode"] for a in record["advisories"]]
    assert "Traceback" not in str(record)


async def test_destination_missing_from_one_source(official_sources) -> None:
    result = (await run_lookup(_input("Cuba"))).result
    assert "CA" in result.sources_failed
    assert result.errors[0].error_code == "DESTINATION_NOT_FOUND"
    assert result.errors[0].retryable is False


async def test_source_subset_and_regional_off(official_sources) -> None:
    result = (await run_lookup(_input("Colombia", sources=["UK", "CA"], includeRegional=False))).result
    assert result.sources_requested == ["UK", "CA"]
    assert result.status == "success"
    assert official_sources.routes["US"].call_count == 0
    assert all(a.regional_warnings is None for a in result.advisories)
    assert all(a.normalized_severity.regional_max is not None for a in result.advisories)


async def test_exactly_one_request_per_source(official_sources) -> None:
    await run_lookup(_input("Ukraine"))
    assert [official_sources.routes[c].call_count for c in ("US", "UK", "CA")] == [1, 1, 1]
    assert official_sources.routes["UK"].calls.last.request.url == UK_API.format(slug="ukraine")
