"""Live smoke test against the real U.S., U.K. and Canadian government sources.

Run explicitly (never part of `pytest`):  python scripts/live_smoke_test.py [--json out.json] [dest ...]
Exits non-zero if any destination fails to resolve or gets fewer than two successful sources.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.lookup import run_lookup  # noqa: E402
from src.models.input import ActorInput  # noqa: E402
from src.utils.http import create_client  # noqa: E402

DEFAULT_DESTINATIONS = [
    "Trinidad and Tobago",
    "Mexico",
    "Colombia",
    "France",
    "Ukraine",
    "Haiti",
    "Thailand",
    "Kenya",
    "Turkey",
    "Ivory Coast",
    "Hong Kong",
    "Japan",
]


async def smoke(destinations: list[str]) -> tuple[list[dict], bool]:
    rows: list[dict] = []
    ok = True
    async with create_client() as client:
        for name in destinations:
            outcome = await run_lookup(ActorInput.model_validate({"destination": name}), client=client)
            result = outcome.result
            ok &= result.status in ("success", "partial")
            by_code = {a.source_code: a for a in result.advisories}
            errors = {e.source_code: e.error_code for e in result.errors}
            sources = {}
            for code in result.sources_requested:
                run = outcome.runs.get(code)
                advisory = by_code.get(code)
                sources[code] = {
                    "ok": advisory is not None,
                    "httpStatus": run.trace.http_status if run else None,
                    "attempts": run.trace.attempts if run else 0,
                    "parserOk": advisory is not None,
                    "overall": advisory.normalized_severity.overall if advisory else None,
                    "regionalMax": advisory.normalized_severity.regional_max if advisory else None,
                    "regions": len(advisory.regional_warnings or []) if advisory else None,
                    "risks": advisory.risk_categories if advisory else None,
                    "error": errors.get(code),
                    "latencyMs": run.elapsed_ms if run else None,
                }
            rows.append(
                {
                    "input": name,
                    "canonical": result.query.canonical_destination,
                    "status": result.status,
                    "billable": result.billing.billable,
                    "spread": result.comparison.severity_spread if result.comparison else None,
                    "totalMs": outcome.elapsed_ms,
                    "sources": sources,
                }
            )
    return rows, ok


def print_table(rows: list[dict]) -> None:
    header = f"{'destination':<22} {'status':<21} {'US':>14} {'UK':>14} {'CA':>14} {'spread':>6} {'ms':>6}"
    print(header)
    print("-" * len(header))
    for row in rows:
        cells = []
        for code in ("US", "UK", "CA"):
            s = row["sources"].get(code)
            if not s:
                cells.append("-")
            elif s["ok"]:
                reg = f"/r{s['regionalMax']}" if s["regionalMax"] else ""
                cells.append(f"{s['httpStatus']} L{s['overall']}{reg} {s['latencyMs']:.0f}")
            else:
                cells.append(f"{s['httpStatus'] or '---'} {s['error']}"[:14])
        print(
            f"{(row['canonical'] or row['input'])[:22]:<22} {row['status']:<21} "
            f"{cells[0]:>14} {cells[1]:>14} {cells[2]:>14} {row['spread']!s:>6} {row['totalMs']:>6.0f}"
        )
    for code in ("US", "UK", "CA"):
        lat = [r["sources"][code]["latencyMs"] for r in rows if r["sources"].get(code, {}).get("ok")]
        okc = sum(1 for r in rows if r["sources"].get(code, {}).get("ok"))
        if lat:
            print(
                f"{code}: {okc}/{len(rows)} ok, latency median {statistics.median(lat):.0f} ms, max {max(lat):.0f} ms"
            )
    totals = [r["totalMs"] for r in rows]
    print(f"lookup total: median {statistics.median(totals):.0f} ms, max {max(totals):.0f} ms")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destinations", nargs="*", default=DEFAULT_DESTINATIONS)
    parser.add_argument("--json", type=Path, help="write per-destination results to this file")
    args = parser.parse_args()
    rows, ok = asyncio.run(smoke(args.destinations))
    print_table(rows)
    if args.json:
        args.json.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
