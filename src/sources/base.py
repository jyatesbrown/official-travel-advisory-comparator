from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, ClassVar

import httpx

from ..destinations.resolver import Destination
from ..models.input import SourceCode
from ..models.output import RegionalCoverage, RegionalWarning, SourceAdvisory
from ..utils.http import FetchTrace

log = logging.getLogger("apify.sources")


class SourceAdapter(ABC):
    code: ClassVar[SourceCode]
    name: ClassVar[str]

    @abstractmethod
    async def fetch_advisory(
        self,
        destination: Destination,
        client: httpx.AsyncClient,
        *,
        include_regional: bool = True,
        trace: FetchTrace | None = None,
    ) -> SourceAdvisory:
        """Fetch and normalise one destination's advisory or raise `SourceError`."""


REGIONAL_OMITTED_NOTE = "Regional warning list omitted because includeRegional is false."


def regional_output(
    include_regional: bool,
    coverage: RegionalCoverage,
    warnings: list[RegionalWarning],
    note: str | None = None,
) -> dict[str, Any]:
    """SourceAdvisory regional fields: warnings are null unless coverage is known and they were requested."""
    if coverage != "available":
        return {"regional_coverage": coverage, "regional_coverage_note": note, "regional_warnings": None}
    if not include_regional:
        return {
            "regional_coverage": coverage,
            "regional_coverage_note": note or REGIONAL_OMITTED_NOTE,
            "regional_warnings": None,
        }
    return {"regional_coverage": coverage, "regional_coverage_note": note, "regional_warnings": warnings}
