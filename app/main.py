from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import json
import yaml

from fastapi import (
    FastAPI,
    Depends,
    UploadFile,
    File,
    Form,
    HTTPException,
    BackgroundTasks,
    Query,
)
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.workflow_logger import log_event
from app.extraction.pipeline import run_extraction as run_extraction_pipeline

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
    CommitteeAssignment,
    CommitteeVote,
    Course,
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
    CommitteeVoteIn,
    CommitteeMemberOut,
    CommitteeInfoOut,
    CourseIn,
    CourseOut,
    LoginIn,
    LoginOut,
    PolicyOut,
    PolicyUpdateIn,
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
from decision_engine.llm_decision import call_llm_decision


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


# mapping DB to Frontend
DB_TO_FE_STATUS = {
    "uploaded": "UPLOADED",
    "extracting": "EXTRACTING",
    "ai_recommendation": "AI_RECOMMENDATION",
    "reviewed": "REVIEWED",
    "pending_committee": "PENDING_COMMITTEE",
    "committee_decided": "COMMITTEE_DECIDED",
    "invalid": "INVALID",
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
        assignedReviewerId=str(r.assigned_reviewer_id) if r.assigned_reviewer_id else None,
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

    committee_votes = (
        db.query(CommitteeVote)
        .filter(CommitteeVote.request_id == request_id)
        .order_by(CommitteeVote.created_at.asc())
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
                "decision": (
                    lambda res: res.result_json.get("decision") if res else None
                )(db.query(DecisionResult).filter(DecisionResult.decision_run_id == r.decision_run_id).first()),
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
        "committeeVotes": [
            {
                "action": v.action,
                "comment": v.comment,
                "createdAt": v.created_at,
            }
            for v in committee_votes
        ],
    }

def run_decision_for_case_and_run(
    db: Session,
    case_uuid: uuid.UUID,
    extraction_run_id: uuid.UUID,
) -> uuid.UUID:
    """
    Creates a decision_run + decision_result for a case, using evidence produced
    by the given extraction_run_id. Updates requests.status accordingly.

    Returns: decision_run_id
    """
    case = db.query(Request).filter(Request.request_id == case_uuid).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found (post-extraction)")

    if case.status != "ready_for_decision":
        raise HTTPException(
            status_code=409,
            detail=f"Case not ready_for_decision after extraction (status={case.status})",
        )

    evidence_rows = (
        db.query(GroundedEvidence)
        .filter(
            GroundedEvidence.request_id == case_uuid,
            GroundedEvidence.extraction_run_id == extraction_run_id,
        )
        .order_by(GroundedEvidence.created_at.asc())
        .all()
    )
    if not evidence_rows:
        raise HTTPException(status_code=409, detail="No grounded evidence found for extraction_run_id")

    decision_run = DecisionRun(
        request_id=case_uuid,
        status="running",
        started_at=now_utc(),
        finished_at=None,
        error_message=None,
        decision_inputs=None,
    )
    db.add(decision_run)
    db.flush()

    try:
        packet = build_contracts_packet(case, evidence_rows)
        packet_hash = compute_packet_hash(packet)

        existing_completed = (
            db.query(DecisionRun)
            .filter(
                DecisionRun.request_id == case_uuid,
                DecisionRun.status == "completed",
            )
            .order_by(DecisionRun.created_at.desc())
            .first()
        )
        if existing_completed and isinstance(existing_completed.decision_inputs, dict):
            prev_hash = existing_completed.decision_inputs.get("inputs_hash")
            prev_extraction = existing_completed.decision_inputs.get("extraction_run_id")
            if prev_hash == packet_hash and prev_extraction == str(extraction_run_id):
                decision_run.status = "completed"
                decision_run.finished_at = now_utc()
                return existing_completed.decision_run_id

        decision_run.decision_inputs = packet.model_dump()
        decision_run.decision_inputs["inputs_hash"] = packet_hash
        decision_run.decision_inputs["extraction_run_id"] = str(extraction_run_id)

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

            case.status = "ai_recommendation"
            case.updated_at = now_utc()

            log_event(
                event="AgentSuggestion",
                request_id=str(case.request_id),
                actor="agent",
                status="ai_recommendation",
                step="decision",
                extra={
                    "suggestion_flag": "needs_more_info",
                    "decision_run_id": str(decision_run.decision_run_id),
                    "extraction_run_id": str(extraction_run_id),
                    "missing_info_requests": missing,
                    "inputs_hash": packet_hash,
                },
            )

            return decision_run.decision_run_id

        # --- OLD deterministic decision engine (commented out) ---
        # engine_result = decide(packet)
        # --- END OLD ---

        # --- NEW: LLM-based decision via OpenAI GPT ---
        chunks_by_evidence = fetch_chunks_by_evidence(db, evidence_rows)
        engine_result = call_llm_decision(packet, evidence_rows, chunks_by_evidence)
        # --- END NEW ---

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

        case.status = "ai_recommendation"
        case.updated_at = now_utc()

        result_dict = engine_result.model_dump()
        suggestion_flag = (result_dict.get("decision") or "").lower()

        log_event(
            event="AgentSuggestion",
            request_id=str(case.request_id),
            actor="agent",
            status="ai_recommendation",
            step="decision",
            extra={
                "suggestion_flag": suggestion_flag,
                "decision_run_id": str(decision_run.decision_run_id),
                "extraction_run_id": str(extraction_run_id),
                "inputs_hash": packet_hash,
            },
        )

        return decision_run.decision_run_id

    except Exception as ex:
        decision_run.status = "failed"
        decision_run.error_message = str(ex)
        decision_run.finished_at = now_utc()

        case.status = "invalid"
        case.updated_at = now_utc()

        log_event(
            event="AgentRunFailed",
            request_id=str(case.request_id),
            actor="agent",
            status="invalid",
            step="decision",
            extra={
                "decision_run_id": str(decision_run.decision_run_id),
                "extraction_run_id": str(extraction_run_id),
                "error": str(ex),
            },
        )

        return decision_run.decision_run_id
    
def run_extraction_and_decision(caseId: str):
    db = SessionLocal()
    try:
        try:
            extraction_run_id_str = run_extraction_pipeline(caseId)
        except Exception as e:
            print(f"[background] Extraction failed for case {caseId}: {e}")
            return

        print(f"[background] Extraction done for case {caseId}, run_id={extraction_run_id_str}")

        db.expire_all()
        case_uuid = uuid.UUID(caseId)
        req = db.query(Request).filter(Request.request_id == case_uuid).first()
        if req and req.status == "ready_for_decision":
            extraction_run_uuid = uuid.UUID(extraction_run_id_str)
            print(f"[background] Running LLM decision for case {caseId}...")
            run_decision_for_case_and_run(db, case_uuid, extraction_run_uuid)
            db.commit()
            print(f"[background] Decision complete for case {caseId}, status={req.status}")
        else:
            print(f"[background] Skipping decision for case {caseId}: status={req.status if req else 'NOT FOUND'}")
    except Exception as e:
        print(f"[background] ERROR in run_extraction_and_decision for case {caseId}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

# FRONTEND ROUTES
@app.post("/api/cases", response_model=CaseOut)
def create_case(
    studentId: str = Form(...),
    studentName: Optional[str] = Form(None),
    courseRequested: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    background_tasks: BackgroundTasks = None,
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
        db.add(req)
        db.commit()
        db.refresh(req)


    try:
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
                "assigned_reviewer_id": str(req.assigned_reviewer_id) if req.assigned_reviewer_id else None,
            },
        )
    except Exception:
        pass

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

    try:
        log_event(
            request_id=str(req.request_id),
            status=req.status,
            actor="system",
            event="ExtractionQueued",
            extra={"queue_reason": "new_case"},
        )
    except Exception:
        pass

    db.commit()
    db.refresh(req)
    background_tasks.add_task(run_extraction_and_decision, str(req.request_id))
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

    log_event(
        event="ReviewerAccessedCase",
        request_id=str(req.request_id),
        actor="reviewer",
        status=req.status,
        step="review",
        extra={
            "access_type": "view_case",
            "assigned_reviewer_id": str(req.assigned_reviewer_id) if req.assigned_reviewer_id else None,
            "student_id": req.student_id,
            "course_requested": req.course_requested,
        },
    )

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


@app.post("/api/cases/{caseId}/documents", response_model=CaseOut)
def add_documents(
    caseId: str,
    files: List[UploadFile] = File(...),
    background_tasks: BackgroundTasks = None,
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

    log_event(
        request_id=str(req.request_id),
        status=req.status,
        actor="system",
        event="ExtractionQueued",
        extra={"queue_reason": "documents_added"},
    )

    db.commit()
    db.refresh(req)
    background_tasks.add_task(run_extraction_and_decision, str(req.request_id))
    return case_to_out(req)

# links review to latest decision_run_id (if present)
@app.post("/api/cases/{caseId}/review", response_model=CaseOut)
def submit_review(
    caseId: str,
    body: ReviewIn,
    db: Session = Depends(get_db),
):
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
        "NEEDS_MORE_INFO": "request_info",
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

    # After reviewer approves or denies, assign committee and move to pending_committee
    if action_db in ("approve", "deny"):
        # Pick 3 random reviewers who are NOT the assigned reviewer
        eligible = (
            db.query(Reviewer)
            .filter(Reviewer.reviewer_id != req.assigned_reviewer_id)
            .order_by(text("RANDOM()"))
            .limit(3)
            .all()
        )

        for member in eligible:
            db.add(CommitteeAssignment(
                request_id=case_uuid,
                reviewer_id=member.reviewer_id,
            ))

        req.status = "pending_committee"
        req.updated_at = now_utc()

        log_event(
            request_id=str(req.request_id),
            status=req.status,
            actor="system",
            event="StatusChange",
            extra={
                "to": "pending_committee",
                "set_by": "review",
                "committee_size": len(eligible),
                "committee_members": [str(m.reviewer_id) for m in eligible],
            },
        )
    else:
        # request_info → keep at reviewed or needs_info
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


@app.get("/api/cases/{caseId}/committee", response_model=CommitteeInfoOut)
def get_committee(
    caseId: str,
    reviewerId: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        case_uuid = uuid.UUID(caseId)
        reviewer_uuid = uuid.UUID(reviewerId)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UUID")

    req = db.query(Request).filter(Request.request_id == case_uuid).first()
    if not req:
        raise HTTPException(status_code=404, detail="Case not found")

    # Check if this reviewer is a committee member for this case
    membership = (
        db.query(CommitteeAssignment)
        .filter(
            CommitteeAssignment.request_id == case_uuid,
            CommitteeAssignment.reviewer_id == reviewer_uuid,
        )
        .first()
    )
    if not membership:
        raise HTTPException(status_code=403, detail="Reviewer is not a committee member for this case")

    # Get all committee members
    assignments = (
        db.query(CommitteeAssignment)
        .filter(CommitteeAssignment.request_id == case_uuid)
        .all()
    )

    # Get all votes for this case
    votes = (
        db.query(CommitteeVote)
        .filter(CommitteeVote.request_id == case_uuid)
        .all()
    )
    voted_ids = {v.voter_id for v in votes}

    # Build member list (no vote details — blind voting)
    members = []
    for a in assignments:
        reviewer = db.query(Reviewer).filter(Reviewer.reviewer_id == a.reviewer_id).first()
        members.append(CommitteeMemberOut(
            reviewerId=str(a.reviewer_id),
            reviewerName=reviewer.reviewer_name if reviewer else None,
            hasVoted=(a.reviewer_id in voted_ids),
        ))

    # Only show requesting reviewer's own vote
    my_vote = None
    for v in votes:
        if v.voter_id == reviewer_uuid:
            my_vote = {
                "action": v.action,
                "comment": v.comment,
                "createdAt": v.created_at.isoformat() if v.created_at else None,
            }
            break

    # Final decision (if all voted)
    final_decision = None
    if req.status == "committee_decided":
        approve_count = sum(1 for v in votes if v.action == "approve")
        deny_count = sum(1 for v in votes if v.action == "deny")
        final_decision = "approve" if approve_count > deny_count else "deny"

    return CommitteeInfoOut(
        members=members,
        myVote=my_vote,
        finalDecision=final_decision,
    )


@app.post("/api/cases/{caseId}/committee/vote", response_model=CaseOut)
def submit_committee_vote(
    caseId: str,
    body: CommitteeVoteIn,
    db: Session = Depends(get_db),
):
    try:
        case_uuid = uuid.UUID(caseId)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid caseId")

    req = db.query(Request).filter(Request.request_id == case_uuid).first()
    if not req:
        raise HTTPException(status_code=404, detail="Case not found")

    if req.status != "pending_committee":
        raise HTTPException(status_code=409, detail=f"Case is not pending committee review (status={req.status})")

    # Verify voter is on the committee
    membership = (
        db.query(CommitteeAssignment)
        .filter(
            CommitteeAssignment.request_id == case_uuid,
            CommitteeAssignment.reviewer_id == body.reviewerId,
        )
        .first()
    )
    if not membership:
        raise HTTPException(status_code=403, detail="Reviewer is not a committee member for this case")

    # Check for duplicate vote
    existing_vote = (
        db.query(CommitteeVote)
        .filter(
            CommitteeVote.request_id == case_uuid,
            CommitteeVote.voter_id == body.reviewerId,
        )
        .first()
    )
    if existing_vote:
        raise HTTPException(status_code=409, detail="Committee member has already voted on this case")

    # Record vote
    db.add(CommitteeVote(
        request_id=case_uuid,
        voter_id=body.reviewerId,
        action=body.action,
        comment=body.comment,
        created_at=now_utc(),
    ))
    db.flush()

    # Check if all committee members have voted
    total_members = (
        db.query(CommitteeAssignment)
        .filter(CommitteeAssignment.request_id == case_uuid)
        .count()
    )
    total_votes = (
        db.query(CommitteeVote)
        .filter(CommitteeVote.request_id == case_uuid)
        .count()
    )

    if total_votes >= total_members:
        # All voted — determine majority decision
        all_votes = (
            db.query(CommitteeVote)
            .filter(CommitteeVote.request_id == case_uuid)
            .all()
        )
        approve_count = sum(1 for v in all_votes if v.action == "approve")
        deny_count = sum(1 for v in all_votes if v.action == "deny")
        final_decision = "approve" if approve_count > deny_count else "deny"

        req.status = "committee_decided"
        req.updated_at = now_utc()

        log_event(
            request_id=str(req.request_id),
            status=req.status,
            actor="system",
            event="CommitteeDecided",
            extra={
                "final_decision": final_decision,
                "approve_count": approve_count,
                "deny_count": deny_count,
                "total_members": total_members,
            },
        )

    db.commit()
    db.refresh(req)
    return case_to_out(req)


@app.get("/api/cases", response_model=list[CaseOut])
def list_cases(
    status: Optional[str] = Query(None),
    studentId: Optional[str] = Query(None),
    committeeReviewerId: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Request)

    if status:
        query = query.filter(Request.status == status)

    if studentId:
        query = query.filter(Request.student_id == studentId)

    if committeeReviewerId:
        try:
            committee_uuid = uuid.UUID(committeeReviewerId)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid committeeReviewerId")
        query = query.join(
            CommitteeAssignment,
            CommitteeAssignment.request_id == Request.request_id,
        ).filter(CommitteeAssignment.reviewer_id == committee_uuid)

    cases = query.order_by(Request.created_at.desc()).all()

    return [case_to_out(c) for c in cases]


@app.post("/api/cases/{caseId}/extraction/start")
def start_extraction(caseId: str, db: Session = Depends(get_db)):
    try:
        case_uuid = uuid.UUID(caseId)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid caseId (must be a UUID)")

    req = db.query(Request).filter(Request.request_id == case_uuid).first()
    if not req:
        raise HTTPException(status_code=404, detail="Case not found")

    docs = (
        db.query(Document)
        .filter(Document.request_id == case_uuid, Document.is_active == True)
        .order_by(Document.created_at.asc())
        .all()
    )
    if not docs:
        raise HTTPException(status_code=409, detail="No active documents to extract")

    req.status = "extracting"
    req.updated_at = now_utc()
    db.commit()

    try:
        extraction_run_id_str = run_extraction_pipeline(str(case_uuid))
    except Exception as e:
        db.expire_all()
        req = db.query(Request).filter(Request.request_id == case_uuid).first()
        return {
            "message": "Extraction failed",
            "caseId": caseId,
            "caseStatus": req.status if req else None,
            "error": str(e),
        }

    db.expire_all()
    req = db.query(Request).filter(Request.request_id == case_uuid).first()

    if not req or req.status != "ready_for_decision":
        return {
            "message": "Extraction completed but case not ready_for_decision",
            "caseId": caseId,
            "extractionRunId": extraction_run_id_str,
            "caseStatus": req.status if req else None,
        }

    extraction_run_uuid = uuid.UUID(extraction_run_id_str)
    try:
        decision_run_id = run_decision_for_case_and_run(db, case_uuid, extraction_run_uuid)
        db.commit()
        db.refresh(req)
        return {
            "message": "Extraction completed + decision auto-triggered",
            "caseId": caseId,
            "extractionRunId": str(extraction_run_uuid),
            "decisionRunId": str(decision_run_id),
            "caseStatus": req.status,
        }
    except Exception as e:
        db.rollback()
        return {
            "message": "Extraction completed but decision trigger failed",
            "caseId": caseId,
            "extractionRunId": str(extraction_run_uuid),
            "error": str(e),
            "caseStatus": req.status if req else None,
        }


@app.post("/api/cases/{caseId}/extraction/complete")
def complete_extraction(caseId: str, body: ExtractionCompleteIn, db: Session = Depends(get_db)):
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

    if run.status not in ("running", "queued"):
        raise HTTPException(status_code=409, detail=f"Run is not active (status={run.status})")

    run.status = "completed"

    if run.started_at is None:
        run.started_at = now_utc()

    run.finished_at = now_utc()

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

    req.status = "ready_for_decision"
    req.updated_at = now_utc()

    evidence_rows = inserted_evidence

    decision_run = DecisionRun(
        request_id=req.request_id,
        status="running",
        started_at=now_utc(),
        finished_at=None,
        error_message=None,
        decision_inputs=None,
    )
    db.add(decision_run)
    db.flush()

    try:
        packet = build_contracts_packet(req, evidence_rows)
        packet_hash = compute_packet_hash(packet)

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

            req.status = "ai_recommendation"
            req.updated_at = now_utc()

        else:
            # --- OLD deterministic decision engine (commented out) ---
            # engine_result = decide(packet)
            # --- END OLD ---

            # --- NEW: LLM-based decision via OpenAI GPT ---
            chunks_by_evidence = fetch_chunks_by_evidence(db, evidence_rows)
            engine_result = call_llm_decision(packet, evidence_rows, chunks_by_evidence)
            # --- END NEW ---

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

            req.status = "ai_recommendation"
            req.updated_at = now_utc()

    except Exception as ex:
        decision_run.status = "failed"
        decision_run.error_message = str(ex)
        decision_run.finished_at = now_utc()

        req.status = "invalid"
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


@app.post("/api/cases/{caseId}/decision/run")
def decision_run(caseId: str, db: Session = Depends(get_db)):
    try:
        case_uuid = uuid.UUID(caseId)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid caseId (must be a UUID)")

    case = db.query(Request).filter(Request.request_id == case_uuid).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if case.status not in ("ready_for_decision", "ai_recommendation"):
        raise HTTPException(
            status_code=409,
            detail=f"Case is not ready for decision (status={case.status})",
        )
    # Reset status so run_decision_for_case_and_run can proceed
    case.status = "ready_for_decision"
    case.updated_at = now_utc()

    # Only block if there's already a completed decision with an actual result
    existing_run = (
        db.query(DecisionRun)
        .filter(
            DecisionRun.request_id == case_uuid,
            DecisionRun.status == "completed",
        )
        .first()
    )
    if existing_run:
        has_result = db.query(DecisionResult).filter(
            DecisionResult.decision_run_id == existing_run.decision_run_id
        ).first()
        if has_result:
            raise HTTPException(status_code=409, detail="Decision already completed for this case")

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

    # Find the latest extraction run for this case
    latest_extraction = (
        db.query(ExtractionRun)
        .filter(
            ExtractionRun.request_id == case_uuid,
            ExtractionRun.status == "completed",
        )
        .order_by(ExtractionRun.created_at.desc())
        .first()
    )
    if not latest_extraction:
        raise HTTPException(status_code=409, detail="No completed extraction run for this case")

    extraction_run_id = latest_extraction.extraction_run_id

    # Use the main decision flow which calls the LLM
    decision_run_id = run_decision_for_case_and_run(db, case_uuid, extraction_run_id)
    db.commit()

    return {
        "message": "LLM decision completed",
        "caseId": str(case_uuid),
        "decisionRunId": str(decision_run_id),
        "status": case.status,
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

    review_action_api = None
    if latest_review:
        reverse_action_map = {
            "approve": "APPROVE",
            "deny": "DENY",
            "request_info": "NEEDS_MORE_INFO",
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
        "caseStatus": req.status,
        "decisionRunId": str(dr.decision_run_id),
        "decisionStatus": dr.status,
        "aiRecommendation": ai_decision,
        "aiRecommendationDisplay": display,
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

    existing = db.query(DecisionResult).filter(DecisionResult.decision_run_id == run_uuid).first()
    if existing:
        existing.result_json = body.resultJson
        existing.needs_more_info = body.needsMoreInfo
        existing.missing_fields = body.missingFields
    else:
        db.add(
            DecisionResult(
                decision_run_id=run_uuid,
                result_json=body.resultJson,
                needs_more_info=body.needsMoreInfo,
                missing_fields=body.missingFields,
            )
        )

    case.status = "ai_recommendation"
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

        v = _first_non_empty(e.fact_json, e.fact_value)
        if isinstance(v, dict) and "items" in v and isinstance(v["items"], list):
            v = v["items"]

        if k in {"credits", "credit_hours", "units", "credits_or_units"}:
            fields["credits"] = EvidenceField(value=v, unknown=bool(e.unknown), citations=[])
            continue

        if k in {"contact_hours_lecture", "lecture_hours", "lecture_contact_hours"}:
            fields["contact_hours_lecture"] = EvidenceField(value=v, unknown=bool(e.unknown), citations=[])
            continue

        if k in {"contact_hours_lab", "lab_hours", "lab_contact_hours"}:
            fields["contact_hours_lab"] = EvidenceField(value=v, unknown=bool(e.unknown), citations=[])
            continue

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

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")


def load_policy_config() -> PolicyConfig:
    path = os.path.join(CONFIG_DIR, "policy.yaml")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return PolicyConfig(**data)


def _normalize_course_code(code: Optional[str]) -> str:
    """Normalize 'cpsc 2150', 'CPSC-2150', 'cpsc2150' -> 'CPSC-2150'."""
    if not code:
        return ""
    import re
    s = code.strip().upper()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"([A-Z])(\d)", r"\1-\2", s)
    s = re.sub(r"-+", "-", s)
    return s


def load_target_profile(course_requested: Optional[str]) -> TargetCourseProfile:
    """
    Look up the requested course in config/target_courses.yaml. Falls back to a
    permissive default profile if the course is not configured.
    """
    path = os.path.join(CONFIG_DIR, "target_courses.yaml")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}

    targets = (data.get("targets") or {})
    code = _normalize_course_code(course_requested)

    profile_data = targets.get(code)
    if profile_data:
        return TargetCourseProfile(
            target_credits=profile_data.get("target_credits", 3),
            target_lab_required=bool(profile_data.get("target_lab_required", False)),
            required_topics=profile_data.get("required_topics", []) or [],
            required_outcomes=profile_data.get("required_outcomes", []) or [],
        )

    # fallback: permissive profile — GPT handles per-target reasoning via its prompt,
    # and the rule engine gives full credit for components with no requirements.
    print(f"[build_contracts_packet] No target profile for '{course_requested}' (normalized '{code}'); using fallback.")
    return TargetCourseProfile(
        target_credits=3,
        target_lab_required=False,
        required_topics=[],
        required_outcomes=[],
    )


def build_contracts_packet(case: Request, evidence_rows: list[GroundedEvidence]) -> DecisionInputsPacket:
    source = map_evidence_rows_to_course_evidence(evidence_rows)
    target = load_target_profile(case.course_requested)
    policy = load_policy_config()

    return DecisionInputsPacket(
        case_id=str(case.request_id),
        source_course=source,
        target_course=target,
        policy=policy,
    )


def fetch_chunks_by_evidence(db: Session, evidence_rows) -> dict:
    """
    Query citation_chunks for each evidence row via the evidence_citations join table.
    Returns dict mapping str(evidence_id) -> list of chunk dicts.
    """
    if not evidence_rows:
        return {}

    import uuid as uuid_mod
    evidence_ids = [uuid_mod.UUID(str(e.evidence_id)) for e in evidence_rows]

    rows = db.execute(
        text("""
            SELECT ec.evidence_id, cc.chunk_uuid, cc.page_num, cc.snippet_text, cc.full_text
            FROM evidence_citations ec
            JOIN citation_chunks cc ON cc.chunk_uuid = ec.chunk_uuid
            WHERE ec.evidence_id = ANY(:ids)
        """),
        {"ids": evidence_ids},
    ).fetchall()

    result = {}
    for row in rows:
        ev_id = str(row[0])
        chunk_dict = {
            "chunk_uuid": str(row[1]),
            "page_num": row[2],
            "snippet_text": row[3],
            "full_text": row[4],
        }
        result.setdefault(ev_id, []).append(chunk_dict)

    return result


def validate_packet_or_raise(packet: DecisionInputsPacket) -> list[str]:
    missing: list[str] = []

    src = packet.source_course
    policy = packet.policy

    if policy.require_credits_known:
        if src.credits.unknown or src.credits.value in (None, "", []):
            missing.append("Missing source course credits.")

    if policy.require_topics_or_outcomes:
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
    payload = packet.model_dump()
    return sha256_str(stable_json_dumps(payload))


def generate_decision_packet(engine_result) -> dict:
    decision = engine_result.decision.value

    if decision == "APPROVE":
        why = "The source course meets the credit and content requirements under the current policy."
    elif decision == "APPROVE_WITH_BRIDGE":
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
        "citations": [],
    }


# ── Auth ─────────────────────────────────────────────────────────────────

@app.post("/api/auth/login", response_model=LoginOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    """Authenticate a reviewer/admin by utcId and password."""
    r = db.query(Reviewer).filter(Reviewer.utc_id == body.utcId).first()
    if not r:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if r.is_deleted:
        raise HTTPException(status_code=401, detail="Account has been deactivated")

    if r.expires_at and r.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Account has expired")

    # Plain text comparison for now — security lead will replace with hashed check
    if r.password_hash != body.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return LoginOut(
        reviewerId=str(r.reviewer_id),
        reviewerName=r.reviewer_name,
        utcId=r.utc_id,
        role=r.role or "reviewer",
    )


@app.get("/api/auth/me", response_model=LoginOut)
def get_me(reviewerId: str = Query(...), db: Session = Depends(get_db)):
    """Return the current user's profile by reviewerId. Frontend calls this on page load."""
    try:
        rid = uuid.UUID(reviewerId)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid reviewerId")

    r = db.query(Reviewer).filter(Reviewer.reviewer_id == rid).first()
    if not r or r.is_deleted:
        raise HTTPException(status_code=404, detail="User not found")

    if r.expires_at and r.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Account has expired")

    return LoginOut(
        reviewerId=str(r.reviewer_id),
        reviewerName=r.reviewer_name,
        utcId=r.utc_id,
        role=r.role or "reviewer",
    )


# ── Policy ────────────────────────────────────────────────────────────────

def _read_policy_yaml() -> dict:
    path = os.path.join(CONFIG_DIR, "policy.yaml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _write_policy_yaml(data: dict):
    path = os.path.join(CONFIG_DIR, "policy.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


@app.get("/api/policy", response_model=PolicyOut)
def get_policy():
    """Return the current policy configuration."""
    d = _read_policy_yaml()
    return PolicyOut(
        approveThreshold=d.get("approve_threshold", 90),
        bridgeThreshold=d.get("bridge_threshold", 80),
        needsInfoThreshold=d.get("needs_info_threshold", 70),
        requireLabParity=d.get("require_lab_parity", True),
        requireCreditsKnown=d.get("require_credits_known", True),
        requireTopicsOrOutcomes=d.get("require_topics_or_outcomes", True),
        minGrade=d.get("min_grade"),
        minContactHours=d.get("min_contact_hours", 0),
        maxCourseAgeYears=d.get("max_course_age_years", 0),
        mustIncludeTopics=d.get("must_include_topics") or [],
    )


@app.put("/api/policy", response_model=PolicyOut)
def update_policy(body: PolicyUpdateIn):
    """Update policy configuration. Only provided fields are changed."""
    d = _read_policy_yaml()

    if body.approveThreshold is not None:
        d["approve_threshold"] = body.approveThreshold
    if body.bridgeThreshold is not None:
        d["bridge_threshold"] = body.bridgeThreshold
    if body.needsInfoThreshold is not None:
        d["needs_info_threshold"] = body.needsInfoThreshold
    if body.requireLabParity is not None:
        d["require_lab_parity"] = body.requireLabParity
    if body.requireCreditsKnown is not None:
        d["require_credits_known"] = body.requireCreditsKnown
    if body.requireTopicsOrOutcomes is not None:
        d["require_topics_or_outcomes"] = body.requireTopicsOrOutcomes
    if body.minGrade is not None:
        d["min_grade"] = body.minGrade if body.minGrade != "" else None
    if body.minContactHours is not None:
        d["min_contact_hours"] = body.minContactHours
    if body.maxCourseAgeYears is not None:
        d["max_course_age_years"] = body.maxCourseAgeYears
    if body.mustIncludeTopics is not None:
        d["must_include_topics"] = body.mustIncludeTopics

    _write_policy_yaml(d)

    return PolicyOut(
        approveThreshold=d.get("approve_threshold", 90),
        bridgeThreshold=d.get("bridge_threshold", 80),
        needsInfoThreshold=d.get("needs_info_threshold", 70),
        requireLabParity=d.get("require_lab_parity", True),
        requireCreditsKnown=d.get("require_credits_known", True),
        requireTopicsOrOutcomes=d.get("require_topics_or_outcomes", True),
        minGrade=d.get("min_grade"),
        minContactHours=d.get("min_contact_hours", 0),
        maxCourseAgeYears=d.get("max_course_age_years", 0),
        mustIncludeTopics=d.get("must_include_topics") or [],
    )


@app.get("/api/reviewers", response_model=list[ReviewerOut])
def list_reviewers(db: Session = Depends(get_db)):
    reviewers = db.query(Reviewer).order_by(Reviewer.created_at.desc()).all()

    return [
        ReviewerOut(
            reviewerId=str(r.reviewer_id),
            reviewerName=r.reviewer_name,
            utcId=r.utc_id,
            role=r.role or "reviewer",
            expiresAt=r.expires_at,
            isDeleted=r.is_deleted or False,
            createdAt=r.created_at,
        )
        for r in reviewers
    ]


@app.post("/api/reviewers", response_model=ReviewerOut)
def create_reviewer(body: ReviewerCreateIn, db: Session = Depends(get_db)):
    r = Reviewer(
        reviewer_name=body.reviewerName,
        utc_id=body.utcId,
        password_hash=body.password,
        role=body.role,
        created_at=now_utc(),
    )
    db.add(r)
    db.commit()
    db.refresh(r)

    return ReviewerOut(
        reviewerId=str(r.reviewer_id),
        reviewerName=r.reviewer_name,
        utcId=r.utc_id,
        role=r.role or "reviewer",
        expiresAt=r.expires_at,
        isDeleted=r.is_deleted or False,
        createdAt=r.created_at,
    )


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
        utcId=r.utc_id,
        role=r.role or "reviewer",
        expiresAt=r.expires_at,
        isDeleted=r.is_deleted or False,
        createdAt=r.created_at,
    )


# ── Courses ──────────────────────────────────────────────────────────────

@app.get("/api/courses", response_model=list[CourseOut])
def list_courses(
    department: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Course)
    if department:
        q = q.filter(Course.department.ilike(department))
    courses = q.order_by(Course.course_code).all()
    return [
        CourseOut(
            courseId=str(c.course_id),
            courseCode=c.course_code,
            displayName=c.display_name,
            department=c.department,
            credits=c.credits,
            labRequired=c.lab_required,
            prerequisites=c.prerequisites,
            requiredTopics=c.required_topics or [],
            requiredOutcomes=c.required_outcomes or [],
            description=c.description,
            createdAt=c.created_at,
            updatedAt=c.updated_at,
        )
        for c in courses
    ]


@app.post("/api/courses", response_model=CourseOut, status_code=201)
def create_course(body: CourseIn, db: Session = Depends(get_db)):
    existing = db.query(Course).filter(Course.course_code == body.courseCode).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Course {body.courseCode} already exists.")

    c = Course(
        course_code=body.courseCode,
        display_name=body.displayName,
        department=body.department,
        credits=body.credits,
        lab_required=body.labRequired,
        prerequisites=body.prerequisites,
        required_topics=body.requiredTopics,
        required_outcomes=body.requiredOutcomes,
        description=body.description,
    )
    db.add(c)
    db.commit()
    db.refresh(c)

    return CourseOut(
        courseId=str(c.course_id),
        courseCode=c.course_code,
        displayName=c.display_name,
        department=c.department,
        credits=c.credits,
        labRequired=c.lab_required,
        prerequisites=c.prerequisites,
        requiredTopics=c.required_topics or [],
        requiredOutcomes=c.required_outcomes or [],
        description=c.description,
        createdAt=c.created_at,
        updatedAt=c.updated_at,
    )


@app.get("/api/courses/{courseId}", response_model=CourseOut)
def get_course(courseId: str, db: Session = Depends(get_db)):
    try:
        cid = uuid.UUID(courseId)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid courseId (must be a UUID)")

    c = db.query(Course).filter(Course.course_id == cid).first()
    if not c:
        raise HTTPException(status_code=404, detail="Course not found")

    return CourseOut(
        courseId=str(c.course_id),
        courseCode=c.course_code,
        displayName=c.display_name,
        department=c.department,
        credits=c.credits,
        labRequired=c.lab_required,
        prerequisites=c.prerequisites,
        requiredTopics=c.required_topics or [],
        requiredOutcomes=c.required_outcomes or [],
        description=c.description,
        createdAt=c.created_at,
        updatedAt=c.updated_at,
    )


@app.post("/api/courses/seed-from-csv", status_code=201)
def seed_courses_from_csv(db: Session = Depends(get_db)):
    """Load all courses from Data/Processed/ParsedData.csv into the courses table."""
    import csv

    csv_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Data", "Processed", "ParsedData.csv",
    )
    if not os.path.exists(csv_path):
        raise HTTPException(status_code=404, detail=f"CSV not found at {csv_path}")

    # Track codes we've already seen (handles duplicates within the CSV itself)
    seen_codes = set()
    # Also load existing codes from DB
    existing_codes = {r[0] for r in db.query(Course.course_code).all()}

    inserted = 0
    skipped = 0
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            course_code = (row.get("course_code") or "").strip()
            if not course_code or course_code in seen_codes or course_code in existing_codes:
                skipped += 1
                continue

            seen_codes.add(course_code)

            # Use credits_min as credits; default to 3 if not parseable
            try:
                credits = int(float(row.get("credits_min") or 3))
            except (ValueError, TypeError):
                credits = 3

            # subject column serves as department
            department = (row.get("subject") or "").strip() or "General"

            c = Course(
                course_code=course_code,
                display_name=(row.get("title") or "").strip() or course_code,
                department=department,
                credits=credits,
                lab_required=False,
                prerequisites=(row.get("prerequisites") or "").strip() or None,
                required_topics=[],
                required_outcomes=[],
                description=(row.get("description") or "").strip() or None,
            )
            db.add(c)
            inserted += 1

    db.commit()
    return {"inserted": inserted, "skipped": skipped}


@app.delete("/api/cases/{case_id}")
def delete_case(case_id: str, db: Session = Depends(get_db)):
    req = db.query(Request).filter(Request.request_id == uuid.UUID(case_id)).first()
    if not req:
        raise HTTPException(status_code=404, detail="Case not found.")
    db.delete(req)
    db.commit()
    return {"message": "Case deleted successfully.", "caseId": case_id}