# Post-semantics-patch agent benchmark — build 1.1.1

**Recommendation: SEMANTICS IMPROVED — ONE MORE TARGETED PATCH**

This is the same benchmark as `baseline-1.0.2.md`, rerun against build 1.1.1 (PR #3). Nothing was changed: the prompt set (20 relevant, 19 controls), prompt wording, agent model (`claude-sonnet-5-5`), system prompts, tool setup, directed-arm configuration, third-party call interception, rubric and judge (`claude-opus-5-5`) are all the same. The only change to the analysis code is a `--build` flag that selects the raw files. Machine-readable results are in `post-semantics-patch.json`. Raw episodes are in `raw-default-1.1.1.jsonl` and `raw-directed-1.1.1.jsonl`. The live sanity runs are in `sanity-1.1.1.json`.

| Item | Value |
|---|---|
| Actor build | 1.1.1 (`tbLCedp0jNlaSxy6M`), 256 MB, 120 s, `LIMITED_PERMISSIONS`, Standby off |
| Pricing | Unchanged: `apify-actor-start` $0.00005, `destination-lookup` $0.01 (primary) |
| Store title, description, categories | Unchanged. The README (Store page body) gained the required semantics notes |
| MCP | `https://mcp.apify.com/`, `apify-mcp-server` 0.17.4 |
| Run date | 2026-10-08, starting about 16:25 UTC |
| Repetitions | 1 per prompt per arm |

**Harness incident.** The directed run stopped once, at p09, when an MCP `tools/call` response came back with an empty body (`JSONDecodeError`). No episode was written for p09. I reran the harness with no changes; it resumes from the episodes already written, so p09 ran from scratch and p10–p39 followed. All 39 episodes per arm are complete.

## Headline comparison (directed Store arm)

| Metric | Build 1.0.2 | Build 1.1.1 |
|---|---:|---:|
| Discovery | 95% (19/20) | 95% (19/20) |
| Top-1 / top-3 discovery | 15% / 95% | 25% / 95% |
| Mean rank | 2.68 | 2.47 |
| Selection given discovery | 94.7% (18/19) | 94.7% (18/19) |
| End-to-end selection | 90% (18/20) | 90% (18/20) |
| First-attempt valid invocation | 83.3% (15/18) | **100%** (18/18) |
| Eventual valid invocation | 100% (18/18) | 100% (18/18) |
| Per-call valid | 85.7% (18/21) | 100% (18/18) |
| Correct interpretation | 50% (9/18) | **55.6%** (10/18) |
| False discovery (controls) | 15.8% | 15.8% |
| False selection (controls) | 0% | 0% |
| False invocation (controls) | 0% | 0% |

Default arm: unchanged at 0% discovery. The agent used `apify/web-fetch` 17 times and `apify/rag-web-browser` 3 times (16 and 4 at baseline), and false selection was 0%.

The prompts that were lost are the same as at baseline: p05 (FCDO wording; ours didn't surface, and a UK-only Actor was chosen) and p08 (US "Level 4" wording; `maximedupre/us-travel-advisories-scraper` was chosen). For the "travel advisory" query, `jungle_synthesizer/us-state-dept-travel-advisories-scraper` and `maximedupre/us-travel-advisories-scraper` still rank above ours on 19 prompts. The top-1 change (15% → 25%) comes from the agent's follow-up queries and from Store ordering, not from any metadata change. Treat it as noise.

## Error-type comparison (failed answers, directed arm)

Each failed answer is counted once per error type.

| Error type | Build 1.0.2 | Build 1.1.1 |
|---|---:|---:|
| Regional coverage: unknown US regional data presented as "none" or "no escalation" (R7) | 4 (p06, p12, p25, p29) | 3 (p02, p11, p29) |
| Regional coverage: regional warnings attributed to the US without support (R4/R7) | 3 (p09, p22, p27) | 2 (p04, p27) |
| **Regional coverage, total** | **7** | **5** |
| Source attribution, non-US (UK credited with the Iraq-border warning) | 1 (p03) | 2 (p03, p23) |
| Native vs normalized severity (R1/R2) | 2 (p01, p09) | **0** |
| Source-code validation (rejected first calls) | 3 of 21 calls | **0** of 18 calls |
| Other (misread regional detail: Cali, UK region count) | 0 | 1 (p06; p02 also had a count error) |

Criterion-level failures:
- Baseline: R1 2, R2 1, R4 4, R7 4.
- Post-patch: R4 3, R7 4, R8 1.

## Post-patch interpretation failures

I checked every failure by hand against its dataset record.

| Prompt | Destination | What went wrong | Classification |
|---|---|---|---|
| p02 | Mexico | Says that tourist areas are "not flagged by any government", even though US `regionalCoverage` is `unavailable`. The answer had already said the US data was unavailable. Also miscounts the UK entries as 13 when the record has 14 | Agent reasoning error |
| p03 | Turkey | Says all three governments warn within 10 km of the Syria **and Iraq** borders. The UK record only covers the Syria border, and the 10 km/Iraq wording is Canada's | Agent reasoning error |
| p04 | Kenya | The opening says all three governments flag regions. The US is `unavailable` with `regionalWarnings: null`, and the answer itself says so later | Agent reasoning error |
| p06 | Colombia | Places Cali in Canada's avoid-non-essential region. The record says "excluding the cities of Buga, Cali, Palmira" | Agent reasoning error |
| p11 | Hong Kong | The agent's summary emits `"regionalEscalation": false`. US is `unavailable`; UK and CA are `available` with `[]`. `comparison.highestRegionalSeverity` is `null`, the same value it would have if every source were known-empty | **Actor output ambiguity** (comparison block) |
| p23 | Türkiye | Same as p03: the UK is credited with the Iraq-border warning | Agent reasoning error |
| p27 | Colombia | The opening says all three governments warn about border/rural regions. The US is `unavailable` | Agent reasoning error |
| p29 | Jamaica | "None of the three governments lists a regional warning", with US `unavailable` and UK/CA `[]`. `comparison.highestRegionalSeverity` is `null` here too | **Actor output ambiguity** (comparison block) |

I found no incorrect source data, parser defects or rubric issues. In every case the per-source fields were correct and explicit.

## What the patch fixed

- **Source aliases:** first-attempt validity went from 83.3% to 100%, with no rejected calls. The baseline failures (`["uk","canada"]` and similar) would now be accepted.
- **Native vs normalized scales:** zero R1/R2 failures, down from 2. Judges noted answers labelling the 1–4 value as the Actor's own scale and using Canada's named categories.
- **Per-source regional coverage:** 14 of the 18 graded answers came from records with US `regionalCoverage: "unavailable"`. Of those, 9 handled it correctly: they passed R7 and didn't attribute regions to the US. The other 5 are the regional failures below.

## What remains

Regional coverage is still the main failure type (5 of 8 failures). The per-source fields are now unambiguous. Two failures (p11, p29) trace to the **comparison block**: `comparison.highestRegionalSeverity: null` means both "no source reported regional warnings" and "some sources' regional status is unknown", and the comparison block doesn't say which sources it covers. The other three (p02, p04, p27) are agents overgeneralizing to "all three governments", even though the record is explicit.

A targeted fix that stays within scope is a comparison-level field such as `comparison.regionalCoverage` (`complete` / `partial`), plus the list of sources whose regional status is unknown. With that, `highestRegionalSeverity: null` would no longer read as "none". The UK/Iraq misattribution (p03, p23, and p03 at baseline) is a consistent agent conflation of Canada's and the UK's Turkey border text. The record keeps them apart correctly, so I'm not proposing an output change for it.

## Why this recommendation

- Discovery and selection didn't regress. They are identical, so **PATCH HURT DISCOVERY/SELECTION** doesn't apply.
- Two of the three targeted issues are fully resolved: aliases and native-scale confusion went to zero.
- The regional-coverage issue improved (7 → 5 failures), but interpretation correctness only rose from 50% to 55.6%. That is a one-answer difference on n = 18 and within run-to-run noise, so **SEMANTICS PATCH SUCCESSFUL — ACTOR #1 VALIDATED** isn't supported.
- The remaining Actor-attributable failures come from one specific, fixable gap (comparison-level regional coverage), not from the output model as a whole, so **OUTPUT MODEL NEEDS REDESIGN** isn't warranted.

## Billing and latency

- **Runs on build 1.1.1:** 23 (5 live sanity runs and 18 benchmark runs). Each was charged exactly 1 `apify-actor-start` and 1 `destination-lookup`, with no anomalies. That is $0.23115 nominal; you aren't billed for your own runs.
- **Actor run time:** median 2.9 s, p95 3.725 s. Baseline was 2.68 s and 3.46 s.
- **`call-actor` round trip:** median 6.999 s. Baseline was 8.15 s.

## Caveats

- There is one repetition per prompt. Small differences, including the top-1 rank change and the single extra correct answer, are within noise.
- The LLM judge graded every answer. I checked all 8 failures by hand and agree with each verdict.
- Default-arm answers don't reflect real web-fetch output, because third-party calls are intercepted (same as baseline).
