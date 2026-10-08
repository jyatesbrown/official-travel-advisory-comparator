from __future__ import annotations

from collections.abc import Sequence

from ..models.input import SourceCode
from ..models.output import Comparison, ComparisonRegionalCoverage, RegionalWarningConclusion, SourceAdvisory

MATERIAL_DISAGREEMENT_SPREAD = 2


def compare(advisories: Sequence[SourceAdvisory], requested: Sequence[SourceCode] | None = None) -> Comparison:
    overall = [(a.source_code, a.normalized_severity.overall) for a in advisories]
    values = [v for _, v in overall if v is not None]
    lowest = min(values) if values else None
    highest = max(values) if values else None
    spread = highest - lowest if len(values) >= 2 and highest is not None and lowest is not None else None

    known = [a for a in advisories if a.regional_coverage != "unavailable"]
    unknown = [a.source_code for a in advisories if a.regional_coverage == "unavailable"]
    warned = [a for a in known if a.normalized_severity.regional_max is not None]
    status = "complete" if known and not unknown else "partial" if known else "unavailable"
    conclusion: RegionalWarningConclusion = (
        "warnings_reported"
        if warned
        else "none_reported"
        if status == "complete"
        else "unknown_due_to_incomplete_coverage"
    )
    requested_codes = set(requested) if requested is not None else {a.source_code for a in advisories}
    regional = [a.normalized_severity.regional_max for a in warned if a.normalized_severity.regional_max]

    return Comparison(
        available_severity_values=values,
        lowest_overall_severity=lowest,
        highest_overall_severity=highest,
        severity_spread=spread,
        material_disagreement=None if spread is None else spread >= MATERIAL_DISAGREEMENT_SPREAD,
        highest_regional_severity=max(regional) if regional else None,
        regional_coverage=ComparisonRegionalCoverage(
            status=status,
            sources_available=[a.source_code for a in known],
            sources_unavailable=unknown,
            all_requested_sources_known=status == "complete" and requested_codes <= {a.source_code for a in known},
        ),
        regional_warning_conclusion=conclusion,
        sources_with_regional_warnings=[a.source_code for a in warned],
        sources_at_highest_overall_severity=[code for code, v in overall if v is not None and v == highest],
    )
