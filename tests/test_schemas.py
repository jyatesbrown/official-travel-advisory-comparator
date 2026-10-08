import json
from pathlib import Path

from scripts.export_dataset_schema import build_schema
from src.billing import EVENT_NAME
from src.models.input import ActorInput

ACTOR_DIR = Path(__file__).resolve().parents[1] / ".actor"


def _load(name: str) -> dict:
    return json.loads((ACTOR_DIR / name).read_text("utf-8"))


def test_dataset_schema_matches_model() -> None:
    assert _load("dataset_schema.json") == json.loads(json.dumps(build_schema(), ensure_ascii=False)), (
        "Run python scripts/export_dataset_schema.py"
    )


def test_input_schema_matches_model() -> None:
    schema = _load("input_schema.json")
    assert schema["required"] == ["destination"]
    assert set(schema["properties"]) == {"destination", "sources", "includeRegional"}
    assert schema["properties"]["sources"]["items"]["enum"] == ["US", "UK", "CA"]
    defaults = ActorInput.model_validate({"destination": "x"})
    assert schema["properties"]["sources"]["default"] == defaults.sources
    assert schema["properties"]["includeRegional"]["default"] is defaults.include_regional


def test_actor_json() -> None:
    actor = _load("actor.json")
    assert actor["name"] == "official-travel-advisory-comparator"
    assert actor["usesStandbyMode"] is False
    for key in ("input", "output"):
        assert (ACTOR_DIR / actor[key]).exists()
    assert (ACTOR_DIR / actor["storages"]["dataset"]).exists()


def test_pay_per_event_config() -> None:
    events = _load("pay_per_event.json")["pricingPerEvent"]["actorChargeEvents"]
    assert list(events) == [EVENT_NAME]
    assert events[EVENT_NAME]["eventPriceUsd"] == 0.01
