"""
Run cases 1-10 through the full pipeline (create case, extract, decide)
and record results to demo_results/demo_results.json.

Usage:
    python run_cases.py
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.main import SessionLocal
from app.extraction.seed import seed_from_student_folder
from app.extraction.pipeline import run_extraction as run_extraction_pipeline
from app.main import run_decision_for_case_and_run

CASES = [
    ("CASE01", "Alice Johnson",  "NURS 2260"),
    ("CASE02", "Brian Lee",      "BIOL 2010"),
    ("CASE03", "Carla Gomez",    "CHEM 4510"),
    ("CASE04", "Daniel Kim",     "BIOL 3060"),
    ("CASE05", "Elena Martinez", "NURS 2260"),
    ("CASE06", "Farah Ahmed",    "HHP 3450"),
    ("CASE07", "George Patel",   "CHEM 3710"),
    ("CASE08", "Hannah Wright",  "COMM 2310"),
    ("CASE09", "Ivan Novak",     "MATH 2100"),
    ("CASE10", "Julia Chen",     "ESC 1500"),
]

BASE_FOLDER = Path("Data/Raw/StudentTestCases")
OUTPUT_DIR = Path("demo_results")


def db_session() -> Session:
    return SessionLocal()


def get_reviewer_id(db: Session) -> uuid.UUID:
    row = db.execute(
        text("SELECT reviewer_id FROM reviewers ORDER BY utc_id LIMIT 1")
    ).fetchone()
    if not row:
        raise RuntimeError("No reviewers found. Run setup_ai_db_demo.sql first.")
    return row[0]


def assign_case_fields(db, request_id, student_name, course_requested, reviewer_id):
    db.execute(
        text("""
            UPDATE requests
            SET student_name = :student_name,
                course_requested = :course_requested,
                assigned_reviewer_id = :reviewer_id,
                updated_at = NOW()
            WHERE request_id = :request_id
        """),
        {
            "student_name": student_name,
            "course_requested": course_requested,
            "reviewer_id": reviewer_id,
            "request_id": request_id,
        },
    )
    db.commit()


def fetch_decision(db: Session, case_id: uuid.UUID) -> dict | None:
    row = db.execute(
        text("""
            SELECT dr.result_json
            FROM decision_runs drun
            JOIN decision_results dr ON dr.decision_run_id = drun.decision_run_id
            WHERE drun.request_id = :case_id AND drun.status = 'completed'
            ORDER BY dr.created_at DESC LIMIT 1
        """),
        {"case_id": case_id},
    ).fetchone()
    return row[0] if row else None


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    results = []

    with db_session() as db:
        reviewer_id = get_reviewer_id(db)

    for case_id_str, student_name, target_course in CASES:
        folder = BASE_FOLDER / case_id_str
        if not folder.exists():
            print(f"{case_id_str}: SKIPPED — folder {folder} not found")
            results.append({
                "case": case_id_str,
                "student_name": student_name,
                "target_course": target_course,
                "status": "SKIPPED",
                "error": f"folder {folder} not found",
            })
            continue

        print(f"{case_id_str}: Creating case for {student_name} -> {target_course}...")

        try:
            seeded = seed_from_student_folder(str(folder), student_id=case_id_str)
            case_uuid = uuid.UUID(str(seeded.request_id))

            with db_session() as db:
                assign_case_fields(db, case_uuid, student_name, target_course, reviewer_id)

            extraction_run_id_str = run_extraction_pipeline(str(case_uuid))
            extraction_run_uuid = uuid.UUID(extraction_run_id_str)

            with db_session() as db:
                decision_run_id = run_decision_for_case_and_run(db, case_uuid, extraction_run_uuid)
                db.commit()

            with db_session() as db:
                result_json = fetch_decision(db, case_uuid)

            if result_json:
                decision = result_json.get("decision", "UNKNOWN")
                score = result_json.get("equivalency_score", 0)
                confidence = result_json.get("confidence", "UNKNOWN")
                reasons = [r.get("text", "") for r in result_json.get("reasons", [])]
                gaps = [g.get("text", "") for g in result_json.get("gaps", [])]
            else:
                decision = score = confidence = "N/A"
                reasons = gaps = []

            print(f"  -> {decision} | score={score} | confidence={confidence}")

            results.append({
                "case": case_id_str,
                "student_name": student_name,
                "target_course": target_course,
                "status": "OK",
                "decision": decision,
                "equivalency_score": score,
                "confidence": confidence,
                "reasons": reasons,
                "gaps": gaps,
            })

        except Exception as e:
            print(f"  -> ERROR: {e}")
            results.append({
                "case": case_id_str,
                "student_name": student_name,
                "target_course": target_course,
                "status": "ERROR",
                "error": str(e),
            })

    # Write results
    output_file = OUTPUT_DIR / "demo_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    # Print summary table
    print("\n" + "=" * 80)
    print(f"{'Case':<8} {'Student':<18} {'Target':<12} {'Decision':<22} {'Score':<6} {'Confidence'}")
    print("-" * 80)
    for r in results:
        if r["status"] == "OK":
            print(f"{r['case']:<8} {r['student_name']:<18} {r['target_course']:<12} {r['decision']:<22} {r['equivalency_score']:<6} {r['confidence']}")
        else:
            print(f"{r['case']:<8} {r['student_name']:<18} {r['target_course']:<12} {r['status']}: {r.get('error','')}")
    print("=" * 80)
    print(f"\nResults saved to {output_file}")


if __name__ == "__main__":
    main()
