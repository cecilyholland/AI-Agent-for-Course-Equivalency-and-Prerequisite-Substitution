# main.py

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException, Query
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session


from models import (
    Base,
    Request,
    Document,
    ExtractionRun,
    DecisionRun,
    ReviewAction,
    GroundedEvidence,
)
from schemas import CaseOut, DocumentOut, CaseDetailOut, ReviewIn

# -----------------------------
# Database setup
# -----------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
print("DATABASE_URL =", DATABASE_URL)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

Base.metadata.create_all(bind=engine)

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="Course Equivalency Backend")


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"ok": True}

# -----------------------------
# Status mapping (DB → Frontend)
# -----------------------------
DB_TO_FE_STATUS = {
    "uploaded": "UPLOADED",
    "extracting": "EXTRACTING",
    "needs_info": "NEEDS_INFO",
    "ready_for_decision": "READY_FOR_DECISION",
    "ai_recommendation": "DECIDED",
    "review_pending": "REVIEW_PENDING",
    "reviewed": "REVIEWED",
}



def to_frontend_status(db_status: str) -> str:
    return DB_TO_FE_STATUS.get(db_status, db_status)


# -----------------------------
# Helpers
# -----------------------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def compute_sha256(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def save_upload(file: UploadFile) -> Dict[str, Any]:
    raw = file.file.read()
    sha = compute_sha256(raw)
    safe_name = f"{uuid.uuid4()}_{file.filename}"
    path = os.path.join(UPLOAD_DIR, safe_name)
    with open(path, "wb") as f:
        f.write(raw)
    return {
        "filename": file.filename,
        "content_type": file.content_type or "application/octet-stream",
        "sha256": sha,
        "storage_uri": path,
        "size_bytes": len(raw),
    }


def case_to_out(r: Request) -> CaseOut:
    return CaseOut(
        caseId=str(r.request_id),          # ✅ cast UUID → str
        studentId=r.student_id,
        studentName=r.student_name,
        courseRequested=r.course_requested,
        status=to_frontend_status(r.status),
        createdAt=r.created_at,
        updatedAt=r.updated_at,
    )


def doc_to_out(d: Document) -> DocumentOut:
    return DocumentOut(
        docId=str(d.doc_id),               # ✅ cast UUID → str
        filename=d.filename,
        sha256=d.sha256,
        storageUri=d.storage_uri,
        createdAt=d.created_at,
        isActive=d.is_active,
    )



def get_latest_extraction_run(db: Session, request_id: str) -> Optional[ExtractionRun]:
    return (
        db.query(ExtractionRun)
        .filter(ExtractionRun.request_id == request_id)
        .order_by(ExtractionRun.created_at.desc())
        .first()
    )


def build_decision_packet(db: Session, request_id: str) -> Dict[str, Any]:
    latest_run = get_latest_extraction_run(db, request_id)
    if not latest_run:
        return {"extractionRunId": None, "evidence": []}

    evidence_rows = (
        db.query(GroundedEvidence)
        .filter(
            GroundedEvidence.request_id == request_id,
            GroundedEvidence.extraction_run_id == latest_run.extraction_run_id,
        )
        .order_by(GroundedEvidence.created_at.asc())
        .all()
    )

    evidence = [
        {
            "evidenceId": str(e.evidence_id),                 # ✅
            "factType": e.fact_type,
            "factKey": e.fact_key,
            "factValue": e.fact_value,
            "factJson": e.fact_json,
            "unknown": e.unknown,
        }
        for e in evidence_rows
    ]

    return {
        "extractionRunId": str(latest_run.extraction_run_id), # ✅
        "evidence": evidence,
    }


def build_audit_log(db: Session, request_id: str) -> Dict[str, Any]:
    extraction_runs = (
        db.query(ExtractionRun)
        .filter(ExtractionRun.request_id == request_id)
        .order_by(ExtractionRun.created_at.asc())
        .all()
    )

    decision_runs = (
        db.query(DecisionRun)
        .filter(DecisionRun.request_id == request_id)
        .order_by(DecisionRun.created_at.asc())
        .all()
    )

    review_actions = (
        db.query(ReviewAction)
        .filter(ReviewAction.request_id == request_id)
        .order_by(ReviewAction.created_at.asc())
        .all()
    )

    return {
        "extractionRuns": [
            {
                "extractionRunId": str(r.extraction_run_id),   # ✅
                "status": r.status,
                "createdAt": r.created_at,
                "startedAt": r.started_at,
                "finishedAt": r.finished_at,
                "errorMessage": r.error_message,
            }
            for r in extraction_runs
        ],
        "decisionRuns": [
            {
                "decisionRunId": str(r.decision_run_id),       # ✅
                "status": r.status,
                "createdAt": r.created_at,
                "startedAt": r.started_at,
                "finishedAt": r.finished_at,
                "errorMessage": r.error_message,
            }
            for r in decision_runs
        ],
        "reviewActions": [
            {
                "reviewActionId": str(a.review_action_id),     # ✅
                "action": a.action,
                "comment": a.comment,
                "reviewerId": a.reviewer_id,
                "createdAt": a.created_at,
            }
            for a in review_actions
        ],
    }


# =========================================================
# FRONTEND ROUTES
# =========================================================

# GET /api/cases?studentId={studentId}
# GET /api/cases
@app.get("/api/cases", response_model=List[CaseOut])
def list_cases(
    studentId: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    q = db.query(Request)
    if studentId:
        q = q.filter(Request.student_id == studentId)
    cases = q.order_by(Request.updated_at.desc()).all()
    return [case_to_out(c) for c in cases]


# GET /api/cases/{caseId}
@app.get("/api/cases/{caseId}", response_model=CaseDetailOut)
def get_case(caseId: str, db: Session = Depends(get_db)):
    req = db.query(Request).filter(Request.request_id == caseId).first()
    if not req:
        raise HTTPException(status_code=404, detail="Case not found")

    docs = (
        db.query(Document)
        .filter(Document.request_id == caseId)
        .order_by(Document.created_at.asc())
        .all()
    )

    return CaseDetailOut(
        case=case_to_out(req),
        documents=[doc_to_out(d) for d in docs],
        decisionPacket=build_decision_packet(db, caseId),
        auditLog=build_audit_log(db, caseId),
    )


# POST /api/cases
@app.post("/api/cases", response_model=CaseOut)
def create_case(
    studentId: str = Form(...),
    studentName: Optional[str] = Form(None),
    courseRequested: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    req = Request(
        student_id=studentId,
        student_name=studentName,
        course_requested=courseRequested,
        status="uploaded",
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    for f in files:
        meta = save_upload(f)
        db.add(
            Document(
                request_id=req.request_id,
                filename=meta["filename"],
                content_type=meta["content_type"],
                sha256=meta["sha256"],
                storage_uri=meta["storage_uri"],
                size_bytes=meta["size_bytes"],
                is_active=True,
                created_at=now_utc(),
            )
        )

    db.add(
        ExtractionRun(
            request_id=req.request_id,
            status="queued",
            created_at=now_utc(),
        )
    )

    db.commit()
    return case_to_out(req)


# POST /api/cases/{caseId}/documents
@app.post("/api/cases/{caseId}/documents", response_model=CaseOut)
def add_documents(
    caseId: str,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    req = db.query(Request).filter(Request.request_id == caseId).first()
    if not req:
        raise HTTPException(status_code=404, detail="Case not found")

    req.status = "extracting"
    req.updated_at = now_utc()

    for f in files:
        meta = save_upload(f)
        db.add(
            Document(
                request_id=caseId,
                filename=meta["filename"],
                content_type=meta["content_type"],
                sha256=meta["sha256"],
                storage_uri=meta["storage_uri"],
                size_bytes=meta["size_bytes"],
                is_active=True,
                created_at=now_utc(),
            )
        )

    db.add(
        ExtractionRun(
            request_id=caseId,
            status="queued",
            created_at=now_utc(),
        )
    )

    db.commit()
    db.refresh(req)
    return case_to_out(req)


# POST /api/cases/{caseId}/review
@app.post("/api/cases/{caseId}/review", response_model=CaseOut)
def submit_review(
    caseId: str,
    body: ReviewIn,
    db: Session = Depends(get_db),
):
    req = db.query(Request).filter(Request.request_id == caseId).first()
    if not req:
        raise HTTPException(status_code=404, detail="Case not found")

    # Normalize frontend action -> DB action (matches CHECK constraint)
    action_map = {
        "APPROVE": "approve",
        "DENY": "deny",
        "REQUEST_INFO": "request_info",
    }

    action_db = action_map.get(body.action)
    if not action_db:
        raise HTTPException(status_code=400, detail=f"Invalid action: {body.action}")

    db.add(
        ReviewAction(
            request_id=caseId,
            reviewer_id=body.reviewerId,
            action=action_db,
            comment=body.comment,
            created_at=now_utc(),
        )
    )

    # Update request status
    if body.action == "REQUEST_INFO":
        req.status = "needs_info"
    else:
        req.status = "reviewed"

    req.updated_at = now_utc()

    db.commit()
    db.refresh(req)
    return case_to_out(req)
