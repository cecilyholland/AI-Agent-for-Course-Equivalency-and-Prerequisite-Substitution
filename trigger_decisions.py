"""
One-time script to run the decision engine on all cases
that are stuck in ready_for_decision state.
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Request, ExtractionRun

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# Import decision logic from main (after env is loaded)
from app.main import run_decision_for_case_and_run

def main():
    db = SessionLocal()
    try:
        cases = db.query(Request).filter(Request.status == "ready_for_decision").all()
        print(f"Found {len(cases)} cases to process\n")

        for case in cases:
            run = (
                db.query(ExtractionRun)
                .filter(
                    ExtractionRun.request_id == case.request_id,
                    ExtractionRun.status == "completed",
                )
                .order_by(ExtractionRun.created_at.desc())
                .first()
            )

            if not run:
                print(f"[SKIP] {case.request_id} — no completed extraction run")
                continue

            try:
                decision_run_id = run_decision_for_case_and_run(
                    db, case.request_id, run.extraction_run_id
                )
                db.commit()
                db.refresh(case)
                print(f"[OK]   {case.request_id} → {case.status}  (decision run: {decision_run_id})")
            except Exception as e:
                db.rollback()
                print(f"[ERR]  {case.request_id} → {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
