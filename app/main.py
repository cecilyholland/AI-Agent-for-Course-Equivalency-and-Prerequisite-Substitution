# main.py

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException, Query, HTTPException, Depends
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from models import Request, ExtractionRun, GroundedEvidence
from schemas import ExtractionCompleteIn


from models import (
    Base,
    Request,
    Document,
    ExtractionRun,
    DecisionRun,
    ReviewAction,
    GroundedEvidence,
)
from schemas import CaseOut, DocumentOut, CaseDetailOut, ReviewIn, ExtractionCompleteIn, ExtractionStartOut, ExtractionStartDocOut

# Database setup
DATABASE_URL = os.environ["DATABASE_URL"]  # raises KeyError if missing
print("DATABASE_URL =", DATABASE_URL)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

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

# mapping DB to Frontend)
DB_TO_FE_STATUS = {
    "uploaded": "UPLOADED",
    "extracting": "EXTRACTING",
    "needs_info": "NEEDS_INFO",
    "ready_for_decision": "READY_FOR_DECISION",
    "ai_recommendation": "AI_RECOMMMENDATION",
    "review_pending": "REVIEW_PENDING",
    "reviewed": "REVIEWED",
}



def to_frontend_status(db_status: str) -> str:
    return DB_TO_FE_STATUS.get(db_status, db_status)


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
        caseId=str(r.request_id),         
        studentId=r.student_id,
        studentName=r.student_name,
        courseRequested=r.course_requested,
        status=to_frontend_status(r.status),
        createdAt=r.created_at,
        updatedAt=r.updated_at,
    )


def doc_to_out(d: Document) -> DocumentOut:
    return DocumentOut(
        docId=str(d.doc_id),              
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
            "evidenceId": str(e.evidence_id),                
            "factType": e.fact_type,
            "factKey": e.fact_key,
            "factValue": e.fact_value,
            "factJson": e.fact_json,
            "unknown": e.unknown,
        }
        for e in evidence_rows
    ]

    return {
        "extractionRunId": str(latest_run.extraction_run_id), 
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
                "extractionRunId": str(r.extraction_run_id),   
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
                "decisionRunId": str(r.decision_run_id),       
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
                "reviewActionId": str(a.review_action_id),     
                "action": a.action,
                "comment": a.comment,
                "reviewerId": a.reviewer_id,
                "createdAt": a.created_at,
            }
            for a in review_actions
        ],
    }


# FRONTEND ROUTES

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

@app.post("/api/cases/{caseId}/extraction/start", response_model=ExtractionStartOut)
def start_extraction(caseId: str, db: Session = Depends(get_db)):
    req = db.query(Request).filter(Request.request_id == caseId).first()
    if not req:
        raise HTTPException(status_code=404, detail="Case not found")

    # Claim the most recent queued run for this case
    run = (
        db.query(ExtractionRun)
        .filter(ExtractionRun.request_id == caseId, ExtractionRun.status == "queued")
        .order_by(ExtractionRun.created_at.desc())
        .first()
    )
    if not run:
        raise HTTPException(status_code=409, detail="No queued extraction run for this case")

    # Fetch active documents to send to extraction service
    docs = (
        db.query(Document)
        .filter(Document.request_id == caseId, Document.is_active == True)
        .order_by(Document.created_at.asc())
        .all()
    )
    if not docs:
        raise HTTPException(status_code=409, detail="No active documents to extract")

    run.status = "running"
    run.started_at = now_utc()

    req.status = "extracting"
    req.updated_at = now_utc()

    db.commit()

    return ExtractionStartOut(
        extractionRunId=str(run.extraction_run_id),
        caseId=caseId,
        status="running",
        documents=[
            ExtractionStartDocOut(
                docId=str(d.doc_id),
                filename=d.filename,
                sha256=d.sha256,
                storageUri=d.storage_uri,
            )
            for d in docs
        ],
    )


@app.post("/api/cases/{caseId}/extraction/complete")
def complete_extraction(caseId: str, body: ExtractionCompleteIn, db: Session = Depends(get_db)):
    # validating case exists
    req = db.query(Request).filter(Request.request_id == caseId).first()
    if not req:
        raise HTTPException(status_code=404, detail="Case not found")

    # validating extraction run exists and belongs to this case
    run = (
        db.query(ExtractionRun)
        .filter(
            ExtractionRun.extraction_run_id == body.extractionRunId,
            ExtractionRun.request_id == caseId,
        )
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Extraction run not found")

    # validating state transition
    if run.status not in ("running", "queued"):
        raise HTTPException(status_code=409, detail=f"Run is not active (status={run.status})")

    run.status = "completed"

    # If someone called /complete without /start, still set started_at for audit consistency
    if run.started_at is None:
        run.started_at = now_utc()

    run.finished_at = now_utc()

    # insert the structured evidence
    for fact in body.facts:
        db.add(
            GroundedEvidence(
                request_id=caseId,
                extraction_run_id=run.extraction_run_id,  
                fact_type=fact.factType,
                fact_key=fact.factKey,
                fact_value=fact.factValue,
                fact_json=fact.factJson,
                unknown=fact.unknown,
                created_at=now_utc(),
            )
        )

    # moving forward in workflow
    req.status = "ready_for_decision"
    req.updated_at = now_utc()

    db.commit()

    return {
        "message": "Extraction completed",
        "extractionRunId": str(run.extraction_run_id),
        "factsInserted": len(body.facts),
    }