"""Regenerate .actor/dataset_schema.json from the Pydantic output model (single source of truth)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.models.output import LookupResult  # noqa: E402

SCHEMA_PATH = ROOT / ".actor" / "dataset_schema.json"


def _inline(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        if "$ref" in node:
            return _inline(defs[node["$ref"].rsplit("/", 1)[-1]], defs)
        return {k: _inline(v, defs) for k, v in node.items() if k != "title"}
    if isinstance(node, list):
        return [_inline(v, defs) for v in node]
    return node


def build_fields() -> dict[str, Any]:
    schema = LookupResult.model_json_schema(by_alias=True, mode="serialization")
    defs = schema.pop("$defs", {})
    return _inline(schema, defs)


def build_schema() -> dict[str, Any]:
    return {
        "actorSpecification": 1,
        "fields": build_fields(),
        "views": {
            "overview": {
                "title": "Overview",
                "description": "Destination, status and cross-government severity comparison.",
                "transformation": {
                    "flatten": ["query", "comparison", "billing"],
                    "fields": [
                        "query.canonicalDestination",
                        "status",
                        "comparison.availableSeverityValues",
                        "comparison.severitySpread",
                        "comparison.materialDisagreement",
                        "comparison.highestRegionalSeverity",
                        "sourcesSucceeded",
                        "sourcesFailed",
                        "billing.billable",
                        "checkedAt",
                    ],
                },
                "display": {
                    "component": "table",
                    "properties": {
                        "query.canonicalDestination": {"label": "Destination", "format": "text"},
                        "status": {"label": "Status", "format": "text"},
                        "comparison.availableSeverityValues": {"label": "Severities (1-4)", "format": "array"},
                        "comparison.severitySpread": {"label": "Spread", "format": "number"},
                        "comparison.materialDisagreement": {"label": "Material disagreement", "format": "boolean"},
                        "comparison.highestRegionalSeverity": {"label": "Highest regional", "format": "number"},
                        "sourcesSucceeded": {"label": "Sources OK", "format": "array"},
                        "sourcesFailed": {"label": "Sources failed", "format": "array"},
                        "billing.billable": {"label": "Billable", "format": "boolean"},
                        "checkedAt": {"label": "Checked at", "format": "date"},
                    },
                },
            },
            "advisories": {
                "title": "Advisories by government",
                "description": "One row per government source.",
                "transformation": {
                    "unwind": ["advisories"],
                    "fields": [
                        "sourceCode",
                        "nativeLevel",
                        "nativeAdvice",
                        "normalizedSeverity",
                        "riskCategories",
                        "sourceUpdatedAt",
                        "sourceUrl",
                    ],
                },
                "display": {
                    "component": "table",
                    "properties": {
                        "sourceCode": {"label": "Source", "format": "text"},
                        "nativeLevel": {"label": "Native level", "format": "text"},
                        "nativeAdvice": {"label": "Native advice", "format": "text"},
                        "normalizedSeverity": {"label": "Normalized severity", "format": "object"},
                        "riskCategories": {"label": "Risk categories", "format": "array"},
                        "sourceUpdatedAt": {"label": "Source updated", "format": "text"},
                        "sourceUrl": {"label": "Official page", "format": "link"},
                    },
                },
            },
        },
    }


if __name__ == "__main__":
    SCHEMA_PATH.write_text(json.dumps(build_schema(), indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {SCHEMA_PATH}")
