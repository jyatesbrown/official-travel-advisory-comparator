from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import ClassVar

import httpx

from ..destinations.resolver import Destination
from ..models.input import SourceCode
from ..models.output import RegionalWarning, SourceAdvisory
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


def regional_output(include_regional: bool, warnings: list[RegionalWarning]) -> list[RegionalWarning] | None:
    return warnings if include_regional else None
