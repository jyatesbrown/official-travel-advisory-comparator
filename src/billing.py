"""Pure billing rules. Charging itself happens in main.py after the record has been stored."""

from __future__ import annotations

from .models.input import MIN_SOURCES
from .models.output import Billing, LookupStatus

EVENT_NAME = "destination-lookup"


def determine_status(requested: int, succeeded: int) -> LookupStatus:
    if succeeded < MIN_SOURCES:
        return "insufficient_sources"
    if succeeded == requested:
        return "success"
    return "partial"


def is_billable(status: LookupStatus, succeeded: int) -> bool:
    return status in ("success", "partial") and succeeded >= MIN_SOURCES


def billing_decision(status: LookupStatus, succeeded: int) -> Billing:
    if is_billable(status, succeeded):
        return Billing(billable=True, event_name=EVENT_NAME, reason=f"{succeeded} official sources compared")
    if status == "invalid_destination":
        reason = "Destination could not be resolved; not charged"
    else:
        reason = f"Only {succeeded} source(s) succeeded; at least {MIN_SOURCES} are required to charge"
    return Billing(billable=False, event_name=None, reason=reason)
