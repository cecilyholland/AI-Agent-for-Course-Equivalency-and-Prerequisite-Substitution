#!/usr/bin/env python3
"""
eval_engine_offline.py

Offline evaluation harness for the decision engine.

Unlike run_demo_cases.py (which needs the live FastAPI backend), this script
loads demo_cases/*.json directly, converts each fact list into a
CourseEvidence, loads the target profile from config/target_courses.yaml (using
the `_target_course_requested` field in each case file, falling back to a
permissive default), runs decide(), and reports agreement vs `_expected_decision`.

Usage:
    python eval_engine_offline.py
    python eval_engine_offline.py --cases demo_cases --out eval_results.csv
    python eval_engine_offline.py --filter redteam          # only redteam*.json
    python eval_engine_offline.py --target CPSC-2150        # force this target

Outputs:
    eval_results.csv — per-case summary (expected vs actual + score/confidence/quality)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from decision_engine.contracts import (
    CourseEvidence, DecisionInputsPacket, EvidenceField,
    PolicyConfig, TargetCourseProfile, decide,
)


REPO_ROOT = Path(__file__).resolve().parent
CONFIG_DIR = REPO_ROOT / "config"


def load_policy() -> PolicyConfig:
    with open(CONFIG_DIR / "policy.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return PolicyConfig(**data)


def load_target(code: Optional[str]) -> TargetCourseProfile:
    # Permissive default target — GPT handles per-target topic reasoning in the
    # real pipeline. This harness uses the same fallback so offline eval matches
    # what the backend produces.
    return TargetCourseProfile(
        target_credits=3, target_lab_required=False,
        required_topics=[], required_outcomes=[],
    )


def facts_to_evidence(facts: List[Dict[str, Any]]) -> CourseEvidence:
    """Mirror app.main.map_evidence_rows_to_course_evidence for offline use."""
    fields: Dict[str, EvidenceField] = {
        key: EvidenceField(value=None, unknown=True, citations=[])
        for key in [
            "credits", "contact_hours_lecture", "contact_hours_lab",
            "lab_component", "topics", "outcomes", "assessments",
        ]
    }
    fields["grade"] = EvidenceField(unknown=True)
    fields["term_taken"] = EvidenceField(unknown=True)

    key_map = {
        "credits": "credits", "credit_hours": "credits", "units": "credits",
        "contact_hours_lecture": "contact_hours_lecture", "lecture_hours": "contact_hours_lecture",
        "contact_hours_lab": "contact_hours_lab", "lab_hours": "contact_hours_lab",
        "lab_component": "lab_component", "has_lab": "lab_component",
        "topics": "topics", "course_topics": "topics",
        "outcomes": "outcomes", "learning_outcomes": "outcomes", "slos": "outcomes",
        "assessments": "assessments", "evaluation_methods": "assessments",
        "grade": "grade",
        "term_taken": "term_taken", "semester": "term_taken",
    }

    for fact in facts:
        raw_key = (fact.get("factKey") or fact.get("factType") or "").strip().lower()
        mapped = key_map.get(raw_key)
        if not mapped:
            continue

        v = fact.get("factJson") or fact.get("factValue")
        if isinstance(v, dict) and "items" in v and isinstance(v["items"], list):
            v = v["items"]

        if mapped == "lab_component" and isinstance(v, str):
            s = v.strip().lower()
            if s in {"true", "yes", "1"}:
                v = True
            elif s in {"false", "no", "0"}:
                v = False

        fields[mapped] = EvidenceField(value=v, unknown=bool(fact.get("unknown", False)))

    return CourseEvidence(**fields)


def run_case(path: Path, default_target: Optional[str]) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    target_code = default_target or payload.get("_target_course_requested")
    expected = (payload.get("_expected_decision") or "").strip().upper() or None
    description = payload.get("_description", "")

    evidence = facts_to_evidence(payload.get("facts", []))
    target = load_target(target_code)
    policy = load_policy()

    result = decide(DecisionInputsPacket(
        case_id=path.stem,
        source_course=evidence,
        target_course=target,
        policy=policy,
    ))

    actual = result.decision.value
    matches = (expected is None) or (expected == actual)

    return {
        "case": path.name,
        "target_course": target_code or "(fallback)",
        "expected": expected or "(unlabeled)",
        "actual": actual,
        "matches": "YES" if expected and matches else ("-" if expected is None else "NO"),
        "score": result.equivalency_score,
        "confidence": result.confidence.value,
        "evidence_quality": result.evidence_quality_score,
        "hard_gaps": len([g for g in result.gaps if g.severity == "HARD"]),
        "info_missing_gaps": len([g for g in result.gaps if g.severity == "INFO_MISSING"]),
        "bridge_items": len(result.bridge_plan_items),
        "description": description[:80],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="demo_cases", help="Directory of *.json case files")
    ap.add_argument("--out", default="demo_results/eval_offline_results.csv")
    ap.add_argument("--filter", default="", help="Only run cases whose filename contains this substring")
    ap.add_argument("--target", default=None, help="Force this target course for every case")
    args = ap.parse_args()

    cases_dir = REPO_ROOT / args.cases
    if not cases_dir.exists():
        print(f"ERROR: cases dir not found: {cases_dir}", file=sys.stderr)
        sys.exit(1)

    files = sorted(p for p in cases_dir.glob("*.json") if args.filter in p.name)
    if not files:
        print(f"No case files found in {cases_dir} matching '{args.filter}'")
        return

    rows: List[Dict[str, Any]] = []
    for p in files:
        print(f"-> {p.name}")
        try:
            rows.append(run_case(p, args.target))
        except Exception as e:
            print(f"  [error] {e}")
            rows.append({
                "case": p.name, "target_course": args.target or "?",
                "expected": "?", "actual": "ERROR",
                "matches": "NO", "score": 0, "confidence": "?", "evidence_quality": 0,
                "hard_gaps": 0, "info_missing_gaps": 0, "bridge_items": 0,
                "description": str(e)[:80],
            })

    # Write CSV
    out_path = REPO_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # Print summary
    print()
    print(f"{'Case':<50s}  {'Target':<12s}  {'Expected':<22s}  {'Actual':<22s}  {'Match':<5s}  {'Score':<5s}  {'Conf':<6s}  EQ")
    print("-" * 150)
    for r in rows:
        print(f"{r['case']:<50s}  {r['target_course']:<12s}  {r['expected']:<22s}  {r['actual']:<22s}  {r['matches']:<5s}  {r['score']:<5d}  {r['confidence']:<6s}  {r['evidence_quality']}")

    labeled = [r for r in rows if r["expected"] not in ("?", "(unlabeled)")]
    agreements = sum(1 for r in labeled if r["matches"] == "YES")
    total_labeled = len(labeled)

    print()
    if total_labeled:
        pct = 100 * agreements / total_labeled
        print(f"Agreement (labeled cases): {agreements}/{total_labeled} = {pct:.1f}%")
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
