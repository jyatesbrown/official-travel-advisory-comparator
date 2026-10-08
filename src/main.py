"""Apify Actor entry point: one destination in, one normalised comparison record out."""

from __future__ import annotations

from apify import Actor, Event
from pydantic import ValidationError

from .billing import EVENT_NAME
from .lookup import LookupOutcome, run_lookup
from .models.input import ActorInput

STATE_KEY = "LOOKUP_STATE"


def _status_message(outcome: LookupOutcome) -> str:
    result = outcome.result
    if result.status == "invalid_destination":
        return f"invalid_destination: could not resolve {result.query.input!r}"
    levels = ", ".join(f"{a.source_code} {a.normalized_severity.overall}" for a in result.advisories)
    return f"{result.status}: {result.query.canonical_destination} ({levels or 'no sources'})"


def _input_error(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, e['loc'])) or 'input'}: {e['msg']}" for e in exc.errors())


async def _on_aborting(_event_data: object) -> None:
    Actor.log.info("Run is aborting; exiting without charging.")
    await Actor.exit()


async def main() -> None:
    async with Actor:
        Actor.on(Event.ABORTING, _on_aborting)
        store = await Actor.open_key_value_store()
        state = await store.get_value(STATE_KEY) or {}
        if state.get("completed"):
            Actor.log.info("Lookup already completed in this run; not repeating it or charging again.")
            return

        try:
            actor_input = ActorInput.model_validate(await Actor.get_input() or {})
        except ValidationError as exc:
            await Actor.fail(status_message=f"Invalid input: {_input_error(exc)}")
            return

        outcome = await run_lookup(actor_input)
        result = outcome.result
        await Actor.push_data(result.to_record())
        await store.set_value(STATE_KEY, {"completed": True, "charged": False})
        Actor.log.info("Lookup %s in %.0f ms", result.status, outcome.elapsed_ms)

        if result.billing.billable:
            charge = await Actor.charge(event_name=EVENT_NAME)
            await store.set_value(STATE_KEY, {"completed": True, "charged": True})
            if charge.event_charge_limit_reached:
                Actor.log.info("Charge limit reached; result was delivered before the limit applied.")
        await Actor.set_status_message(_status_message(outcome))
