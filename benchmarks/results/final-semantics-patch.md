# Final semantics patch agent benchmark — build 1.2.1

**Decision: ACTOR #1 VALIDATED — MOVE TO PORTFOLIO TEST**

This is the same benchmark as `baseline-1.0.2.md` and `post-semantics-patch.md`, rerun against build 1.2.1. Build 1.2.1 is PR #5: comparison-level `regionalCoverage`, `regionalWarningConclusion` and `sourcesWithRegionalWarnings`, at schema 1.2.

Everything else is unchanged:
- the 20 relevant and 19 control prompts, word for word;
- the agent model (`claude-sonnet-5-5`), system prompts and MCP tool setup;
- the directed-arm configuration and the interception of third-party calls;
- the rubric and the judge (`claude-opus-5-5`).

Results are in `final-semantics-patch.json`. Raw episodes are in `raw-default-1.2.1.jsonl` and `raw-directed-1.2.1.jsonl`, and the live sanity runs are in `sanity-1.2.1.json`.

| Item | Value |
|---|---|
| Actor build | 1.2.1 (`KS0FmI5NpYqyXtq6C`), 256 MB, 120 s, `LIMITED_PERMISSIONS`, Standby off |
| Pricing | Unchanged: `apify-actor-start` $0.00005, `destination-lookup` $0.01 (primary) |
| Store title, description, categories | Unchanged |
| Run date | 2026-10-08, about 17:05 UTC |
| Repetitions | 1 per prompt per arm |

**Harness incident.** The analysis script hit one transient Apify API `502` while reading run stats. I reran it and nothing else changed.

## Live sanity checks (build 1.2.1)

| Destination | Per-source regional coverage | `regionalCoverage.status` | `regionalWarningConclusion` | `highestRegionalSeverity` |
|---|---|---|---|---:|
| Mexico | US unavailable; UK 14 warnings; CA 1 warning | `partial` (US unavailable) | `warnings_reported` (UK, CA) | 3 |
| Jamaica | US unavailable; UK `[]`; CA `[]` | `partial` (US unavailable) | `unknown_due_to_incomplete_coverage` | null |
| Turkey | US, UK and CA all available with warnings | `complete` | `warnings_reported` (US, UK, CA) | 4 |

None of the three runs found a "complete coverage, no warnings" case with all three sources. The US adapter only reports `available` when the RSS summary names regions, and that always means a warning. Case B is covered by the unit tests.

## Headline comparison (directed Store arm)

| Metric | 1.0.2 | 1.1.1 | 1.2.1 |
|---|---:|---:|---:|
| Discovery | 95% (19/20) | 95% (19/20) | 100% (20/20) |
| Top-1 / top-3 discovery | 15% / 95% | 25% / 95% | 20% / 100% |
| Mean rank | 2.68 | 2.47 | 2.60 |
| Selection given discovery | 94.7% (18/19) | 94.7% (18/19) | 90% (18/20) |
| End-to-end selection | 90% (18/20) | 90% (18/20) | 90% (18/20) |
| First-attempt valid invocation | 83.3% | 100% | 100% |
| Eventual valid invocation | 100% | 100% | 100% |
| Correct interpretation | 50% (9/18) | 55.6% (10/18) | 50% (9/18) |
| False discovery (controls) | 15.8% | 15.8% | 21.1% |
| False selection (controls) | 0% | 0% | 0% |
| False invocation (controls) | 0% | 0% | 0% |

- **Selection given discovery fell from 94.7% to 90%.** p05 is now discovered (rank 3), but the agent still picks the UK-only `jungle_synthesizer` Actor for FCDO wording. The two lost prompts are the same as before, p05 and p08, so end-to-end selection is unchanged.
- **False discovery rose from 15.8% to 21.1%.** That is 4 of 19 controls where our Actor appeared in search results, against 3 of 19 before. None of them selected it.
- **Default arm:** still 0% discovery. It used `apify/web-fetch` 18 times and `apify/rag-web-browser` twice, and false selection was 0%.
- **Billing:** 18 runs charged exactly 18 starts and 18 lookups.
- **Latency:** median Actor run 2.8 s, p95 4.1 s.

## What the patch targeted

| Prompt | 1.1.1 failure | 1.2.1 |
|---|---|---|
| p11 (Hong Kong) | `regionalEscalation: false` despite unknown US coverage | **Correct** |
| p27 | "all three governments warn about regions" despite unknown US coverage | **Correct** |
| p29 (Jamaica) | "no government lists a regional warning" | Still fails, but now because the agent contradicted an explicit field (see below) |

Flips between runs. The records for these prompts are unaffected by the patch, except for the added `warnings_reported` conclusion:
- **Fixed:** p06, p11, p27.
- **Regressed:** p09, p24, p26, p28.

The net change of -1 is within single-run variance. The interpretation rate swings ±1–2 answers between runs, with no change to the relevant data.

## Remaining interpretation failures (9)

I checked each one by hand against its dataset record.

| Prompt | Failure (judge) | Classification | Why |
|---|---|---|---|
| p02 Mexico | UK regional count 13/9 states instead of 14/11; Canada count inconsistent | Agent reasoning error | Counting mistake. The record lists every entry. |
| p03 Turkey | All three said to warn about the Syria **and Iraq** borders at 10 km | Agent reasoning error | The UK entry covers only the Syria border. Each source's `regionalWarnings` is explicit. |
| p04 Kenya | Merged region list used the UK's narrower exceptions; Canada understated; Lagdera misstated | Agent reasoning error | Each source's regions are given verbatim. The agent's merge lost information. |
| p09 Ivory Coast | "Three governments" warn about border regions | Agent reasoning error | The record says `sourcesWithRegionalWarnings: ["UK","CA"]` and `sourcesUnavailable: ["US"]`. The answer's own later note says US regional data is unavailable. |
| p23 Türkiye | Opening says "normal travel to most of the country" | Agent reasoning error | Concerns national advice, not regions. The native US Level 2 and Canada "high degree of caution" are in the record and in the answer's own table. |
| p24 Trinidad | Credits the US with avoiding Port of Spain neighborhoods | Agent reasoning error | The record has US `regionalCoverage: "unavailable"` and `regionalWarnings: null`. The answer then contradicts itself. |
| p26 Mexico | Paraphrases "all but essential" as "all or most travel"; Canada given US "increased caution" wording; "generally fine" | Agent reasoning error | The native wording, `nativeScale` and `scaleNote` are all present. These are paraphrasing errors. |
| p28 Thailand | Credits the US with crime, scams and terrorism; scams said to come from all three | Agent reasoning error | The US Level 1 record has `riskCategories: []`, and its `riskCategoriesBasis` gives the source rule. The agent added risks the record doesn't contain. |
| p29 Jamaica | "None lists a region as off-limits" and then a caveat | Agent reasoning error | The record says `regionalWarningConclusion: "unknown_due_to_incomplete_coverage"` and `sourcesUnavailable: ["US"]`. The answer reports the caveat but leads with an overstated sentence. |

Summary:

| Classification | Count |
|---|---:|
| Actor output ambiguity | 0 |
| Agent reasoning error | 9 |
| Source-data problem | 0 |
| Parser defect | 0 |
| Rubric/judge issue | 0 |

Criterion failures: R4 (attribution) 4, R1 3, R2 1, R7 (regional coverage) 1, R8 1. R7 failures fell from 4 at both 1.0.2 and 1.1.1 to 1, and the remaining one (p29) contradicts an explicit field.

**Could better output semantics fix any of these?** Not without overfitting. Every failure contradicts a field that already states the correct fact: per-source `regionalWarnings`, `regionalCoverage`, `nativeAdvice`, `riskCategories`, or the new `sourcesWithRegionalWarnings` and `regionalWarningConclusion`. Most of them also contradict the agent's own table or caveat in the same answer. Fixing them would take output tailored to particular mistakes, such as precomputed counts or prewritten sentences. The brief excludes that.

**One item to watch, not a defect.** On the US Level 1 record (p28), `riskCategories: []` means the RSS summary names no risk factor, as `riskCategoriesBasis` states. The agent over-attributed risks here rather than reading the empty list as "no risk". So this is not the empty-versus-unknown problem the patches fixed.

## Decision

**ACTOR #1 VALIDATED — MOVE TO PORTFOLIO TEST**

These are the brief's criteria:
- **No material output ambiguity remains.** The comparison-level unknown-versus-empty gap was the only one identified at 1.1.1, and it is closed. p11 and p27 are now correct, and p29 now contradicts an explicit field.
- **Discovery and selection are strong.** Discovery is 100% with top-3 at 100%, and end-to-end selection is 90%.
- **Invocation is reliable.** First-attempt valid invocation is 100%.
- **False selection is 0%.**
- **All 9 remaining failures are agent reasoning errors.**

Per the brief, development on this Actor stops here. Not addressed, and outside this Actor's output model:
- In the default arm, the agent still bypasses the Store in favour of generic web tools.
- p05 and p08 still go to competing single-government Actors.
