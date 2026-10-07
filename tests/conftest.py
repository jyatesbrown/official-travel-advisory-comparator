from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from src.destinations.resolver import Destination, get_resolver
from src.sources import canada, uk_fcdo, us_state
from src.utils import http as http_utils

FIXTURES = Path(__file__).parent / "fixtures"


def load_json(relative: str) -> Any:
    return json.loads((FIXTURES / relative).read_text(encoding="utf-8"))


def load_text(relative: str) -> str:
    return (FIXTURES / relative).read_text(encoding="utf-8")


def dest(query: str) -> Destination:
    resolution = get_resolver().resolve(query)
    assert resolution.destination is not None, query
    return resolution.destination


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http_utils, "BACKOFF_BASE_SECONDS", 0.0)


@pytest.fixture(scope="session")
def us_feed_text() -> str:
    return load_text("us/TAsTWs.xml")


@pytest.fixture(scope="session")
def us_items(us_feed_text: str) -> list[us_state.FeedItem]:
    return us_state.parse_feed(us_feed_text)


@pytest.fixture
def official_sources(us_feed_text: str):
    """Serve every official endpoint from fixtures; unknown destinations get HTTP 404."""

    def uk_route(request: httpx.Request) -> httpx.Response:
        slug = request.url.path.rsplit("/", 1)[-1]
        path = FIXTURES / "uk" / f"{slug}.json"
        return httpx.Response(200, text=path.read_text("utf-8")) if path.exists() else httpx.Response(404)

    def ca_route(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        path = FIXTURES / "ca" / name
        return httpx.Response(200, text=path.read_text("utf-8")) if path.exists() else httpx.Response(404)

    with respx.mock(assert_all_called=False) as router:
        router.get(us_state.FEED_URL, name="US").mock(return_value=httpx.Response(200, text=us_feed_text))
        router.get(url__startswith=uk_fcdo.API_URL.split("{")[0], name="UK").mock(side_effect=uk_route)
        router.get(url__startswith=canada.API_URL.split("{")[0], name="CA").mock(side_effect=ca_route)
        yield router
