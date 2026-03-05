from __future__ import annotations

import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.main import SessionLocal  # uses DATABASE_URL
from app.extraction.seed import seed_from_student_folder
from app.extraction.pipeline import run_extraction as run_extraction_pipeline
from app.main import run_decision_for_case_and_run

CASES = [
    ("CASE01", "Alice Johnson",  "COMP 1000"),
    ("CASE02", "Brian Lee",      "COMP 1200"),
    ("CASE03", "Carla Gomez",    "COMP 2000"),
    ("CASE04", "Daniel Kim",     "COMP 2100"),
    ("CASE05", "Elena Martinez", "COMP 2200"),
    ("CASE06", "Farah Ahmed",    "COMP 2300"),
    ("CASE07", "George Patel",   "COMP 2400"),
    ("CASE08", "Hannah Wright",  "COMP 2500"),
    ("CASE09", "Ivan Novak",     "COMP 2600"),
    ("CASE10", "Julia Chen",     "COMP 2700"),
]

BASE_FOLDER = Path("Data/Raw/StudentTestCases")


def db_session() -> Session:
    return SessionLocal()


def get_demo_reviewer_ids(db: Session) -> list[uuid.UUID]:
    rows = db.execute(
        text("""
            SELECT reviewer_id, utc_id, reviewer_name
            FROM reviewers
            WHERE utc_id IN ('rev001', 'rev002', 'rev003')
            ORDER BY utc_id
        """)
    ).fetchall()

    if len(rows) != 3:
        found = [(r[1], r[2]) for r in rows]
        raise RuntimeError(
            "Expected exactly 3 demo reviewers (rev001, rev002, rev003) "
            f"but found {len(rows)}: {found}. "
            "Did you run Database/setup_ai_db_demo.sql?"
        )

    return [r[0] for r in rows]


def assign_case_fields(
    db: Session,
    request_id: uuid.UUID,
    student_name: str,
    course_requested: str,
    reviewer_id: uuid.UUID,
):
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


def main():
    with db_session() as db:
        reviewer_ids = get_demo_reviewer_ids(db)

    for idx, (student_id, student_name, course_requested) in enumerate(CASES):
        folder = BASE_FOLDER / student_id
        if not folder.exists():
            raise RuntimeError(f"Missing folder: {folder}")

        seeded = seed_from_student_folder(str(folder), student_id=student_id)
        case_uuid = uuid.UUID(str(seeded.request_id))

        reviewer_id = reviewer_ids[idx % len(reviewer_ids)]
        with db_session() as db:
            assign_case_fields(db, case_uuid, student_name, course_requested, reviewer_id)

        extraction_run_id_str = run_extraction_pipeline(str(case_uuid))
        extraction_run_uuid = uuid.UUID(extraction_run_id_str)

        with db_session() as db:
            decision_run_id = run_decision_for_case_and_run(db, case_uuid, extraction_run_uuid)
            db.commit()

        print(f"{student_id}: case={case_uuid} extraction={extraction_run_uuid} decision={decision_run_id}")

    print("seed complete")


if __name__ == "__main__":
    main()