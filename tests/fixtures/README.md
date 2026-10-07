# Test fixtures

Snapshots of official government travel-advisory data, captured on 2026-10-07 from the live
endpoints the Actor uses. They are trimmed only by removing fields the parsers don't read: GOV.UK
`links`/`change_history`, Canada French text and the health/entry/laws/offices sections. Advisory
content is otherwise unchanged. The files contain no personal data.

| Directory | Source | Licence |
|---|---|---|
| `us/TAsTWs.xml` | U.S. Department of State, https://travel.state.gov/_res/rss/TAsTWs.xml | U.S. Government work (public domain) |
| `uk/*.json` | GOV.UK Content API, https://www.gov.uk/api/content/foreign-travel-advice/{slug} | Crown copyright, Open Government Licence v3.0 |
| `ca/*.json` | Government of Canada, https://data.international.gc.ca/travel-voyage/cta-cap-{iso}.json | Open Government Licence – Canada |

Refresh one with, for example, `curl -s https://www.gov.uk/api/content/foreign-travel-advice/kenya > uk/kenya.json`,
then re-apply the trimming. The parser tests assert values from these exact snapshots, so update the
expected values in `tests/test_parsers.py` whenever you refresh.
