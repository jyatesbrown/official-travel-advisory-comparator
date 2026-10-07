# AGENTS.md

Apify Actor (Python 3.12) that compares official U.S., U.K. and Canadian travel advisories for one
destination and emits exactly one normalised dataset record. Deterministic parsing only: no LLMs,
no browsers.

## Layout
- `src/main.py` Actor entry point (input, push record, charge `destination-lookup` once).
- `src/lookup.py` orchestration: resolve destination, run adapters concurrently, compare.
- `src/sources/` one adapter per government (`us_state.py` RSS, `uk_fcdo.py` GOV.UK Content API,
  `canada.py` travel.gc.ca JSON). Each raises `SourceError` with a controlled `ErrorCode`.
- `src/normalization/` severity mapping, risk vocabulary, comparison.
- `.actor/` Actor definition, input/output/dataset schemas, intended PPE pricing.

## Commands
```bash
pip install -r requirements-dev.txt
ruff check . && ruff format --check .
pytest                                   # unit + fixture tests, no network
python scripts/live_smoke_test.py        # live government sources (manual only)
python scripts/export_dataset_schema.py  # regenerate .actor/dataset_schema.json fields
apify run --input '{"destination": "Kenya"}'
```

## Rules
- Tests must never hit the network; use fixtures in `tests/fixtures/` or `respx`.
- When a source's structure changes, raise `UNEXPECTED_SOURCE_FORMAT`/`PARSER_FAILED`; never
  return empty fields that look like "no risk".
- Do not change the public input (no timeouts/selectors/headers) or the billing rules in
  `src/billing.py` without updating README and tests.
