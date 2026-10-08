from __future__ import annotations

from collections.abc import Sequence

from ..models.output import Comparison, SourceAdvisory

MATERIAL_DISAGREEMENT_SPREAD = 2


def compare(advisories: Sequence[SourceAdvisory]) -> Comparison:
    overall = [(a.source_code, a.normalized_severity.overall) for a in advisories]
    values = [v for _, v in overall if v is not None]
    regional = [a.normalized_severity.regional_max for a in advisories if a.normalized_severity.regional_max]
    lowest = min(values) if values else None
    highest = max(values) if values else None
    spread = highest - lowest if len(values) >= 2 and highest is not None and lowest is not None else None
    return Comparison(
        available_severity_values=values,
        lowest_overall_severity=lowest,
        highest_overall_severity=highest,
        severity_spread=spread,
        material_disagreement=None if spread is None else spread >= MATERIAL_DISAGREEMENT_SPREAD,
        highest_regional_severity=max(regional) if regional else None,
        sources_at_highest_overall_severity=[code for code, v in overall if v is not None and v == highest],
    )
