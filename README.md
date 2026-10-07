# Official Travel Advisory Comparator — US, UK & Canada

Look up **one country or territory** and get its current **official government travel advisories**
from the **U.S. Department of State**, the **U.K. Foreign, Commonwealth & Development Office (FCDO)**
and the **Government of Canada**, side by side, as **one structured JSON record**.

Each government uses its own wording and scale ("Level 3: Reconsider Travel", "advises against all
but essential travel to parts", "Exercise a high degree of caution"). This Actor keeps that native
wording and adds a **normalized 1–4 severity**, **regional (sub-national) warnings**, **risk
categories**, source dates and **official source URLs**. That way you can **compare travel advisories**
and check for disagreement between governments without scraping three websites.

It is a deterministic data utility, not a chatbot. It uses no LLM and no browser. It reads the
governments' own published data feeds, and the same input always produces the same structure.

## What you can use it for

- **AI agents and assistants:** answer "Is it safe to travel to X?" with what governments actually
  say, citing the sources (callable through the Apify MCP server).
- **Travel risk and duty-of-care checks:** gate trip approval when any government says
  "avoid all travel", or flag regional warnings for an itinerary.
- **Destination safety data:** a country travel risk field for travel apps, insurance and
  booking flows.
- **Spotting disagreement:** `comparison.materialDisagreement` is `true` when governments differ
  by two or more levels.

## Input

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `destination` | string | yes | | One country or territory. Common names, alternate spellings and ISO codes work: `"Trinidad and Tobago"`, `"trinidad & tobago"`, `"Turkey"` → Türkiye, `"Ivory Coast"` / `"Côte d'Ivoire"`, `"TT"`, `"MEX"`. |
| `sources` | array | no | `["US","UK","CA"]` | Any two or three of `US`, `UK`, `CA`. |
| `includeRegional` | boolean | no | `true` | Include the list of regional warnings. Regional *maximum* severity is always returned. |

```json
{ "destination": "Trinidad and Tobago" }
```

Unknown or ambiguous names are never guessed. `"Congo"`, `"Korea"` and `"Virgin Islands"` return
`invalid_destination` with a `candidates` list, and the lookup is not charged.

## Output

Every run writes **exactly one dataset item**. Real output for `{"destination": "Trinidad and Tobago"}`
(retrieved 2026-10-07; long regional details and risk-label lists shortened with "…"):

```json
{
  "schemaVersion": "1.0",
  "status": "success",
  "query": {
    "input": "Trinidad and Tobago",
    "canonicalDestination": "Trinidad and Tobago",
    "iso2": "TT",
    "iso3": "TTO",
    "matchMethod": "name",
    "candidates": []
  },
  "checkedAt": "2026-10-07T21:32:00Z",
  "sourcesRequested": [
    "US",
    "UK",
    "CA"
  ],
  "sourcesSucceeded": [
    "US",
    "UK",
    "CA"
  ],
  "sourcesFailed": [],
  "errors": [],
  "advisories": [
    {
      "sourceCode": "US",
      "sourceName": "U.S. Department of State",
      "sourceUrl": "https://travel.state.gov/content/tsg_aem/us/en/home/international-travel/travel-advisories/destination.tto.html",
      "retrievalUrl": "https://travel.state.gov/_res/rss/TAsTWs.xml",
      "retrievedAt": "2026-10-07T21:32:00Z",
      "sourceUpdatedAt": "2026-04-13",
      "nativeLevel": "Level 3",
      "nativeAdvice": "Reconsider Travel",
      "normalizedSeverity": {
        "overall": 3,
        "regionalMax": null,
        "hasRegionalEscalation": null,
        "basis": "Mapped from U.S. Department of State Level 3 (Reconsider Travel)"
      },
      "riskCategories": [
        "crime",
        "terrorism",
        "health"
      ],
      "nativeRiskLabels": [
        "crime",
        "health",
        "terrorism"
      ],
      "riskCategoriesBasis": "Risk factors named in the advisory summary sentence ('... due to ...').",
      "regionalWarnings": []
    },
    {
      "sourceCode": "UK",
      "sourceName": "U.K. Foreign, Commonwealth & Development Office",
      "sourceUrl": "https://www.gov.uk/foreign-travel-advice/trinidad-and-tobago",
      "retrievalUrl": "https://www.gov.uk/api/content/foreign-travel-advice/trinidad-and-tobago",
      "retrievedAt": "2026-10-07T21:32:00Z",
      "sourceUpdatedAt": "2026-09-21T15:13:58Z",
      "nativeLevel": "none",
      "nativeAdvice": null,
      "normalizedSeverity": {
        "overall": 1,
        "regionalMax": null,
        "hasRegionalEscalation": false,
        "basis": "GOV.UK alert_status=[]: no FCDO advice against travel to the whole country, mapped to 1 (the FCDO has no intermediate national levels)"
      },
      "riskCategories": [
        "crime",
        "terrorism",
        "natural_disaster"
      ],
      "nativeRiskLabels": [
        "Terrorism",
        "Terrorism in Trinidad and Tobago",
        "Violent crime and assault",
        "Drug assisted robbery and sexual assault",
        "Extreme weather and natural disasters",
        "Hurricanes",
        "…"
      ],
      "riskCategoriesBasis": "Section headings of the GOV.UK 'Safety and security' page that match the vocabulary.",
      "regionalWarnings": []
    },
    {
      "sourceCode": "CA",
      "sourceName": "Government of Canada",
      "sourceUrl": "https://travel.gc.ca/destinations/trinidad-and-tobago",
      "retrievalUrl": "https://data.international.gc.ca/travel-voyage/cta-cap-tt.json",
      "retrievedAt": "2026-10-07T21:32:00Z",
      "sourceUpdatedAt": "2026-09-24T12:53:00Z",
      "nativeLevel": "advisory-state 1",
      "nativeAdvice": "Exercise a high degree of caution",
      "normalizedSeverity": {
        "overall": 2,
        "regionalMax": 3,
        "hasRegionalEscalation": true,
        "basis": "Mapped from Government of Canada risk level 'Exercise a high degree of caution' (advisory-state 1)"
      },
      "riskCategories": [
        "crime",
        "terrorism",
        "civil_unrest",
        "maritime"
      ],
      "nativeRiskLabels": [
        "Crime",
        "Petty crime",
        "Violent crime",
        "Terrorism",
        "Fraud",
        "Demonstrations",
        "…"
      ],
      "riskCategoriesBasis": "Section headings of the travel.gc.ca 'Safety and security' section that match the vocabulary.",
      "regionalWarnings": [
        {
          "region": "Regional Advisory",
          "nativeAdvice": "Avoid non-essential travel",
          "normalizedSeverity": 3,
          "nativeDetails": [
            "Avoid non-essential travel to the following areas due to high levels of violence and gang-related crime:",
            "Beetham Estate Gardens",
            "Cocorite (north of Western Main Road)",
            "…"
          ]
        }
      ]
    }
  ],
  "comparison": {
    "availableSeverityValues": [
      3,
      1,
      2
    ],
    "lowestOverallSeverity": 1,
    "highestOverallSeverity": 3,
    "severitySpread": 2,
    "materialDisagreement": true,
    "highestRegionalSeverity": 3,
    "sourcesAtHighestOverallSeverity": [
      "US"
    ]
  },
  "billing": {
    "billable": true,
    "eventName": "destination-lookup",
    "reason": "3 official sources compared"
  }
}
```

### Key fields

| Field | Meaning |
|---|---|
| `status` | `success` (all requested sources returned data), `partial` (at least 2 returned data, at least 1 failed), `insufficient_sources` (fewer than 2 returned data), `invalid_destination` |
| `query` | Your input, the canonical name, ISO-2/ISO-3 codes and `matchMethod` (`name`, `alias`, `iso_code`, `fuzzy`) |
| `advisories[]` | One entry per government that returned data |
| `advisories[].nativeLevel` / `nativeAdvice` | The government's own level and wording, unchanged |
| `advisories[].normalizedSeverity.overall` | National advisory on the shared 1–4 scale |
| `advisories[].normalizedSeverity.regionalMax` | Most severe regional warning. Kept separate from `overall` and never merged into it |
| `advisories[].regionalWarnings[]` | Region, native advice, normalized severity and verbatim details |
| `advisories[].riskCategories` | Controlled vocabulary: `crime`, `terrorism`, `kidnapping`, `civil_unrest`, `armed_conflict`, `arbitrary_detention`, `health`, `natural_disaster`, `border_security`, `maritime`, `landmines`, `wrongful_detention`, `other` |
| `advisories[].sourceUrl` / `sourceUpdatedAt` | Official page and the source's own last-updated date |
| `comparison` | `availableSeverityValues`, lowest/highest, `severitySpread` (max − min), `materialDisagreement` (spread ≥ 2), `highestRegionalSeverity`, `sourcesAtHighestOverallSeverity` |
| `errors[]` | Per-source failures: `DESTINATION_NOT_FOUND`, `UPSTREAM_UNAVAILABLE`, `UPSTREAM_TIMEOUT`, `PARSER_FAILED`, `UNEXPECTED_SOURCE_FORMAT`, plus `INVALID_DESTINATION` |
| `billing` | Whether this lookup was charged, and why |

### Normalized severity scale

| Normalized | U.S. State Department | U.K. FCDO | Government of Canada |
|---|---|---|---|
| 1 Normal precautions | Level 1: Exercise Normal Precautions | No whole-country "advise against" warning | Take normal security precautions |
| 2 Increased caution | Level 2: Exercise Increased Caution | (no equivalent) | Exercise a high degree of caution |
| 3 Avoid non-essential / reconsider | Level 3: Reconsider Travel | Advises against all but essential travel to the whole country | Avoid non-essential travel |
| 4 Avoid all travel | Level 4: Do Not Travel | Advises against all travel to the whole country | Avoid all travel |

The U.K. FCDO has no national level 2. When it warns only about **parts** of a country, its
`overall` stays 1, and the warnings appear in `regionalMax` and `regionalWarnings`. For example,
Ukraine shows UK `overall: 1, regionalMax: 4`. Always read `overall` together with `regionalMax`.

## Pricing

Pay per event: **$0.01 per `destination-lookup`**. You are charged once, only when the lookup
compares at least two official sources (`success` or `partial`). You are **not** charged for
`invalid_destination`, `insufficient_sources`, invalid input or failed runs.

A typical lookup finishes in under a second (live test: median about 0.26 s, slowest about 0.9 s,
plus Actor start-up).

## Sources and method

| Government | Data used | Official page linked |
|---|---|---|
| U.S. Department of State | Travel advisories RSS feed `travel.state.gov/_res/rss/TAsTWs.xml` | travel.state.gov advisory page |
| U.K. FCDO | GOV.UK Content API `www.gov.uk/api/content/foreign-travel-advice/{country}` | gov.uk/foreign-travel-advice |
| Government of Canada | Open data `data.international.gc.ca/travel-voyage/cta-cap-{iso}.json` | travel.gc.ca/destinations |

- Sources are fetched concurrently, with timeouts and up to 3 attempts for transient errors.
  If one government's site fails, the others' results are still returned.
- Risk categories come only from explicit headings or phrases: U.S. "due to …" summary phrases,
  U.K. "Safety and security" headings, Canada "Safety and security" headings. Nothing is inferred.
- If a source's format changes, the Actor reports `UNEXPECTED_SOURCE_FORMAT` / `PARSER_FAILED` for
  that source. It never returns empty fields that would look like "no risk".

## Limitations

- **Current advisories only.** No history, monitoring or alerts.
- **English only.**
- **U.S. regional detail comes from the feed summary.** For some destinations (e.g. Mexico), the State
  Department lists states only on its full web page, which blocks automated access. In those
  cases `regionalWarnings` can be empty and `hasRegionalEscalation` is `null` (unknown), not `false`.
- **Some grouped or special destinations are covered by only some governments.** Examples are the West
  Bank and Gaza, the Canary Islands, the Azores and French overseas territories. Expect
  `partial` or `DESTINATION_NOT_FOUND` for some sources.
- **This is not travel, legal or insurance advice.** Always read the linked official pages before making
  decisions.

## Using it from an AI agent (MCP)

Connect your agent to the Apify MCP server (`https://mcp.apify.com`) and search for "travel
advisory", or add this Actor as a tool directly. Call it with `{"destination": "<country>"}` and read
`status`, `advisories[].normalizedSeverity` and `comparison`.

## FAQ

**Does it call an LLM?** No. Parsing is rule-based, so outputs are reproducible.

**Why do the US and UK numbers differ so often?** The scales are different. The UK has no "increased
caution" national level, and the US level 2 is common. `materialDisagreement` only flags gaps of two
or more levels.

**Can I look up several countries?** One destination per run, so each lookup is priced and
cached independently. Run it once per country.
