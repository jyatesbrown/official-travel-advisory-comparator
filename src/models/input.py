from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SourceCode = Literal["US", "UK", "CA"]
ALL_SOURCES: tuple[SourceCode, ...] = ("US", "UK", "CA")
MIN_SOURCES = 2

SOURCE_ALIASES: dict[str, SourceCode] = {
    **dict.fromkeys(("us", "usa", "u.s.", "united states", "state department"), "US"),
    **dict.fromkeys(("uk", "u.k.", "fcdo", "united kingdom", "gov.uk"), "UK"),
    **dict.fromkeys(("ca", "can", "canada", "travel.gc.ca"), "CA"),
}


def normalize_source(value: object) -> object:
    """Map a case-insensitive source alias to its canonical code; unknown values pass through to fail validation."""
    if not isinstance(value, str):
        return value
    return SOURCE_ALIASES.get(" ".join(value.split()).lower(), value)


class ActorInput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    destination: str = Field(min_length=1, max_length=100)
    sources: list[SourceCode] = Field(default_factory=lambda: list(ALL_SOURCES))
    include_regional: bool = Field(default=True, alias="includeRegional")

    @field_validator("destination")
    @classmethod
    def _strip_destination(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("destination must not be blank")
        return value

    @field_validator("sources", mode="before")
    @classmethod
    def _canonical_sources(cls, value: object) -> object:
        return [normalize_source(v) for v in value] if isinstance(value, list) else value

    @field_validator("sources")
    @classmethod
    def _dedupe_sources(cls, value: list[SourceCode]) -> list[SourceCode]:
        unique = list(dict.fromkeys(value))
        if len(unique) < MIN_SOURCES:
            raise ValueError(f"at least {MIN_SOURCES} distinct sources are required for a comparison")
        return [code for code in ALL_SOURCES if code in unique]
