#!/usr/bin/env python3
"""
llm_probe.py

Offline LLM probe — calls call_llm_decision() directly against each labeled
demo case and reports LLM accuracy + LLM-vs-deterministic-engine agreement.

No backend or database required. Only needs OPENAI_API_KEY in .env.

Usage:
    python llm_probe.py
    python llm_probe.py --case case01_approve_full.json
    python llm_probe.py --out demo_results/llm_probe_results.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

from eval_engine_offline import facts_to_evidence, load_policy, load_target
from decision_engine.contracts import DecisionInputsPacket, decide
from decision_engine.llm_decision import call_llm_decision


REPO_ROOT = Path(__file__).resolve().parent
DEMO_DIR = REPO_ROOT / "demo_cases"
RESULTS_DIR = REPO_ROOT / "demo_results"


def mock_evidence_rows(facts: list) -> list:
    """Convert demo-case fact dicts into objects the prompt formatter can read.

    llm_decision._format_evidence_for_prompt expects attributes:
    evidence_id, unknown, fact_value, fact_json, fact_key, fact_type
    """
    rows = []
    for f in facts:
        rows.append(SimpleNamespace(
            evidence_id=uuid.uuid4(),
            fact_type=f.get("factType", "course"),
            fact_key=f.get("factKey", ""),
            fact_value=f.get("factValue"),
            fact_json=f.get("factJson"),
            unknown=bool(f.get("unknown", False)),
        ))
    return rows


def run_case(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    target_code = payload.get("_target_course_requested")
    expected = (payload.get("_expected_decision") or "").strip().upper() or None

    evidence = facts_to_evidence(payload.get("facts", []))
    target = load_target(target_code)
    policy = load_policy()

    packet = DecisionInputsPacket(
        case_id=path.stem,
        source_course=evidence,
        target_course=target,
        policy=policy,
    )

    # Deterministic engine — for agreement comparison
    eng_result = decide(packet)
    engine_decision = eng_result.decision.value

    # LLM
    try:
        evidence_rows = mock_evidence_rows(payload.get("facts", []))
        llm_result = call_llm_decision(packet, evidence_rows, chunks_by_evidence={})
        llm_decision = llm_result.decision.value
        llm_score = llm_result.equivalency_score
        llm_conf = llm_result.confidence.value
        err = ""
    except Exception as e:
        llm_decision = "ERROR"
        llm_score = 0
        llm_conf = "N/A"
        err = str(e)[:120]

    return {
        "case": path.name,
        "target": target_code or "(fallback)",
        "expected": expected or "(unlabeled)",
        "engine": engine_decision,
        "llm": llm_decision,
        "llm_score": llm_score,
        "llm_conf": llm_conf,
        "eng_vs_expected": "YES" if expected and expected == engine_decision else ("-" if not expected else "NO"),
        "llm_vs_expected": "YES" if expected and expected == llm_decision else ("-" if not expected else "NO"),
        "llm_vs_engine": "YES" if llm_decision == engine_decision else "NO",
        "error": err,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--case", help="Run single case filename (default: all)")
    p.add_argument("--out", default=str(RESULTS_DIR / "llm_probe_results.csv"))
    args = p.parse_args()

    if args.case:
        files = [DEMO_DIR / args.case]
    else:
        files = sorted(DEMO_DIR.glob("case*.json"))

    rows = []
    for f in files:
        print(f"-> {f.name}")
        rows.append(run_case(f))

    # Report
    print()
    header = f"{'Case':55s} {'Expected':22s} {'Engine':22s} {'LLM':22s} {'EngOK':6s} {'LLMOK':6s} {'Agree':6s}"
    print(header)
    print("-" * len(header))
    eng_match = llm_match = llm_eng_agree = labeled = 0
    for r in rows:
        print(f"{r['case']:55s} {r['expected']:22s} {r['engine']:22s} {r['llm']:22s} {r['eng_vs_expected']:6s} {r['llm_vs_expected']:6s} {r['llm_vs_engine']:6s}")
        if r["expected"] != "(unlabeled)":
            labeled += 1
            if r["eng_vs_expected"] == "YES":
                eng_match += 1
            if r["llm_vs_expected"] == "YES":
                llm_match += 1
        if r["llm_vs_engine"] == "YES":
            llm_eng_agree += 1

    print()
    if labeled:
        print(f"Engine accuracy: {eng_match}/{labeled} = {100*eng_match/labeled:.1f}%")
        print(f"LLM accuracy:    {llm_match}/{labeled} = {100*llm_match/labeled:.1f}%")
    print(f"LLM-vs-Engine agreement: {llm_eng_agree}/{len(rows)} = {100*llm_eng_agree/len(rows):.1f}%")

    # CSV
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote: {args.out}")


if __name__ == "__main__":
    main()
