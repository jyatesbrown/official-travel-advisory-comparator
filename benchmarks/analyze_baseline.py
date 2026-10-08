"""Score raw harness episodes into baseline metrics.

Usage:
    APIFY_TOKEN=... ANTHROPIC_API_KEY=... python benchmarks/analyze_baseline.py --judge-model <id>
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections import Counter
from pathlib import Path

import httpx

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from src.destinations.resolver import get_resolver  # noqa: E402

OURS = "rhincodontypus/official-travel-advisory-comparator"
SCHEMA_FIELDS = {"destination", "sources", "includeRegional"}
API = "https://api.apify.com/v2"
RUBRIC = """Grade the assistant's answer against the Actor's dataset record. Criteria (mark each
"pass", "fail" or "n/a"):
R1 native_wording: each successful government's native level/advice is reported faithfully; does not
   claim the UK (FCDO) uses a formal numbered 1-4 level system.
R2 normalized_vs_official: the shared 1-4 normalized severity is not presented as official government
   terminology (e.g. calling Canada "Level 3" when Canada's wording is different is a fail unless clearly
   labelled as normalized).
R3 regional_vs_national: regional (sub-national) warnings and regionalMax are not presented as the
   country-wide/national advisory.
R4 provenance: the answer attributes advice to the correct governments (names or URLs).
R5 disagreement: if comparison.materialDisagreement is true the answer does not hide that governments
   disagree; if false it does not invent disagreement.
R6 partial_sources: if any requested source failed, the answer does not claim all requested sources
   succeeded.
R7 null_unknown: null/unknown values (e.g. regional data unavailable) are not presented as "no warnings".
R8 answers_question: the answer addresses the user's actual question using the record.
Return only JSON: {"criteria": {"R1": "...", ...}, "correct": true|false, "errors": ["short labels"],
"notes": "one or two sentences"}. "correct" is true only if no criterion fails."""


def apify(path: str) -> dict:
    r = httpx.get(f"{API}{path}", headers={"Authorization": f"Bearer {os.environ['APIFY_TOKEN']}"}, timeout=60)
    r.raise_for_status()
    return r.json()


def judge(model: str, prompt: str, record: dict, answer: str) -> dict:
    body = {
        "model": model,
        "max_tokens": 2000,
        "messages": [
            {
                "role": "user",
                "content": f"{RUBRIC}\n\nUSER QUESTION:\n{prompt}\n\nDATASET RECORD:\n"
                f"{json.dumps(record, ensure_ascii=False)}\n\nASSISTANT ANSWER:\n{answer}",
            }
        ],
    }
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        timeout=180,
        json=body,
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
    )
    r.raise_for_status()
    text = "".join(b["text"] for b in r.json()["content"] if b["type"] == "text")
    return json.loads(text[text.index("{") : text.rindex("}") + 1])


def pct(n: int, d: int) -> float | None:
    return round(100 * n / d, 1) if d else None


def stats(xs: list[float]) -> dict | None:
    if not xs:
        return None
    s = sorted(xs)
    p95 = s[min(len(s) - 1, round(0.95 * (len(s) - 1)))] if len(s) >= 10 else None
    return {
        "n": len(s),
        "min": round(s[0], 3),
        "median": round(statistics.median(s), 3),
        "mean": round(statistics.mean(s), 3),
        "p95": p95 and round(p95, 3),
        "max": round(s[-1], 3),
    }


def expected_iso2(dest: str) -> str | None:
    res = get_resolver().resolve(dest)
    d = getattr(res, "destination", None)
    return getattr(d, "iso2", None)


def score_arm(episodes: list[dict], prompts: dict, judge_model: str | None, arm_name: str, reuse: dict) -> dict:
    rel = [e for e in episodes if prompts[e["id"]]["expectedSelection"]]
    ctl = [e for e in episodes if not prompts[e["id"]]["expectedSelection"]]
    rows, comp_ahead, comp_selected, invocations = [], Counter(), Counter(), []
    for e in episodes:
        p = prompts[e["id"]]
        ranks = [s["oursRank"] for s in e["searches"] if s["oursRank"]]
        rank = min(ranks) if ranks else None
        first = next((s for s in e["searches"] if s["oursRank"]), None)
        ahead = first["ranking"][: first["oursRank"] - 1] if first else []
        returned = sorted({a for s in e["searches"] for a in s["ranking"] if a != OURS})
        sel = e["selected"]
        row = {
            "id": e["id"],
            "category": p["category"],
            "relevant": p["expectedSelection"],
            "prompt": e["prompt"],
            "searchQueries": [s["keywords"] for s in e["searches"]],
            "discovered": rank is not None,
            "rank": rank,
            "competitorsReturned": len(returned),
            "competitorsAhead": ahead,
            "detailsFetched": e["detailsFetched"],
            "selected": sel,
            "oursSelected": sel == OURS,
            "selectionRationale": e.get("selectionRationale"),
            "elapsedS": e["elapsedS"],
        }
        if p["expectedSelection"]:
            for a in ahead:
                comp_ahead[a] += 1
            if rank and sel and sel != OURS:
                comp_selected[sel] += 1
        ours_calls = [c for c in e["actorCalls"] if c["actor"].split(":")[0] == OURS and c.get("executed")]
        call_rows = []
        for c in ours_calls:
            inp = c.get("input") or {}
            sc = c.get("structured") or {}
            run_id = sc.get("runId")
            run = apify(f"/actor-runs/{run_id}")["data"] if run_id else {}
            ds = run.get("defaultDatasetId")
            items = apify(f"/datasets/{ds}/items?clean=1") if ds else []
            items = items if isinstance(items, list) else []
            rec = items[0] if items else {}
            exp = p.get("expectedInput", {})
            exp_iso = expected_iso2(exp["destination"]) if exp.get("destination") else None
            got_iso = (rec.get("query") or {}).get("iso2")
            cr = {
                "runId": run_id,
                "callError": None if run_id else (c.get("resultText") or "")[:400],
                "input": inp,
                "inventedFields": sorted(set(inp) - SCHEMA_FIELDS),
                "destinationCorrect": (got_iso == exp_iso) if p["expectedSelection"] and rec else None,
                "sourcesSupplied": inp.get("sources"),
                "sourcesExpected": exp.get("sources"),
                "accepted": run.get("status") == "SUCCEEDED" and bool(rec),
                "runStatus": run.get("status"),
                "datasetStatus": rec.get("status"),
                "runTimeSecs": (run.get("stats") or {}).get("runTimeSecs"),
                "toolLatencyS": c.get("latencyS"),
                "chargedEventCounts": run.get("chargedEventCounts"),
                "accountedChargedEventCounts": run.get("accountedChargedEventCounts"),
                "billable": (rec.get("billing") or {}).get("billable"),
            }
            cr["valid"] = cr["accepted"] and not cr["inventedFields"] and cr["destinationCorrect"] is not False
            call_rows.append(cr)
            invocations.append(cr)
        row["invocations"] = call_rows
        if (
            call_rows
            and call_rows[-1]["runId"]
            and call_rows[-1]["datasetStatus"] in ("success", "partial")
            and judge_model
        ):
            rec = apify(
                f"/datasets/{apify('/actor-runs/' + call_rows[-1]['runId'])['data']['defaultDatasetId']}/items?clean=1"
            )[0]
            row["finalAnswer"] = e.get("finalAnswer")
            key = (arm_name, e["id"])
            row["interpretation"] = reuse.get(key) or judge(judge_model, e["prompt"], rec, e.get("finalAnswer") or "")
        rows.append(row)

    rr = [r for r in rows if r["relevant"]]
    cr_ = [r for r in rows if not r["relevant"]]
    disc = [r for r in rr if r["discovered"]]
    ranks = [r["rank"] for r in disc]
    sel = [r for r in rr if r["oursSelected"]]
    sel_given_disc = [r for r in disc if r["oursSelected"]]
    sel_rows = [r for r in rows if r["oursSelected"] and r["invocations"]]
    valid = [r for r in sel_rows if r["invocations"][-1]["valid"]]
    first_valid = [r for r in sel_rows if r["invocations"][0]["valid"]]
    executed_ok = [r for r in sel_rows if r["invocations"][-1]["datasetStatus"] in ("success", "partial")]
    interp = [r for r in rows if "interpretation" in r]
    correct = [r for r in interp if r["interpretation"].get("correct")]
    charged = Counter()
    for c in invocations:
        for k, v in (c["chargedEventCounts"] or {}).items():
            charged[k] += v
    unexpected = [
        c["runId"]
        for c in invocations
        if (c["chargedEventCounts"] or {}).get("destination-lookup", 0) and not c["billable"]
    ]
    return {
        "counts": {
            "relevant": len(rel),
            "control": len(ctl),
            "relevantByCategory": dict(Counter(prompts[e["id"]]["category"] for e in rel)),
        },
        "discovery": {
            "rate": pct(len(disc), len(rr)),
            "discovered": len(disc),
            "top1": pct(sum(1 for x in ranks if x <= 1), len(rr)),
            "top3": pct(sum(1 for x in ranks if x <= 3), len(rr)),
            "top5": pct(sum(1 for x in ranks if x <= 5), len(rr)),
            "meanRank": round(statistics.mean(ranks), 2) if ranks else None,
            "medianRank": statistics.median(ranks) if ranks else None,
            "promptsWithAnySearch": sum(1 for r in rr if r["searchQueries"]),
        },
        "selection": {
            "givenDiscovery": pct(len(sel_given_disc), len(disc)),
            "endToEnd": pct(len(sel), len(rr)),
            "selectedCount": len(sel),
            "selectedByTool": dict(Counter(r["selected"] for r in rr)),
        },
        "invocation": {
            "validRate": pct(len(valid), len(sel_rows)),
            "firstAttemptValidRate": pct(len(first_valid), len(sel_rows)),
            "perCallValidRate": pct(sum(c["valid"] for c in invocations), len(invocations)),
            "rejectedCalls": [
                {"input": c["input"], "error": (c["callError"] or "")[:160]} for c in invocations if not c["runId"]
            ],
            "executionSuccessRate": pct(len(executed_ok), len(sel_rows)),
            "callsWithInventedFields": sum(1 for c in invocations if c["inventedFields"]),
            "wrongDestination": sum(1 for c in invocations if c["destinationCorrect"] is False),
        },
        "interpretation": {
            "correctRate": pct(len(correct), len(interp)),
            "graded": len(interp),
            "errors": dict(Counter(x for r in interp for x in r["interpretation"].get("errors", []))),
        },
        "abstention": {
            "controls": len(cr_),
            "falseDiscoveryRate": pct(sum(r["discovered"] for r in cr_), len(cr_)),
            "falseSelectionRate": pct(sum(r["oursSelected"] for r in cr_), len(cr_)),
            "falseInvocationRate": pct(sum(bool(r["invocations"]) for r in cr_), len(cr_)),
            "selectedByTool": dict(Counter(r["selected"] for r in cr_)),
        },
        "economics": {
            "invocations": len(invocations),
            "chargedEventCounts": dict(charged),
            "nominalEventValueUsd": round(
                charged["destination-lookup"] * 0.01 + charged["apify-actor-start"] * 0.00005, 5
            ),
            "accountedDestinationLookups": sum(
                (c["accountedChargedEventCounts"] or {}).get("destination-lookup", 0) for c in invocations
            ),
            "unexpectedLookupCharges": unexpected,
        },
        "latency": {
            "actorRunTimeSecs": stats([c["runTimeSecs"] for c in invocations if c["runTimeSecs"]]),
            "callActorToolLatencyS": stats([c["toolLatencyS"] for c in invocations if c["toolLatencyS"]]),
            "episodeElapsedS": stats([r["elapsedS"] for r in rows if r["oursSelected"]]),
        },
        "competitors": {
            "outrankedOursCount": dict(comp_ahead.most_common()),
            "selectedOverOursCount": dict(comp_selected.most_common()),
        },
        "rows": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge-model")
    ap.add_argument("--out", default=str(HERE / "results" / "baseline-1.0.2.json"))
    ap.add_argument("--reuse-judgments", action="store_true", help="reuse interpretation grades from --out")
    a = ap.parse_args()
    reuse = {}
    if a.reuse_judgments and Path(a.out).exists():
        for arm_name, arm_data in json.loads(Path(a.out).read_text())["arms"].items():
            for row in arm_data["rows"]:
                if "interpretation" in row:
                    reuse[(arm_name, row["id"])] = row["interpretation"]
    prompts = {p["id"]: p for p in json.loads((HERE / "agent_selection_prompts.json").read_text())["prompts"]}
    result = {"actor": OURS, "actorBuild": "1.0.2", "judgeModel": a.judge_model, "arms": {}}
    for arm in ("default", "directed"):
        f = HERE / "results" / f"raw-{arm}-1.0.2.jsonl"
        eps = [json.loads(line) for line in f.read_text().splitlines()]
        result["arms"][arm] = {
            "model": eps[0]["model"],
            "mcpServer": eps[0]["mcpServer"].get("version"),
            "mcpTools": eps[0]["mcpTools"],
            "firstEpisodeAt": eps[0]["startedAt"],
            **score_arm(eps, prompts, a.judge_model if arm == "directed" else None, arm, reuse),
        }
    Path(a.out).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    for arm, r in result["arms"].items():
        print(arm, {k: r[k] for k in ("discovery", "selection", "invocation", "interpretation", "abstention")})


if __name__ == "__main__":
    main()
