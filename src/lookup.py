"""Orchestrates one destination lookup: resolve, fetch sources concurrently, normalise, compare."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, field

import httpx

from .billing import billing_decision, determine_status
from .destinations.resolver import Destination, DestinationResolver, get_resolver
from .models.input import ActorInput, SourceCode
from .models.output import LookupError_, LookupResult, QueryInfo, SourceAdvisory
from .normalization.comparison import compare
from .sources.base import SourceAdapter
from .sources.canada import CanadaAdapter
from .sources.uk_fcdo import UkFcdoAdapter
from .sources.us_state import UsStateAdapter
from .utils.dates import to_iso, utc_now
from .utils.errors import FORMAT_DRIFT_CODES, ErrorCode, SourceError, public_message
from .utils.http import FetchTrace, create_client

log = logging.getLogger("apify.lookup")

SOURCE_DEADLINE_SECONDS = 20.0


@dataclass
class SourceRun:
    code: SourceCode
    advisory: SourceAdvisory | None
    error: SourceError | None
    trace: FetchTrace
    elapsed_ms: float


@dataclass
class LookupOutcome:
    result: LookupResult
    runs: dict[SourceCode, SourceRun] = field(default_factory=dict)
    elapsed_ms: float = 0.0


def default_adapters(resolver: DestinationResolver | None = None) -> dict[SourceCode, SourceAdapter]:
    return {"US": UsStateAdapter(resolver), "UK": UkFcdoAdapter(), "CA": CanadaAdapter()}


async def _run_source(
    adapter: SourceAdapter,
    destination: Destination,
    client: httpx.AsyncClient,
    *,
    include_regional: bool,
    deadline: float,
) -> SourceRun:
    trace = FetchTrace()
    started = time.perf_counter()
    advisory: SourceAdvisory | None = None
    error: SourceError | None = None
    try:
        advisory = await asyncio.wait_for(
            adapter.fetch_advisory(destination, client, include_regional=include_regional, trace=trace),
            timeout=deadline,
        )
    except TimeoutError:
        error = SourceError(ErrorCode.UPSTREAM_TIMEOUT, f"{adapter.code} exceeded {deadline}s deadline")
    except SourceError as exc:
        error = exc
    except Exception as exc:
        log.exception("%s adapter raised an unexpected exception", adapter.code)
        error = SourceError(ErrorCode.PARSER_FAILED, f"{type(exc).__name__}: {exc}")
    elapsed = round((time.perf_counter() - started) * 1000, 1)
    if error is None:
        log.info("%s ok in %.0f ms (HTTP %s, %d attempt(s))", adapter.code, elapsed, trace.http_status, trace.attempts)
    elif error.code in FORMAT_DRIFT_CODES:
        log.warning(
            "SOURCE FORMAT DRIFT: %s %s for %s: %s. The parser needs maintenance.",
            adapter.code,
            error.code,
            destination.iso2,
            error.detail,
        )
    else:
        log.warning("%s failed with %s in %.0f ms: %s", adapter.code, error.code, elapsed, error.detail)
    return SourceRun(adapter.code, advisory, error, trace, elapsed)


async def run_lookup(
    actor_input: ActorInput,
    *,
    adapters: Mapping[SourceCode, SourceAdapter] | None = None,
    client: httpx.AsyncClient | None = None,
    resolver: DestinationResolver | None = None,
    deadline: float = SOURCE_DEADLINE_SECONDS,
) -> LookupOutcome:
    started = time.perf_counter()
    resolver = resolver or get_resolver()
    checked_at = to_iso(utc_now())
    requested = list(actor_input.sources)
    resolution = resolver.resolve(actor_input.destination)

    if resolution.destination is None:
        status = "invalid_destination"
        result = LookupResult(
            status=status,
            query=QueryInfo(
                input=actor_input.destination,
                canonical_destination=None,
                iso2=None,
                iso3=None,
                match_method=None,
                candidates=list(resolution.candidates),
            ),
            checked_at=checked_at,
            sources_requested=requested,
            sources_succeeded=[],
            sources_failed=[],
            errors=[
                LookupError_(
                    source_code=None,
                    error_code=ErrorCode.INVALID_DESTINATION,
                    message=public_message(ErrorCode.INVALID_DESTINATION)
                    + (" Candidates: " + ", ".join(resolution.candidates) + "." if resolution.candidates else ""),
                    retryable=False,
                )
            ],
            advisories=[],
            comparison=None,
            billing=billing_decision(status, 0),
        )
        log.info("Destination %r not resolved (%s)", actor_input.destination, resolution.reason)
        return LookupOutcome(result, {}, round((time.perf_counter() - started) * 1000, 1))

    destination = resolution.destination
    adapters = adapters or default_adapters(resolver)
    own_client = client is None
    http = client or create_client()
    try:
        runs = await asyncio.gather(
            *(
                _run_source(
                    adapters[code],
                    destination,
                    http,
                    include_regional=actor_input.include_regional,
                    deadline=deadline,
                )
                for code in requested
            )
        )
    finally:
        if own_client:
            await http.aclose()

    advisories = [run.advisory for run in runs if run.advisory is not None]
    failed = [run for run in runs if run.error is not None]
    status = determine_status(len(requested), len(advisories))
    result = LookupResult(
        status=status,
        query=QueryInfo(
            input=actor_input.destination,
            canonical_destination=destination.name,
            iso2=destination.iso2,
            iso3=destination.iso3,
            match_method=resolution.method,
        ),
        checked_at=checked_at,
        sources_requested=requested,
        sources_succeeded=[a.source_code for a in advisories],
        sources_failed=[run.code for run in failed],
        errors=[
            LookupError_(
                source_code=run.code,
                error_code=run.error.code,
                message=public_message(run.error.code, adapters[run.code].name),
                retryable=run.error.retryable,
            )
            for run in failed
            if run.error is not None
        ],
        advisories=advisories,
        comparison=compare(advisories, requested),
        billing=billing_decision(status, len(advisories)),
    )
    return LookupOutcome(result, {run.code: run for run in runs}, round((time.perf_counter() - started) * 1000, 1))
