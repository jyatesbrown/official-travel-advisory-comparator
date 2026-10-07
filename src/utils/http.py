from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .errors import ErrorCode, SourceError

USER_AGENT = (
    "OfficialTravelAdvisoryComparator/1.0 "
    "(Apify Actor; +https://github.com/jyatesbrown/official-travel-advisory-comparator)"
)
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 0.5
BACKOFF_MAX_SECONDS = 2.0
TRANSIENT_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


@dataclass
class FetchTrace:
    """Developer diagnostics for one source fetch (not part of the public record)."""

    url: str | None = None
    http_status: int | None = None
    attempts: int = 0
    elapsed_ms: float | None = None


def create_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en"},
        timeout=TIMEOUT,
        follow_redirects=True,
        max_redirects=5,
    )


def backoff_delay(attempt: int) -> float:
    return min(BACKOFF_BASE_SECONDS * 2 ** (attempt - 1), BACKOFF_MAX_SECONDS)


async def fetch(
    client: httpx.AsyncClient,
    url: str,
    *,
    accept: str,
    trace: FetchTrace | None = None,
    not_found_code: ErrorCode = ErrorCode.DESTINATION_NOT_FOUND,
) -> httpx.Response:
    """GET `url` with bounded retries on transient failures; raise `SourceError` otherwise."""
    trace = trace if trace is not None else FetchTrace()
    trace.url = url
    started = time.perf_counter()
    last_error: SourceError | None = None
    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            trace.attempts = attempt
            try:
                response = await client.get(url, headers={"Accept": accept})
            except httpx.TimeoutException as exc:
                last_error = SourceError(ErrorCode.UPSTREAM_TIMEOUT, f"{url}: {type(exc).__name__}")
            except httpx.HTTPError as exc:
                last_error = SourceError(ErrorCode.UPSTREAM_UNAVAILABLE, f"{url}: {type(exc).__name__}: {exc}")
            else:
                status = response.status_code
                trace.http_status = status
                if status in (404, 410):
                    raise SourceError(not_found_code, f"{url}: HTTP {status}")
                if status in TRANSIENT_STATUSES:
                    last_error = SourceError(ErrorCode.UPSTREAM_UNAVAILABLE, f"{url}: HTTP {status}")
                elif status >= 400:
                    raise SourceError(ErrorCode.UPSTREAM_UNAVAILABLE, f"{url}: HTTP {status}")
                elif not response.content.strip():
                    raise SourceError(ErrorCode.UNEXPECTED_SOURCE_FORMAT, f"{url}: empty body")
                else:
                    return response
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(backoff_delay(attempt))
        assert last_error is not None
        raise last_error
    finally:
        trace.elapsed_ms = round((time.perf_counter() - started) * 1000, 1)


def parse_json_body(text: str, *, url: str) -> Any:
    stripped = text.lstrip()
    if not stripped.startswith(("{", "[")):
        raise SourceError(ErrorCode.UNEXPECTED_SOURCE_FORMAT, f"{url}: body is not JSON (starts {stripped[:40]!r})")
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise SourceError(ErrorCode.UNEXPECTED_SOURCE_FORMAT, f"{url}: invalid JSON: {exc}") from exc
