import pytest
from pydantic import ValidationError

from src.billing import EVENT_NAME, billing_decision, determine_status, is_billable
from src.models.input import ActorInput
from src.models.output import LookupError_
from src.utils.errors import ErrorCode, SourceError, public_message


@pytest.mark.parametrize(
    ("requested", "succeeded", "status"),
    [
        (3, 3, "success"),
        (2, 2, "success"),
        (3, 2, "partial"),
        (3, 1, "insufficient_sources"),
        (3, 0, "insufficient_sources"),
        (2, 1, "insufficient_sources"),
    ],
)
def test_status(requested: int, succeeded: int, status: str) -> None:
    assert determine_status(requested, succeeded) == status


@pytest.mark.parametrize(
    ("status", "succeeded", "billable"),
    [
        ("success", 3, True),
        ("success", 2, True),
        ("partial", 2, True),
        ("insufficient_sources", 1, False),
        ("insufficient_sources", 0, False),
        ("invalid_destination", 0, False),
        ("partial", 1, False),
    ],
)
def test_billable(status: str, succeeded: int, billable: bool) -> None:
    assert is_billable(status, succeeded) is billable
    decision = billing_decision(status, succeeded)
    assert decision.billable is billable
    assert decision.event_name == (EVENT_NAME if billable else None)


def test_event_name() -> None:
    assert EVENT_NAME == "destination-lookup"


def test_input_defaults() -> None:
    parsed = ActorInput.model_validate({"destination": " Kenya "})
    assert parsed.destination == "Kenya"
    assert parsed.sources == ["US", "UK", "CA"]
    assert parsed.include_regional is True


def test_input_sources_deduped_and_ordered() -> None:
    parsed = ActorInput.model_validate(
        {"destination": "Kenya", "sources": ["CA", "US", "CA"], "includeRegional": False}
    )
    assert parsed.sources == ["US", "CA"]
    assert parsed.include_regional is False


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"destination": ""},
        {"destination": "   "},
        {"destination": "Kenya", "sources": ["US"]},
        {"destination": "Kenya", "sources": ["US", "FR"]},
        {"destination": "x" * 101},
    ],
)
def test_input_rejected(raw: dict) -> None:
    with pytest.raises(ValidationError):
        ActorInput.model_validate(raw)


def test_unknown_input_fields_ignored() -> None:
    assert ActorInput.model_validate({"destination": "Kenya", "timeout": 3}).destination == "Kenya"


def test_error_serialisation_has_no_internal_detail() -> None:
    error = SourceError(ErrorCode.UPSTREAM_TIMEOUT, "internal: https://x ReadTimeout traceback")
    record = LookupError_(
        source_code="UK", error_code=error.code, message=public_message(error.code, "FCDO"), retryable=error.retryable
    ).to_record()
    assert record == {
        "sourceCode": "UK",
        "errorCode": "UPSTREAM_TIMEOUT",
        "message": "FCDO source did not respond in time.",
        "retryable": True,
    }


def test_not_found_is_not_retryable() -> None:
    assert SourceError(ErrorCode.DESTINATION_NOT_FOUND, "x").retryable is False
    assert SourceError(ErrorCode.UNEXPECTED_SOURCE_FORMAT, "x").retryable is False
