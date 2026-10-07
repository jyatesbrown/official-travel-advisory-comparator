from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SourceCode = Literal["US", "UK", "CA"]
ALL_SOURCES: tuple[SourceCode, ...] = ("US", "UK", "CA")
MIN_SOURCES = 2


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

    @field_validator("sources")
    @classmethod
    def _dedupe_sources(cls, value: list[SourceCode]) -> list[SourceCode]:
        unique = list(dict.fromkeys(value))
        if len(unique) < MIN_SOURCES:
            raise ValueError(f"at least {MIN_SOURCES} distinct sources are required for a comparison")
        return [code for code in ALL_SOURCES if code in unique]
