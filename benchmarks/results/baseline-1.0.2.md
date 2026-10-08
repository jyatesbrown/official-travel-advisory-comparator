# Baseline agent-discovery and selection benchmark — build 1.0.2

**Recommendation: INTERPRETATION WEAK — IMPROVE OUTPUT SEMANTICS**

No Actor code, metadata, schema, README or pricing was changed for this benchmark. Machine-readable results, including every per-prompt row, are in `baseline-1.0.2.json`. Raw episodes are in `raw-default-1.0.2.jsonl` and `raw-directed-1.0.2.jsonl`.

## Environment

| Item | Value |
|---|---|
| Actor | `rhincodontypus/official-travel-advisory-comparator` (`NlGhYH3A5vpWZe3Th`), build 1.0.2 |
| Agent model | `claude-sonnet-5-5` via the Anthropic Messages API, using provider-default sampling (this model doesn't support `temperature`) |
| Interpretation judge | `claude-opus-5-5`; p01, p03 and p09 checked by hand against the dataset records, and all three verdicts confirmed |
| MCP | `https://mcp.apify.com/`, `apify-mcp-server` 0.17.4 |
| Run date | 2026-10-08, starting about 14:50 UTC |
| Repetitions | 1 per prompt per arm, with at most 14 tool turns |
| Harness | `benchmarks/agent_harness.py`; scoring is in `benchmarks/analyze_baseline.py` |

**Arms.** This setup wasn't covered by the brief, so I'm reporting it as a decision I made.
- **Default:** every MCP tool except `report-problem` and `abort-actor-run`, with a neutral system prompt. A smoke test showed the agent never searches the Store when generic web tools are available.
- **Directed Store:** the same prompts, with `apify--web-fetch` and `apify--rag-web-browser` removed. The system prompt tells the agent to search Apify Store with `search-actors`, choose the best-fitting Actor, run it, or answer directly if none fits. Our Actor is never named, and candidates are never injected.

**Third-party calls.** Calls to any Actor other than ours, including `apify/web-fetch` and `apify/rag-web-browser`, were recorded but not executed. The episode ended at that point, which kept paid competitor runs off the account. Default-arm answers therefore don't reflect what those tools would actually have returned.

## Prompt set

The set has 20 relevant prompts and 19 controls, frozen in commit `ceab386` before any run. All 23 original prompts are unchanged.

| Relevant category | n |
|---|---|
| general_official_advisory | 6 |
| single_source_wording | 5 |
| explicit_comparator | 3 |
| cross_source_disagreement | 3 |
| ambiguous_natural_language | 3 |

The controls cover flights (2), weather (2), visas (2), hotels (2), advisory history, alerts/monitoring, street-level safety, unsupported government, bulk ranking, itinerary, restaurants, passports, currency conversion, attractions and local transport.

## Headline metrics

| Metric | Default arm | Directed Store arm |
|---|---|---|
| Relevant prompts that issued any `search-actors` call | 0/20 | 20/20 |
| Discovery rate | 0% | **95%** (19/20) |
| Discovered in top 1 / top 3 / top 5 | 0 / 0 / 0% | 15 / 95 / 95% |
| Mean / median rank | — | 2.68 / 3 |
| Selected, given discovered | — | **94.7%** (18/19) |
| Selected, end to end | 0% | **90%** (18/20) |
| Valid invocation (final call) | — | **100%** (18/18) |
| Valid on first attempt | — | 83.3% (15/18) |
| Valid per call | — | 85.7% (18/21) |
| Correct interpretation | — | **50%** (9/18) |
| False discovery (controls) | 0% | 15.8% (3/19) |
| False selection (controls) | 0% | **0%** |
| False invocation (controls) | 0% | 0% |

**What was selected for relevant prompts:**
- Default arm: `apify/web-fetch` 16 times and `apify/rag-web-browser` 4 times. Each was pointed directly at the government pages.
- Directed arm: ours 18 times, `jungle_synthesizer/uk-fcdo-foreign-travel-advice-scraper` once (p05) and `maximedupre/us-travel-advisories-scraper` once (p08).

**Rank semantics.** `search-actors` returns Store relevance order. That order isn't guaranteed to be stable, so the ranks above are the positions returned at run time. For most prompts, the agent's first query was "travel advisory", where ours came 3rd behind `jungle_synthesizer/us-state-dept-travel-advisories-scraper` and `maximedupre/us-travel-advisories-scraper`.

## Invocation

- There were 21 calls to our Actor. No call invented a field, and every executed call resolved the expected destination.
- The agent's own aliases resolved correctly: Ivory Coast, Côte d'Ivoire → Ivory Coast, Turkey and Türkiye.
- **Malformed pattern:** in 3 of 18 episodes (p07, p10, p12), the first call used lowercase or long-form source codes such as `["uk","canada"]` and `["us","canada"]`. The enum `["US","UK","CA"]` rejected them. The agent corrected the codes on its second call each time.
  - The rejected calls never started a run, so nothing was charged.
- All 18 executed runs returned `SUCCEEDED` with one dataset record whose status was `success`.

## Interpretation

**Rubric.** Each answer was graded against its run's dataset record. Each criterion is marked pass, fail or n/a, and an answer counts as correct only if no criterion fails.
- **R1:** native wording is faithful, and the UK isn't given a numbered 1–4 scale.
- **R2:** normalized severity isn't presented as official government terminology.
- **R3:** regional and national advice are kept separate.
- **R4:** advice is attributed to the correct government.
- **R5:** disagreement is neither hidden nor invented.
- **R6:** a failed source isn't claimed as having succeeded.
- **R7:** null or unknown values aren't presented as "none".
- **R8:** the answer addresses the question.

**Results:** 9 of 18 answers were correct.

| Error class | Count | Prompts |
|---|---|---|
| US regional data unknown (`regionalWarnings: []` with `regionalMax: null`) presented as "no regional warnings" (R7) | 4 | p06, p12, p25, p29 |
| Other governments' regional warnings attributed to the US, or "all three agree" (R4) | 3 | p09, p22, p27 |
| UK record said to warn about the Iraq border (it covers only the Syria border) (R4) | 1 | p03 |
| Canada reported as "Level 2 of 3", mixing normalized severity with native terms (R1/R2) | 1 | p01 |

**Errors that didn't occur:** `regionalMax` treated as national severity, the UK given a formal 1–4 scale, disagreement hidden, and failed sources claimed as successful. No partial-source results occurred, so R6 is untested.

The dominant cause is the US source: 7 of the 9 failures involve its regional data. The feed carries no regional detail, and the record shows that as an empty array alongside null flags. Agents read the empty array as "none".

## Abstention

- **Controls where ours appeared in search results:** advisory history (p16), unsupported government (p19) and bulk ranking (p21). It ranked 3rd each time and was never selected.
- **What the agent picked for those three:** `maximedupre` for p16, `apify/rag-web-browser` for p19, and `jungle_synthesizer` US for p21.
- **The other 16 controls:** the agent either picked an unrelated Actor (weather, booking, maps, FX, website monitor) or answered directly (7).

## Billing and economics

| Item | Value |
|---|---|
| Runs of our Actor | 18 |
| `apify-actor-start` charged | 18 |
| `destination-lookup` charged | 18 |
| Nominal event value | $0.1809 (18 × $0.01005) |
| Lookups charged on non-billable results | 0 |
| Accounted (actually billed) | 0, because the owner isn't billed for their own runs |

Per paid lookup, net is about \(0.8 \times \$0.01 - \sim\$0.0001\) of platform cost, or roughly $0.0079.

## Latency (directed arm, our Actor)

| Measure | n | Min | Median | Mean | p95 | Max |
|---|---|---|---|---|---|---|
| Actor `runTimeSecs` | 18 | 2.38 | 2.68 | 2.84 | 3.46 | 3.76 |
| `call-actor` tool round trip (s) | 21 | 0.07 | 8.15 | 7.09 | 9.79 | 9.85 |
| Whole episode (s) | 18 | 16.5 | 21.6 | 21.5 | 24.7 | 32.5 |

The 0.07 s minimum is a rejected-input call.

## Competitors encountered

| Actor | Scope | Price | Multiple governments | Advantage | Weakness | Ranked above ours | Selected over ours |
|---|---|---|---|---|---|---|---|
| `jungle_synthesizer/us-state-dept-travel-advisories-scraper` | US State Dept, 213+ countries | ~$0.10 per start + $0.0005 per record | No | #1 for "travel advisory"; bulk output | US only; expensive for one lookup | 19 | 0 |
| `maximedupre/us-travel-advisories-scraper` | US State Dept + CDC | $0.00001 per alert | No | #2 for "travel advisory"; cheap; US level filter | US only | 19 | 1 (p08) |
| `jungle_synthesizer/uk-fcdo-foreign-travel-advice-scraper` | UK FCDO, 226 countries | ~$0.10 per start + per record | No | Top result for FCDO queries | UK only | 0 | 0 (won p05, where ours wasn't found) |
| `nexgenwatch/official-travel-advice-mcp` | UK FCDO MCP server | ~$0.05 per start + $0.05 per tool call | No | Appears for FCDO/GOV.UK queries | UK only; an MCP server, not a one-shot lookup | 0 | 0 |

## Failure analysis

- **Default-arm discovery: 0 of 20.** The agent answered every relevant prompt by fetching government pages with generic web tools and never called `search-actors`. Store metadata can't influence an agent that never searches. That's why this result doesn't drive the recommendation, though it is the largest real-world gap.
- **p05, discovery.** "Does the FCDO advise against travel to any part of Thailand?" The agent searched "FCDO travel advice" and "gov.uk foreign travel advice". Ours didn't appear for either, and the UK-only scraper was chosen.
- **p08, selection.** "Is there a Level 4 Do Not Travel advisory for Haiti?" Ours ranked 3rd and 5th. The agent fetched details only for the US-only `maximedupre` Actor and chose it without giving a reason.
- **p07, p10 and p12, invocation.** The source codes were rejected because of case and form. The agent recovered on the second call.
- **Interpretation.** See the table above. 7 of the 9 failures come down to unknown US regional coverage.

## Candidate optimizations

None of these has been applied. They're ordered by expected impact.

1. **Interpretation:** when regional data is unavailable, emit `regionalWarnings: null` instead of `[]`. Add a per-source `regionalCoverage` value (`available`/`unavailable`) with a short deterministic note. This targets 7 of the 9 failures.
2. **Interpretation:** add a per-source native-scale description (Canada has 4 advisory states, the UK has no numbered levels). This targets p01.
3. **Invocation:** accept case-insensitive codes and common aliases (`us`/`usa`, `uk`/`fcdo`, `ca`/`canada`), or state the exact codes in the field description. This targets 3 of 18 rejected first attempts.
4. **Discovery:** add single-government terms to the Store description and keywords: FCDO, GOV.UK foreign travel advice, State Department levels 1–4, travel.gc.ca. This targets p05 and the 15% top-1 rate.
5. **Selection:** make clear that the Actor returns the State Department's level and wording, so US-only questions don't go to US-only Actors by default. This targets p08.

## Why this recommendation

In the directed arm, three stages are near target:
- **Discovery:** 95%.
- **Selection:** 94.7% given discovery.
- **Invocation:** 100% eventual validity (83% on the first attempt).

Abstention is also at target, with 0% false selection. Correct interpretation, at 50%, is the clearly weakest measured stage, and its failures cluster in one output-semantics problem: unknown versus empty regional data.

The default arm's 0% discovery is reported, not hidden. It isn't attributed to Store metadata, because the agent never queried the Store.

## Caveats

- n = 20 relevant prompts and 19 controls, one run each. All rates are point estimates.
- The directed arm measures Store discovery and selection under an instruction to use Store Actors. It doesn't measure default agent behaviour.
- The judge is an LLM. Three verdicts were hand-checked; the rest were not.
