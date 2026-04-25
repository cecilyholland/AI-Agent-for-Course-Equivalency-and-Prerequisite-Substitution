"""
Lightweight startup seed for Docker — hashes reviewer passwords
and loads courses from CSV. Does NOT run extraction or decision pipelines.
"""
from __future__ import annotations
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.main import SessionLocal, Course
from app.auth import hash_password
from Database.seed_database import hash_reviewer_passwords, seed_courses_from_csv


def main():
    with SessionLocal() as db:
        hash_reviewer_passwords(db)
        seed_courses_from_csv(db)
    print("Docker startup seed complete")


if __name__ == "__main__":
    main()
