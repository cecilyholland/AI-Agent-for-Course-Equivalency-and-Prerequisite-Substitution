#!/usr/bin/env python3
"""
run_demo_cases.py

Runs your demo payloads (demo_cases/*.json) end-to-end against your FastAPI backend:

1) POST /api/cases            (multipart: form fields + 1 PDF file)
2) POST /api/cases/{caseId}/extraction/start
3) POST /api/cases/{caseId}/extraction/complete   (using facts from each demo payload)
4) GET  /api/cases/{caseId}/decision/result/latest

Outputs:
- demo_results.json (full responses per case)
- demo_results.csv  (summary for quick midterm reporting)

Assumptions (adjust if your API differs):
- /api/cases accepts multipart form fields: studentId, studentName, courseRequested
- file field name is "files" and accepts a PDF
- extraction complete payload format: {"extractionRunId": "...", "facts": [...]}
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def save_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def post_create_case(
    base_url: str,
    pdf_path: Path,
    student_id: str,
    student_name: str,
    course_requested: str,
    timeout_s: int,
) -> str:
    url = f"{base_url}/api/cases"
    if not pdf_path.exists():
        die(f"PDF not found: {pdf_path}")

    # Your API likely expects multipart form + file upload.
    data = {
        "studentId": student_id,
        "studentName": student_name,
        "courseRequested": course_requested,
    }
    files = [
        ("files", (pdf_path.name, pdf_path.read_bytes(), "application/pdf")),
    ]

    r = requests.post(url, data=data, files=files, timeout=timeout_s)
    if r.status_code != 200:
        die(f"POST /api/cases failed ({r.status_code}): {r.text}")

    js = r.json()
    case_id = js.get("caseId") or js.get("requestId") or js.get("id")
    if not case_id:
        die(f"Could not find caseId in /api/cases response: {js}")
    return case_id


def post_extraction_start(base_url: str, case_id: str, timeout_s: int) -> str:
    url = f"{base_url}/api/cases/{case_id}/extraction/start"
    r = requests.post(url, timeout=timeout_s)
    if r.status_code != 200:
        die(f"POST /extraction/start failed ({r.status_code}): {r.text}")

    js = r.json()
    run_id = js.get("extractionRunId")
    if not run_id:
        die(f"Could not find extractionRunId in /extraction/start response: {js}")
    return run_id


def post_extraction_complete(
    base_url: str,
    case_id: str,
    run_id: str,
    facts_payload: Dict[str, Any],
    timeout_s: int,
) -> Dict[str, Any]:
    url = f"{base_url}/api/cases/{case_id}/extraction/complete"

    payload = dict(facts_payload)
    payload["extractionRunId"] = run_id

    r = requests.post(url, json=payload, timeout=timeout_s)
    if r.status_code != 200:
        # 422 is common for schema validation; include response text
        die(f"POST /extraction/complete failed ({r.status_code}): {r.text}")
    return r.json()


def get_latest_decision(base_url: str, case_id: str, timeout_s: int) -> Dict[str, Any]:
    url = f"{base_url}/api/cases/{case_id}/decision/result/latest"
    r = requests.get(url, timeout=timeout_s)
    if r.status_code != 200:
        die(f"GET /decision/result/latest failed ({r.status_code}): {r.text}")
    return r.json()


def summarize_case(
    payload_name: str,
    case_id: str,
    extraction_run_id: str,
    complete_resp: Dict[str, Any],
    latest_resp: Dict[str, Any],
) -> Dict[str, Any]:
    # Try to be resilient to your response shape
    decision = None
    score = None
    confidence = None
    needs_more_info = None

    # Your /decision/result/latest response example includes decisionInputs and likely resultJson
    result_json = latest_resp.get("resultJson") or latest_resp.get("result_json") or {}
    needs_more_info = latest_resp.get("needsMoreInfo", latest_resp.get("needs_more_info"))

    if isinstance(result_json, dict):
        decision = result_json.get("decision")
        score = result_json.get("equivalency_score") or result_json.get("equivalencyScore")
        confidence = result_json.get("confidence")

    return {
        "payload": payload_name,
        "case_id": case_id,
        "extraction_run_id": extraction_run_id,
        "decision_run_id": complete_resp.get("decisionRunId") or latest_resp.get("decisionRunId"),
        "case_status": complete_resp.get("caseStatus") or latest_resp.get("status"),
        "decision": decision,
        "equivalency_score": score,
        "confidence": confidence,
        "needs_more_info": needs_more_info,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000", help="FastAPI base URL")
    ap.add_argument("--cases-dir", default="demo_cases", help="Folder containing *.json payloads")
    ap.add_argument("--pdf", default="demo_syllabus.pdf", help="PDF to upload for each case")
    ap.add_argument("--student-id", default="S-DEMO", help="Student ID used for case creation")
    ap.add_argument("--student-name", default="Demo Student", help="Student name used for case creation")
    ap.add_argument("--course-requested", default="CPSC-DEMO", help="Course requested field")
    ap.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
    ap.add_argument("--sleep", type=float, default=0.0, help="Seconds to sleep between cases")
    ap.add_argument("--out-json", default="demo_results/demo_results.json")
    ap.add_argument("--out-csv", default="demo_results/demo_results.csv")
    args = ap.parse_args()

    base_url = args.base_url.rstrip("/")
    cases_dir = Path(args.cases_dir)
    pdf_path = Path(args.pdf)

    if not cases_dir.exists():
        die(f"cases dir not found: {cases_dir}")

    payload_files = sorted([p for p in cases_dir.glob("*.json") if p.is_file()])
    if not payload_files:
        die(f"No payloads found in {cases_dir} (expected *.json)")

    all_results: List[Dict[str, Any]] = []
    summary_rows: List[Dict[str, Any]] = []

    for p in payload_files:
        payload_name = p.name
        print(f"\n=== Running {payload_name} ===")

        facts_payload = load_json(p)
        if "facts" not in facts_payload or not isinstance(facts_payload["facts"], list):
            die(f"{payload_name} must contain a top-level 'facts' list")

        # 1) create case
        case_id = post_create_case(
            base_url=base_url,
            pdf_path=pdf_path,
            student_id=args.student_id,
            student_name=args.student_name,
            course_requested=args.course_requested,
            timeout_s=args.timeout,
        )
        print(f"caseId = {case_id}")

        # 2) start extraction
        run_id = post_extraction_start(base_url=base_url, case_id=case_id, timeout_s=args.timeout)
        print(f"extractionRunId = {run_id}")

        # 3) complete extraction (auto-triggers decision)
        complete_resp = post_extraction_complete(
            base_url=base_url,
            case_id=case_id,
            run_id=run_id,
            facts_payload=facts_payload,
            timeout_s=args.timeout,
        )
        print(f"complete: decisionRunId = {complete_resp.get('decisionRunId')} caseStatus = {complete_resp.get('caseStatus')}")

        # 4) fetch latest decision
        latest = get_latest_decision(base_url=base_url, case_id=case_id, timeout_s=args.timeout)
        result_json = latest.get("resultJson") or {}
        decision = result_json.get("decision") if isinstance(result_json, dict) else None
        print(f"latest decision = {decision}")

        # store detailed + summary
        all_results.append(
            {
                "payload": payload_name,
                "caseId": case_id,
                "extractionRunId": run_id,
                "extractionCompleteResponse": complete_resp,
                "latestDecisionResponse": latest,
            }
        )
        summary_rows.append(summarize_case(payload_name, case_id, run_id, complete_resp, latest))

        if args.sleep > 0:
            time.sleep(args.sleep)

    out_json = Path(args.out_json)
    out_csv = Path(args.out_csv)
    save_json(out_json, all_results)

    fieldnames = [
        "payload",
        "case_id",
        "extraction_run_id",
        "decision_run_id",
        "case_status",
        "decision",
        "equivalency_score",
        "confidence",
        "needs_more_info",
    ]
    save_csv(out_csv, summary_rows, fieldnames=fieldnames)

    print("\n=== DONE ===")
    print(f"Wrote: {out_json}")
    print(f"Wrote: {out_csv}")


if __name__ == "__main__":
    main()