from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from ..utils.errors import ErrorCode
from .input import SourceCode

SCHEMA_VERSION = "1.1"

Severity = Annotated[int, Field(ge=1, le=4)]
LookupStatus = Literal["success", "partial", "insufficient_sources", "invalid_destination"]
MatchMethod = Literal["name", "alias", "iso_code", "fuzzy"]
RegionalCoverage = Literal["available", "unavailable", "not_applicable"]
NativeScaleType = Literal["numbered", "categorical"]

_SEVERITY_SCALE = (
    "1 normal precautions, 2 increased caution, 3 avoid non-essential/reconsider travel, 4 avoid all travel"
)
NORMALIZED_SCALE_NOTE = (
    "Internal cross-source normalization used by this Actor for comparison "
    f"({_SEVERITY_SCALE}). Not necessarily the source government's native advisory level; "
    "see nativeLevel, nativeAdvice and nativeScale for the official terminology."
)


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    def to_record(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True)


class NormalizedSeverity(_Model):
    overall: Severity | None = Field(
        description=(
            "National advisory on the Actor's internal cross-source 1-4 scale "
            f"({_SEVERITY_SCALE}). Not necessarily the government's native level. Null if not mappable."
        )
    )
    regional_max: Severity | None = Field(
        description=(
            "Highest regional (sub-national) severity on the Actor's internal 1-4 scale. Null when no regional "
            "warning is known, including when regionalCoverage is 'unavailable' (unknown, not 'none')."
        )
    )
    has_regional_escalation: bool | None = Field(
        description=(
            "True if some region is rated more severe than the national level; null if unknown "
            "(always null when regionalCoverage is 'unavailable')."
        )
    )
    basis: str = Field(description="How the normalized value was derived from the source's native value.")
    scale_note: str = Field(
        default=NORMALIZED_SCALE_NOTE,
        description="Reminder that these values are the Actor's internal normalization, not native levels.",
    )


class NativeScale(_Model):
    type: NativeScaleType = Field(
        description="'numbered' if the government publishes numbered levels, otherwise 'categorical'."
    )
    description: str = Field(description="How this government expresses its own advisory levels.")


class RegionalWarning(_Model):
    region: str = Field(description="Region name as published by the source (heading or advice text).")
    native_advice: str = Field(description="The source's own advice wording for this region.")
    normalized_severity: Severity | None = Field(description="Regional advice on the shared 1-4 scale.")
    native_details: list[str] = Field(
        default_factory=list,
        description="Verbatim supporting text/bullets from the source (areas included or excepted).",
    )


class SourceAdvisory(_Model):
    source_code: SourceCode = Field(description="US, UK or CA.")
    source_name: str = Field(description="Issuing government body.")
    source_url: str = Field(description="Official human-readable advisory page.")
    retrieval_url: str = Field(description="Official machine-readable URL actually fetched.")
    retrieved_at: str = Field(description="ISO-8601 UTC time the source was fetched.")
    source_updated_at: str | None = Field(description="Source's own last-updated date/time (ISO-8601) if published.")
    native_level: str | None = Field(
        description=(
            "Native level identifier: US 'Level N', UK GOV.UK alert_status codes, CA advisory-state "
            "(an internal feed code, not a public Canadian level number)."
        )
    )
    native_advice: str | None = Field(
        description="Native national advice wording; null when the source issues no national statement (UK)."
    )
    native_scale: NativeScale = Field(description="The government's own advisory scale (numbered or categorical).")
    normalized_severity: NormalizedSeverity
    risk_categories: list[str] = Field(description="Controlled-vocabulary risk categories (deterministic mapping).")
    native_risk_labels: list[str] = Field(description="Source labels/headings that produced the risk categories.")
    risk_categories_basis: str = Field(description="Which part of the source the risk categories come from.")
    regional_coverage: RegionalCoverage = Field(
        description=(
            "'available': the source data was sufficient to determine regional-warning status; "
            "'unavailable': this source/adapter does not provide enough regional detail, so regional status is "
            "unknown; 'not_applicable': regional breakdown does not apply to this destination."
        )
    )
    regional_coverage_note: str | None = Field(
        description="Deterministic note explaining regionalCoverage or omitted regional warnings; null if none."
    )
    regional_warnings: list[RegionalWarning] | None = Field(
        description=(
            "Regional warnings. [] means the source was checked and lists no regional warnings. "
            "null means unknown/unavailable (regionalCoverage 'unavailable') or omitted (includeRegional false)."
        )
    )


class LookupError_(_Model):
    source_code: SourceCode | None = Field(description="Failed source, or null for destination errors.")
    error_code: ErrorCode = Field(description="Controlled error code.")
    message: str = Field(description="Public error message (no stack traces).")
    retryable: bool = Field(description="Whether retrying later may succeed.")


class QueryInfo(_Model):
    input: str = Field(description="Destination exactly as supplied.")
    canonical_destination: str | None = Field(description="Canonical English destination name.")
    iso2: str | None = Field(description="ISO 3166-1 alpha-2 code (XK for Kosovo).")
    iso3: str | None = Field(description="ISO 3166-1 alpha-3 code.")
    match_method: MatchMethod | None = Field(description="How the input was resolved.")
    candidates: list[str] = Field(default_factory=list, description="Possible matches when the input is ambiguous.")


class Comparison(_Model):
    available_severity_values: list[int] = Field(description="Normalized overall severities, in source order.")
    lowest_overall_severity: Severity | None
    highest_overall_severity: Severity | None
    severity_spread: int | None = Field(description="max - min overall severity; null with fewer than two values.")
    material_disagreement: bool | None = Field(description="True when severitySpread >= 2; null if not computable.")
    highest_regional_severity: Severity | None = Field(description="Highest regionalMax across sources.")
    sources_at_highest_overall_severity: list[SourceCode]


class Billing(_Model):
    billable: bool = Field(description="Whether this lookup is charged (one destination-lookup event).")
    event_name: str | None = Field(description="Pay-per-event name charged, if billable.")
    reason: str


class LookupResult(_Model):
    schema_version: str = Field(default=SCHEMA_VERSION, description="Record schema version.")
    status: LookupStatus = Field(
        description="success: all sources ok; partial: >=2 ok, some failed; insufficient_sources: <2 ok; "
        "invalid_destination: input not resolved."
    )
    query: QueryInfo
    checked_at: str = Field(description="ISO-8601 UTC time of the lookup.")
    sources_requested: list[SourceCode]
    sources_succeeded: list[SourceCode]
    sources_failed: list[SourceCode]
    errors: list[LookupError_]
    advisories: list[SourceAdvisory]
    comparison: Comparison | None = Field(description="Cross-source comparison; null for invalid destinations.")
    billing: Billing
