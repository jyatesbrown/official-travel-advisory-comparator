"""Actor entry point: push-before-charge ordering, one charge per billable lookup, no rerun charge."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src import main as main_module


class FakeStore:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    async def get_value(self, key: str) -> Any:
        return self.values.get(key)

    async def set_value(self, key: str, value: Any) -> None:
        self.values[key] = value


class FakeActor:
    def __init__(self, actor_input: Any, store: FakeStore | None = None) -> None:
        self.input = actor_input
        self.store = store or FakeStore()
        self.events: list[tuple[str, Any]] = []
        self.log = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None)

    async def __aenter__(self) -> FakeActor:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def on(self, *_args: object) -> None:
        return None

    async def open_key_value_store(self) -> FakeStore:
        return self.store

    async def get_input(self) -> Any:
        return self.input

    async def push_data(self, data: Any) -> None:
        self.events.append(("push", data))

    async def charge(self, event_name: str, count: int = 1) -> Any:
        self.events.append(("charge", event_name))
        return SimpleNamespace(event_charge_limit_reached=False)

    async def set_status_message(self, message: str) -> None:
        self.events.append(("status", message))

    async def fail(self, status_message: str) -> None:
        self.events.append(("fail", status_message))

    async def exit(self) -> None:
        return None


def _run(monkeypatch: pytest.MonkeyPatch, actor: FakeActor):
    monkeypatch.setattr(main_module, "Actor", actor)
    return main_module.main()


async def test_billable_lookup_pushes_then_charges_once(monkeypatch, official_sources) -> None:
    actor = FakeActor({"destination": "Trinidad and Tobago"})
    await _run(monkeypatch, actor)
    kinds = [kind for kind, _ in actor.events]
    assert kinds == ["push", "charge", "status"]
    assert actor.events[1] == ("charge", "destination-lookup")
    assert actor.events[0][1]["status"] == "success"
    assert actor.store.values[main_module.STATE_KEY] == {"completed": True, "charged": True}


async def test_partial_lookup_charges_once(monkeypatch, official_sources) -> None:
    import httpx

    official_sources.routes["CA"].mock(return_value=httpx.Response(500))
    actor = FakeActor({"destination": "Kenya"})
    await _run(monkeypatch, actor)
    assert [k for k, _ in actor.events].count("charge") == 1
    assert actor.events[0][1]["status"] == "partial"


@pytest.mark.parametrize("destination", ["Narnia", "Korea"])
async def test_invalid_destination_not_charged(monkeypatch, official_sources, destination: str) -> None:
    actor = FakeActor({"destination": destination})
    await _run(monkeypatch, actor)
    assert [k for k, _ in actor.events] == ["push", "status"]
    assert actor.events[0][1]["status"] == "invalid_destination"


async def test_insufficient_sources_not_charged(monkeypatch, official_sources) -> None:
    import httpx

    official_sources.routes["UK"].mock(return_value=httpx.Response(502))
    official_sources.routes["US"].mock(return_value=httpx.Response(502))
    actor = FakeActor({"destination": "Mexico"})
    await _run(monkeypatch, actor)
    assert [k for k, _ in actor.events] == ["push", "status"]
    assert actor.events[0][1]["status"] == "insufficient_sources"


async def test_restarted_run_does_not_repeat_or_recharge(monkeypatch, official_sources) -> None:
    store = FakeStore()
    await _run(monkeypatch, FakeActor({"destination": "France"}, store))
    second = FakeActor({"destination": "France"}, store)
    await _run(monkeypatch, second)
    assert second.events == []


@pytest.mark.parametrize("bad_input", [None, {}, {"destination": ""}, {"destination": "Kenya", "sources": ["US"]}])
async def test_invalid_input_fails_run_without_charge(monkeypatch, official_sources, bad_input) -> None:
    actor = FakeActor(bad_input)
    await _run(monkeypatch, actor)
    assert [k for k, _ in actor.events] == ["fail"]
    assert official_sources.calls.call_count == 0
