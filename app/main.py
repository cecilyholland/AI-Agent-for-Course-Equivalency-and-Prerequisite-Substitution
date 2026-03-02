from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import json

from fastapi import (
    FastAPI,
    Depends,
    UploadFile,
    File,
    Form,
    HTTPException,
    Query,
)
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.workflow_logger import log_event


from app.models import (
    Base,
    Request,
    Document,
    ExtractionRun,
    DecisionRun,
    ReviewAction,
    DecisionResult,
    GroundedEvidence,
    Reviewer,
)
from app.schemas import (
    CaseOut,
    DocumentOut,
    CaseDetailOut,
    ReviewIn,
    ExtractionCompleteIn,
    ExtractionStartOut,
    ExtractionStartDocOut,
    DecisionResultIn,
    ReviewerCreateIn,
    ReviewerOut,
)
import httpx
from decision_engine.contracts import (
    DecisionInputsPacket,
    CourseEvidence,
    TargetCourseProfile,
    PolicyConfig,
    EvidenceField,
    decide,
)


# Database setup
DATABASE_URL = os.environ["DATABASE_URL"]  
print("DATABASE_URL =", DATABASE_URL)

# needs this for auto-integration
DECISION_ENGINE_URL = os.getenv("DECISION_ENGINE_URL")  
DECISION_ENGINE_TIMEOUT_SECS = float(os.getenv("DECISION_ENGINE_TIMEOUT_SECS", "30"))
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
    "ai_recommendation": "AI_RECOMMENDATION",
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
        assignedReviewerId=str(r.assigned_reviewer_id) if r.assigned_reviewer_id else None,        courseRequested=r.course_requested,
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

    assigned = db.query(Reviewer).order_by(text("RANDOM()")).first()
    if assigned:
        req.assigned_reviewer_id = assigned.reviewer_id
        req.updated_at = now_utc()

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


@app.get("/api/cases/{caseId}", response_model=CaseDetailOut)
def get_case(caseId: str, db: Session = Depends(get_db)):
    try:
        case_uuid = uuid.UUID(caseId)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid caseId (must be a UUID)")

    req = db.query(Request).filter(Request.request_id == case_uuid).first()
    if not req:
        raise HTTPException(status_code=404, detail="Case not found")

    docs = (
        db.query(Document)
        .filter(Document.request_id == case_uuid)
        .order_by(Document.created_at.asc())
        .all()
    )

    evidence_packet = build_decision_packet(db, case_uuid)

    latest_decision_run = (
        db.query(DecisionRun)
        .filter(DecisionRun.request_id == case_uuid)
        .order_by(DecisionRun.created_at.desc())
        .first()
    )

    decision_result_obj = None
    if latest_decision_run:
        res = (
            db.query(DecisionResult)
            .filter(DecisionResult.decision_run_id == latest_decision_run.decision_run_id)
            .first()
        )
        if res:
            decision_result_obj = {
                "decisionRunId": str(latest_decision_run.decision_run_id),
                "createdAt": res.created_at,
                "needsMoreInfo": bool(res.needs_more_info),
                "missingFields": res.missing_fields,
                "resultJson": res.result_json,
            }

    return CaseDetailOut(
        case=case_to_out(req),
        documents=[doc_to_out(d) for d in docs],
        evidencePacket=evidence_packet,
        decisionResult=decision_result_obj,
        auditLog=build_audit_log(db, case_uuid),
    )


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

    log_event(
    request_id=str(req.request_id),
    status=req.status,
    actor="student",
    event="StudentAttempt",
    extra={
        "student_id": req.student_id,
        "student_name": req.student_name,
        "course_requested": req.course_requested,
        "doc_count": len(files),
        "filenames": [f.filename for f in files],
    },
    )

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

    log_event(
    request_id=str(req.request_id),
    status=req.status,
    actor="system",
    event="ExtractionQueued",
    extra={"queue_reason": "new_case"},
    )

    db.commit()
    return case_to_out(req)


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

    log_event(
    request_id=str(req.request_id),
    status=req.status,
    actor="system",
    event="StatusChange",
    extra={"to": "extracting", "reason": "documents_added"},
    )

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

    log_event(
    request_id=str(req.request_id),
    status=req.status,
    actor="student",
    event="DocumentsAdded",
    extra={"doc_count": len(files), "filenames": [f.filename for f in files]},
    )
    
    db.add(
        ExtractionRun(
            request_id=caseId,
            status="queued",
            created_at=now_utc(),
        )
    )

    log_event(
    request_id=str(req.request_id),
    status=req.status,
    actor="system",
    event="ExtractionQueued",
    extra={"queue_reason": "documents_added"},
    )

    db.commit()
    db.refresh(req)
    return case_to_out(req)


# links review to latest decision_run_id (if present)
@app.post("/api/cases/{caseId}/review", response_model=CaseOut)
def submit_review(
    caseId: str,
    body: ReviewIn,
    db: Session = Depends(get_db),
):
    # Parse UUID to match UUID(as_uuid=True) columns
    try:
        case_uuid = uuid.UUID(caseId)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid caseId (must be a UUID)")

    req = db.query(Request).filter(Request.request_id == case_uuid).first()
    if not req:
        raise HTTPException(status_code=404, detail="Case not found")

    reviewer = db.query(Reviewer).filter(Reviewer.reviewer_id == body.reviewerId).first()
    if not reviewer:
        raise HTTPException(status_code=404, detail="Reviewer not found")

    if req.assigned_reviewer_id and req.assigned_reviewer_id != body.reviewerId:
        raise HTTPException(status_code=403, detail="Reviewer not assigned to this case")

    action_map = {
        "APPROVE": "approve",
        "DENY": "deny",
        "REQUEST_INFO": "request_info",
        "NEEDS_MORE_INFO": "request_info",  # alias for frontend wording
    }

    action_db = action_map.get(body.action)
    if not action_db:
        raise HTTPException(status_code=400, detail=f"Invalid action: {body.action}")

    latest_decision_run = (
        db.query(DecisionRun)
        .filter(DecisionRun.request_id == case_uuid)
        .order_by(DecisionRun.created_at.desc())
        .first()
    )

    db.add(
        ReviewAction(
            request_id=case_uuid,
            reviewer_id=body.reviewerId,
            action=action_db,
            comment=body.comment,
            created_at=now_utc(),
            decision_run_id=latest_decision_run.decision_run_id if latest_decision_run else None,
        )
    )

    log_event(
    request_id=str(req.request_id),
    status=req.status,
    actor="reviewer",
    event="ReviewerActionSubmitted",
    extra={
        "reviewer_id": body.reviewerId,
        "action": body.action,
        "action_db": action_db,
        "comment_preview": (body.comment[:160] + "…") if len(body.comment) > 160 else body.comment,
    },
    )

    if body.action in ("REQUEST_INFO", "NEEDS_MORE_INFO"):
        req.status = "needs_info"
    else:
        req.status = "reviewed"

    req.updated_at = now_utc()

    log_event(
    request_id=str(req.request_id),
    status=req.status,
    actor="system",
    event="StatusChange",
    extra={"to": req.status, "set_by": "review"},
    )

    db.commit()
    db.refresh(req)
    return case_to_out(req)


@app.post("/api/cases/{caseId}/extraction/start", response_model=ExtractionStartOut)
def start_extraction(caseId: str, db: Session = Depends(get_db)):
    req = db.query(Request).filter(Request.request_id == caseId).first()
    if not req:
        raise HTTPException(status_code=404, detail="Case not found")

    run = (
        db.query(ExtractionRun)
        .filter(ExtractionRun.request_id == caseId, ExtractionRun.status == "queued")
        .order_by(ExtractionRun.created_at.desc())
        .first()
    )
    if not run:
        raise HTTPException(status_code=409, detail="No queued extraction run for this case")

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
    try:
        case_uuid = uuid.UUID(caseId)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid caseId (must be a UUID)")

    req = (
        db.query(Request)
        .filter(Request.request_id == case_uuid)
        .with_for_update()
        .first()
    )
    if not req:
        raise HTTPException(status_code=404, detail="Case not found")

    # validating extraction run exists and belongs to this case
    run = (
        db.query(ExtractionRun)
        .filter(
            ExtractionRun.extraction_run_id == body.extractionRunId,
            ExtractionRun.request_id == case_uuid,
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
    inserted_evidence: list[GroundedEvidence] = []
    for fact in body.facts:
        ev = GroundedEvidence(
            request_id=case_uuid,
            extraction_run_id=run.extraction_run_id,
            fact_type=fact.factType,
            fact_key=fact.factKey,
            fact_value=fact.factValue,
            fact_json=fact.factJson,
            unknown=fact.unknown,
            created_at=now_utc(),
        )
        db.add(ev)
        inserted_evidence.append(ev)

    db.flush()

    # moving forward in workflow
    req.status = "ready_for_decision"
    req.updated_at = now_utc()

    evidence_rows = inserted_evidence

    # create a decision_run record first
    decision_run = DecisionRun(
        request_id=req.request_id,
        status="running",
        started_at=now_utc(),
        finished_at=None,
        error_message=None,
        decision_inputs=None,
    )
    db.add(decision_run)
    db.flush()  # ensures decision_run_id exists before we write decision_results

    try:
        packet = build_contracts_packet(req, evidence_rows)
        packet_hash = compute_packet_hash(packet)

        # prevent duplicate completed decision runs for identical packet inputs
        existing_completed = (
            db.query(DecisionRun)
            .filter(
                DecisionRun.request_id == req.request_id,
                DecisionRun.status == "completed",
            )
            .order_by(DecisionRun.created_at.desc())
            .first()
        )

        if existing_completed and isinstance(existing_completed.decision_inputs, dict):
            prev_hash = existing_completed.decision_inputs.get("inputs_hash")
            prev_extraction_run_id = existing_completed.decision_inputs.get("extraction_run_id")
            if prev_hash == packet_hash and prev_extraction_run_id == str(run.extraction_run_id):
                decision_run.status = "completed"
                decision_run.finished_at = now_utc()
                db.commit()
                return {
                    "message": "Extraction completed (decision already up-to-date)",
                    "extractionRunId": str(run.extraction_run_id),
                    "factsInserted": len(body.facts),
                    "decisionRunId": str(existing_completed.decision_run_id),
                    "caseStatus": req.status,
                }

        # store the exact packet used (JSONB) for audit/repro
        decision_run.decision_inputs = packet.model_dump()
        decision_run.decision_inputs["inputs_hash"] = packet_hash
        decision_run.decision_inputs["extraction_run_id"] = str(run.extraction_run_id)

        missing = validate_packet_or_raise(packet)
        if missing:
            synthetic_result_json = {
                "decision": "NEEDS_MORE_INFO",
                "equivalency_score": 0,
                "confidence": "LOW",
                "gaps": [{"text": m} for m in missing],
                "missing_info_requests": missing,
            }

            db.add(
                DecisionResult(
                    decision_run_id=decision_run.decision_run_id,
                    result_json=synthetic_result_json,
                    needs_more_info=True,
                    missing_fields={"missing_info_requests": missing},
                )
            )

            decision_run.status = "completed"
            decision_run.finished_at = now_utc()

            # advance workflow status (mirrors /decision/result behavior)
            req.status = "needs_info"
            req.updated_at = now_utc()

        else:
            # run engine locally (Mode A)
            engine_result = decide(packet)

            # persist decision result (1:1 with decision_runs)
            needs_more_info = (engine_result.decision.value == "NEEDS_MORE_INFO")
            missing_fields = (
                {"missing_info_requests": engine_result.missing_info_requests}
                if engine_result.missing_info_requests
                else None
            )

            db.add(
                DecisionResult(
                    decision_run_id=decision_run.decision_run_id,
                    result_json=engine_result.model_dump(),
                    needs_more_info=needs_more_info,
                    missing_fields=missing_fields,
                )
            )

            decision_run.status = "completed"
            decision_run.finished_at = now_utc()

            # advance workflow status (mirrors /decision/result behavior)
            req.status = "needs_info" if needs_more_info else "ai_recommendation"
            req.updated_at = now_utc()

    except Exception as ex:
        decision_run.status = "failed"
        decision_run.error_message = str(ex)
        decision_run.finished_at = now_utc()

        # safest workflow signal: needs_info (advisor can review + re-run later)
        req.status = "needs_info"
        req.updated_at = now_utc()

    db.commit()

    return {
        "message": "Extraction completed (decision engine triggered)",
        "extractionRunId": str(run.extraction_run_id),
        "factsInserted": len(body.facts),
        "decisionRunId": str(decision_run.decision_run_id),
        "caseStatus": req.status,
    }

def build_decision_inputs(case: Request, docs: list[Document], evidence: list[GroundedEvidence]) -> dict:
    return {
        "case": {
            "caseId": str(case.request_id),
            "studentId": case.student_id,
            "studentName": case.student_name,
            "courseRequested": case.course_requested,
            "status": case.status,
            "createdAt": case.created_at.isoformat() if case.created_at else None,
            "updatedAt": case.updated_at.isoformat() if case.updated_at else None,
        },
        "documents": [
            {
                "docId": str(d.doc_id),
                "filename": d.filename,
                "contentType": d.content_type,
                "sha256": d.sha256,
                "storageUri": d.storage_uri,
                "sizeBytes": d.size_bytes,
                "createdAt": d.created_at.isoformat() if d.created_at else None,
                "isActive": d.is_active,
            }
            for d in docs
        ],
        "facts": [
            {
                "evidenceId": str(e.evidence_id),
                "extractionRunId": str(e.extraction_run_id),
                "factType": e.fact_type,
                "factKey": e.fact_key,
                "factValue": e.fact_value,
                "factJson": e.fact_json,
                "unknown": e.unknown,
                "createdAt": e.created_at.isoformat() if e.created_at else None,
            }
            for e in evidence
        ],
    }


# for Decision Engine (inputs-only)
@app.post("/api/cases/{caseId}/decision/run")
def decision_run(caseId: str, db: Session = Depends(get_db)):
    # Parse UUID (important because your PKs are UUID(as_uuid=True))
    try:
        case_uuid = uuid.UUID(caseId)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid caseId (must be a UUID)")

    # Load case
    case = db.query(Request).filter(Request.request_id == case_uuid).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # this is a guard. only allow once extraction is done
    if case.status != "ready_for_decision":
        raise HTTPException(
            status_code=409,
            detail=f"Case is not ready_for_decision (status={case.status})",
        )

    # prevent duplicate completed decision runs
    existing_run = (
        db.query(DecisionRun)
        .filter(
            DecisionRun.request_id == case_uuid,
            DecisionRun.status == "completed",
        )
        .first()
    )
    if existing_run:
        raise HTTPException(status_code=409, detail="Decision inputs already built for this case")

    docs = (
        db.query(Document)
        .filter(Document.request_id == case_uuid, Document.is_active == True)
        .order_by(Document.created_at.asc())
        .all()
    )
    if not docs:
        raise HTTPException(status_code=409, detail="No active documents for this case")

    evidence = (
        db.query(GroundedEvidence)
        .filter(GroundedEvidence.request_id == case_uuid)
        .order_by(GroundedEvidence.created_at.asc())
        .all()
    )
    if not evidence:
        raise HTTPException(status_code=409, detail="No grounded evidence for this case")

    decision_inputs = build_decision_inputs(case, docs, evidence)

    run = DecisionRun(
        request_id=case_uuid,
        status="completed",
        started_at=now_utc(),
        finished_at=now_utc(),
        error_message=None,
        decision_inputs=decision_inputs,
    )
    db.add(run)

    db.commit()
    db.refresh(run)

    return {
        "message": "Decision inputs built and stored",
        "caseId": str(case_uuid),
        "decisionRunId": str(run.decision_run_id),
        "status": run.status,
    }


@app.get("/api/cases/{caseId}/decision/result/latest")
def get_latest_decision_result(caseId: str, db: Session = Depends(get_db)):
    try:
        case_uuid = uuid.UUID(caseId)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid caseId (must be a UUID)")

    req = db.query(Request).filter(Request.request_id == case_uuid).first()
    if not req:
        raise HTTPException(status_code=404, detail="Case not found")

    dr = (
        db.query(DecisionRun)
        .filter(DecisionRun.request_id == case_uuid)
        .order_by(DecisionRun.created_at.desc())
        .first()
    )
    if not dr:
        raise HTTPException(status_code=404, detail="No decision run found")

    res = (
        db.query(DecisionResult)
        .filter(DecisionResult.decision_run_id == dr.decision_run_id)
        .first()
    )
    if not res:
        raise HTTPException(status_code=404, detail="No decision result found for latest decision run")

    result_json = res.result_json or {}
    ai_decision = result_json.get("decision")

    display = ai_decision
    bridge_plan = result_json.get("bridge_plan")
    gaps = result_json.get("gaps") or []
    has_fixable_gap = any(isinstance(g, dict) and g.get("severity") == "FIXABLE" for g in gaps)

    if ai_decision == "APPROVE" and (bridge_plan or has_fixable_gap):
        display = "APPROVE_WITH_BRIDGE"

    latest_review = (
        db.query(ReviewAction)
        .filter(ReviewAction.request_id == case_uuid)
        .order_by(ReviewAction.created_at.desc())
        .first()
    )

    # DB stores: approve / deny / request_info
    review_action_api = None
    if latest_review:
        reverse_action_map = {
            "approve": "APPROVE",
            "deny": "DENY",
            "request_info": "NEEDS_MORE_INFO",  # frontend wording
        }
        review_action_api = {
            "reviewActionId": str(latest_review.review_action_id),
            "reviewerId": latest_review.reviewer_id,
            "reviewerDecision": reverse_action_map.get(latest_review.action, latest_review.action),
            "comment": latest_review.comment,
            "createdAt": latest_review.created_at,
            "decisionRunId": str(latest_review.decision_run_id) if latest_review.decision_run_id else None,
        }

    return {
        "caseId": str(case_uuid),
        "caseStatus": req.status,                 # ai_recommendation / needs_info / reviewed
        "decisionRunId": str(dr.decision_run_id),
        "decisionStatus": dr.status,              # completed/failed/running
        "aiRecommendation": ai_decision,          # raw engine decision
        "aiRecommendationDisplay": display,       # friendly display label
        "needsMoreInfo": bool(res.needs_more_info),
        "resultJson": result_json,
        "decisionInputs": dr.decision_inputs,
        "createdAt": dr.created_at,
        "latestReview": review_action_api,       
    }


@app.post("/api/cases/{caseId}/decision/result")
def store_decision_result(caseId: str, body: DecisionResultIn, db: Session = Depends(get_db)):
    try:
        case_uuid = uuid.UUID(caseId)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid caseId (must be UUID)")

    case = db.query(Request).filter(Request.request_id == case_uuid).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    try:
        run_uuid = uuid.UUID(body.decisionRunId)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid decisionRunId (must be UUID)")

    run = (
        db.query(DecisionRun)
        .filter(
            DecisionRun.decision_run_id == run_uuid,
            DecisionRun.request_id == case_uuid,
        )
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Decision run not found for this case")

    # upsert into decision_results (1:1 with decision_runs)
    existing = db.query(DecisionResult).filter(DecisionResult.decision_run_id == run_uuid).first()
    if existing:
        existing.result_json = body.resultJson
        existing.needs_more_info = body.needsMoreInfo
        existing.missing_fields = body.missingFields
        # created_at has server_default NOW(). keep original for audit history
    else:
        db.add(
            DecisionResult(
                decision_run_id=run_uuid,
                result_json=body.resultJson,
                needs_more_info=body.needsMoreInfo,
                missing_fields=body.missingFields,
            )
        )

    #update case status based on workflow signal
    # if more info needed is true then set needs_info
    # else ai_recommendation (AI produced a recommendation, now human review)
    case.status = "needs_info" if body.needsMoreInfo else "ai_recommendation"
    case.updated_at = now_utc()

    db.commit()

    return {
        "message": "Decision result stored",
        "caseId": str(case_uuid),
        "decisionRunId": str(run_uuid),
        "caseStatus": case.status,
    }


# Decision Engine 

def _first_non_empty(*vals):
    for v in vals:
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        return v
    return None


def map_evidence_rows_to_course_evidence(evidence_rows: list[GroundedEvidence]) -> CourseEvidence:
    # Defaults: unknown unless we find a value
    fields = {
        "credits": EvidenceField(value=None, unknown=True, citations=[]),
        "contact_hours_lecture": EvidenceField(value=None, unknown=True, citations=[]),
        "contact_hours_lab": EvidenceField(value=None, unknown=True, citations=[]),
        "lab_component": EvidenceField(value=None, unknown=True, citations=[]),
        "topics": EvidenceField(value=None, unknown=True, citations=[]),
        "outcomes": EvidenceField(value=None, unknown=True, citations=[]),
        "assessments": EvidenceField(value=None, unknown=True, citations=[]),
    }

    def key_of(e: GroundedEvidence) -> str:
        return (e.fact_key or e.fact_type or "").strip().lower()

    for e in evidence_rows:
        k = key_of(e)

        # prefer structured JSON if present, else fact_value
        v = _first_non_empty(e.fact_json, e.fact_value)
        # Unwrap {"items":[...]} payloads into plain lists for the decision engine
        if isinstance(v, dict) and "items" in v and isinstance(v["items"], list):
            v = v["items"]

        # credits
        if k in {"credits", "credit_hours", "units"}:
            fields["credits"] = EvidenceField(value=v, unknown=bool(e.unknown), citations=[])
            continue

        # contact hours
        if k in {"contact_hours_lecture", "lecture_hours", "lecture_contact_hours"}:
            fields["contact_hours_lecture"] = EvidenceField(value=v, unknown=bool(e.unknown), citations=[])
            continue

        if k in {"contact_hours_lab", "lab_hours", "lab_contact_hours"}:
            fields["contact_hours_lab"] = EvidenceField(value=v, unknown=bool(e.unknown), citations=[])
            continue

        # lab component (try to coerce truthy strings)
        if k in {"lab_component", "has_lab", "lab_required", "includes_lab"}:
            lab_val = v
            if isinstance(lab_val, str):
                s = lab_val.strip().lower()
                if s in {"true", "yes", "y", "1"}:
                    lab_val = True
                elif s in {"false", "no", "n", "0"}:
                    lab_val = False
            fields["lab_component"] = EvidenceField(value=lab_val, unknown=bool(e.unknown), citations=[])
            continue

        # topics / outcomes / assessments
        if k in {"topics", "course_topics"}:
            fields["topics"] = EvidenceField(value=v, unknown=bool(e.unknown), citations=[])
            continue

        if k in {"outcomes", "learning_outcomes", "slos"}:
            fields["outcomes"] = EvidenceField(value=v, unknown=bool(e.unknown), citations=[])
            continue

        if k in {"assessments", "evaluation_methods", "grading_components"}:
            fields["assessments"] = EvidenceField(value=v, unknown=bool(e.unknown), citations=[])
            continue

    return CourseEvidence(**fields)

# build decision inputs packet from db
# TO DO: hard coded the course needs to be updated 
def build_contracts_packet(case: Request, evidence_rows: list[GroundedEvidence]) -> DecisionInputsPacket:
    source = map_evidence_rows_to_course_evidence(evidence_rows)

    # Demo target profile (replace later with course profile config)
    target = TargetCourseProfile(
        target_credits=3,
        target_lab_required=False,
        required_topics=["trees", "graphs", "hashing", "heaps"],
        required_outcomes=[
            "Analyze time complexity",
            "Implement common data structures",
            "Design balanced trees",
        ],
    )

    policy = PolicyConfig()  # uses defaults from contracts.py

    return DecisionInputsPacket(
        case_id=str(case.request_id),
        source_course=source,
        target_course=target,
        policy=policy,
    )

def validate_packet_or_raise(packet: DecisionInputsPacket) -> list[str]:
    missing: list[str] = []

    src = packet.source_course

    # credits required
    if src.credits.unknown or src.credits.value in (None, "", []):
        missing.append("Missing source course credits.")

    # topics or outcomes required
    topics_missing = src.topics.unknown or not src.topics.value
    outcomes_missing = src.outcomes.unknown or not src.outcomes.value
    if topics_missing and outcomes_missing:
        missing.append("Missing source course topics and learning outcomes.")

    return missing

def stable_json_dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def compute_packet_hash(packet: DecisionInputsPacket) -> str:
    # model_dump gives a stable structure; stable_json_dumps makes ordering deterministic
    payload = packet.model_dump()
    return sha256_str(stable_json_dumps(payload))

def generate_decision_packet(engine_result) -> dict:
    decision = engine_result.decision.value

    if decision == "APPROVE":
        why = "The source course meets the credit and content requirements under the current policy."
    elif decision == "BRIDGE":
        why = "The source course is close to equivalent but requires bridging requirements."
    elif decision == "DENY":
        why = "The source course does not meet the minimum equivalency threshold under the current policy."
    elif decision == "NEEDS_MORE_INFO":
        why = "The request is missing required evidence needed to evaluate equivalency."
    else:
        why = "No recommendation available."

    return {
        "decision": decision,
        "equivalency_score": engine_result.equivalency_score,
        "confidence": engine_result.confidence.value,
        "why": why,
        "gaps": [
            g.model_dump() if hasattr(g, "model_dump") else g
            for g in (engine_result.gaps or [])
        ],
        "missing_info_requests": list(engine_result.missing_info_requests or []),
        "citations": [],  # Cecily will populate later via grounding
    }

@app.post("/api/reviewers", response_model=ReviewerOut)
def create_reviewer(body: ReviewerCreateIn, db: Session = Depends(get_db)):
    r = Reviewer(
        reviewer_name=body.reviewerName,
        created_at=now_utc(),
    )
    db.add(r)
    db.commit()
    db.refresh(r)

    return {
        "reviewerId": str(r.reviewer_id),
        "reviewerName": r.reviewer_name,
        "createdAt": r.created_at,
    }

@app.get("/api/reviewers/{reviewerId}", response_model=ReviewerOut)
def get_reviewer(reviewerId: str, db: Session = Depends(get_db)):
    try:
        reviewer_uuid = uuid.UUID(reviewerId)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid reviewerId (must be a UUID)")

    r = db.query(Reviewer).filter(Reviewer.reviewer_id == reviewer_uuid).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reviewer not found")

    return ReviewerOut(
        reviewerId=str(r.reviewer_id),
        reviewerName=getattr(r, "reviewer_name", None),
        createdAt=r.created_at,
    )