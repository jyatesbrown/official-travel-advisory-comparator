"""Regenerate src/sources/uk_slugs.py from the live GOV.UK index (maintenance only).

Usage: python scripts/generate_uk_slugs.py > src/sources/uk_slugs.py
Unresolved index entries are reported on stderr and must be added to MANUAL by hand.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.destinations.resolver import get_resolver
from src.utils.http import USER_AGENT

INDEX_URL = "https://www.gov.uk/api/content/foreign-travel-advice"
MANUAL = {
    "CG": "congo",
    "BQ": "bonaire-st-eustatius-saba",
    "PN": "pitcairn-island",
    "AQ": "antarctica-british-antarctic-territory",
    "CK": "cook-islands-tokelau-and-niue",
    "NU": "cook-islands-tokelau-and-niue",
    "TK": "cook-islands-tokelau-and-niue",
}


def main() -> None:
    resolver = get_resolver()
    index = httpx.get(INDEX_URL, headers={"User-Agent": USER_AGENT}, timeout=30).json()
    slugs: dict[str, str] = {}
    for child in index["links"]["children"]:
        country = child["details"]["country"]
        names = [country["name"], *country.get("synonyms", [])]
        resolved = [resolver.resolve(n) for n in names]
        iso2 = next((r.destination.iso2 for r in resolved if r.ok and r.method != "fuzzy"), None)
        if iso2 is None:
            print(f"UNRESOLVED: {country['name']} ({country['slug']})", file=sys.stderr)
            continue
        slugs.setdefault(iso2, country["slug"])
    slugs.update(MANUAL)
    print('"""ISO 3166-1 alpha-2 -> GOV.UK foreign-travel-advice slug (generated)."""\n')
    print("UK_SLUGS: dict[str, str] = {")
    for iso2, slug in sorted(slugs.items()):
        print(f'    "{iso2}": "{slug}",')
    print("}")


if __name__ == "__main__":
    main()
