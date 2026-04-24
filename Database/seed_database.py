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

from app.main import SessionLocal, Course  # uses DATABASE_URL
from app.extraction.seed import seed_from_student_folder
from app.extraction.pipeline import run_extraction as run_extraction_pipeline
from app.main import run_decision_for_case_and_run
from app.auth import hash_password

CASES = [
    ("CASE01", "Alice Johnson",  "NURS 2260"),    # General Pathology -> Pathophysiology
    ("CASE02", "Brian Lee",      "BIOL 2010"),    # Anatomy & Physiology -> Anatomy & Physiology I
    ("CASE03", "Carla Gomez",    "CHEM 4510"),    # Biochemistry -> Biochemistry
    ("CASE04", "Daniel Kim",     "BIOL 3060"),    # Principles of Ecology -> Ecology
    ("CASE05", "Elena Martinez", "NURS 2260"),    # Clinical Pathology -> Pathophysiology
    ("CASE06", "Farah Ahmed",    "HHP 3450"),     # Classics in Neuroscience -> Neuroscience and Neurofeedback
    ("CASE07", "George Patel",   "CHEM 3710"),    # CBE Thermodynamics -> Physical Chemistry: Thermo & Kinetics
    ("CASE08", "Hannah Wright",  "COMM 2310"),    # Leadership and Communication -> Multimedia Journalism
    ("CASE09", "Ivan Novak",     "MATH 2100"),    # Statistical Programming with R -> Introductory Statistics
    ("CASE10", "Julia Chen",     "ESC 1500"),     # Intro Complex Environmental Systems -> Intro Environmental Science I
]

BASE_FOLDER = Path("Data/Raw/StudentTestCases")


def db_session() -> Session:
    return SessionLocal()


def get_demo_reviewer_ids(db: Session) -> list[uuid.UUID]:
    rows = db.execute(
        text("""
            SELECT reviewer_id, utc_id, reviewer_name
            FROM reviewers
            WHERE utc_id IN ('rev001', 'rev002', 'rev003', 'rev004', 'rev005', 'rev006')
            ORDER BY utc_id
        """)
    ).fetchall()

    if len(rows) < 4:
        found = [(r[1], r[2]) for r in rows]
        raise RuntimeError(
            "Expected at least 4 demo reviewers "
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


def hash_reviewer_passwords(db: Session):
    """Replace plain-text passwords with hashed passwords for all reviewers."""
    rows = db.execute(text("SELECT utc_id, password_hash FROM reviewers")).fetchall()
    for utc_id, pw in rows:
        if ":" not in (pw or ""):  # not yet hashed
            db.execute(
                text("UPDATE reviewers SET password_hash = :hashed WHERE utc_id = :utc_id"),
                {"hashed": hash_password(pw or "password123"), "utc_id": utc_id},
            )
    db.commit()
    print(f"Hashed passwords for {len(rows)} reviewers")


def seed_courses_from_csv(db: Session):
    """Load all courses from Data/Processed/ParsedData.csv into the courses table."""
    import csv

    csv_path = REPO_ROOT / "Data" / "Processed" / "ParsedData.csv"
    if not csv_path.exists():
        print(f"CSV not found at {csv_path}, skipping course seed")
        return

    existing_codes = {r[0] for r in db.query(Course.course_code).all()}
    if existing_codes:
        print(f"Courses table already has {len(existing_codes)} records, skipping CSV seed")
        return

    seen_codes = set()
    inserted = 0
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            course_code = (row.get("course_code") or "").strip()
            if not course_code or course_code in seen_codes:
                continue
            seen_codes.add(course_code)
            try:
                credits = int(float(row.get("credits_min") or 3))
            except (ValueError, TypeError):
                credits = 3
            department = (row.get("subject") or "").strip() or "General"
            db.add(Course(
                course_code=course_code,
                display_name=(row.get("title") or "").strip() or course_code,
                department=department,
                credits=credits,
                lab_required=False,
                prerequisites=(row.get("prerequisites") or "").strip() or None,
                required_topics=[],
                required_outcomes=[],
                description=(row.get("description") or "").strip() or None,
            ))
            inserted += 1
    db.commit()
    print(f"Seeded {inserted} courses from CSV")


def main():
    with db_session() as db:
        hash_reviewer_passwords(db)
        seed_courses_from_csv(db)
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

        try:
            extraction_run_id_str = run_extraction_pipeline(str(case_uuid))
            extraction_run_uuid = uuid.UUID(extraction_run_id_str)

            with db_session() as db:
                decision_run_id = run_decision_for_case_and_run(db, case_uuid, extraction_run_uuid)
                db.commit()

            print(f"{student_id}: case={case_uuid} extraction={extraction_run_uuid} decision={decision_run_id}")

        except Exception as e:
            import traceback
            print(f"{student_id}: SKIPPED — {e}")
            traceback.print_exc()

    print("seed complete")


if __name__ == "__main__":
    main()