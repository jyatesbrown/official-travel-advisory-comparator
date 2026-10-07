import httpx
import pytest
import respx

from src.utils.errors import ErrorCode, SourceError
from src.utils.http import MAX_ATTEMPTS, USER_AGENT, FetchTrace, create_client, fetch, parse_json_body

URL = "https://example.gov/advisory.json"


@respx.mock
async def test_retries_transient_then_succeeds() -> None:
    route = respx.get(URL).mock(
        side_effect=[httpx.Response(503), httpx.ConnectError("boom"), httpx.Response(200, text="{}")]
    )
    trace = FetchTrace()
    async with create_client() as client:
        response = await fetch(client, URL, accept="application/json", trace=trace)
    assert response.status_code == 200
    assert route.call_count == 3
    assert trace.attempts == 3
    assert trace.http_status == 200
    assert route.calls[0].request.headers["User-Agent"] == USER_AGENT


@respx.mock
async def test_timeouts_exhaust_retries() -> None:
    route = respx.get(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    async with create_client() as client:
        with pytest.raises(SourceError) as info:
            await fetch(client, URL, accept="application/json")
    assert info.value.code is ErrorCode.UPSTREAM_TIMEOUT
    assert route.call_count == MAX_ATTEMPTS


@respx.mock
async def test_404_is_not_found_without_retry() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(404))
    async with create_client() as client:
        with pytest.raises(SourceError) as info:
            await fetch(client, URL, accept="application/json")
    assert info.value.code is ErrorCode.DESTINATION_NOT_FOUND
    assert route.call_count == 1


@respx.mock
async def test_403_is_unavailable_without_retry() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(403, text="cloudflare"))
    async with create_client() as client:
        with pytest.raises(SourceError) as info:
            await fetch(client, URL, accept="application/json")
    assert info.value.code is ErrorCode.UPSTREAM_UNAVAILABLE
    assert route.call_count == 1


@respx.mock
async def test_empty_body_is_format_error() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, text="  "))
    async with create_client() as client:
        with pytest.raises(SourceError) as info:
            await fetch(client, URL, accept="application/json")
    assert info.value.code is ErrorCode.UNEXPECTED_SOURCE_FORMAT


@respx.mock
async def test_redirects_followed() -> None:
    respx.get(URL).mock(return_value=httpx.Response(301, headers={"Location": "https://example.gov/new"}))
    respx.get("https://example.gov/new").mock(return_value=httpx.Response(200, text="{}"))
    async with create_client() as client:
        assert (await fetch(client, URL, accept="application/json")).status_code == 200


@pytest.mark.parametrize("body", ["<!DOCTYPE html><html>challenge</html>", "{not json"])
def test_parse_json_body_rejects_non_json(body: str) -> None:
    with pytest.raises(SourceError) as info:
        parse_json_body(body, url=URL)
    assert info.value.code is ErrorCode.UNEXPECTED_SOURCE_FORMAT
