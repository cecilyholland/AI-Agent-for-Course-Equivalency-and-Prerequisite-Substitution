# app/extraction/pipeline.py
# orchestrates, writes DB, writes manifest

# app/extraction/pipeline.py
from __future__ import annotations

import json
import os
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy import create_engine, text

from .pdf_text import ensure_searchable_text
from .chunking import Chunk, chunk_page_text
from .syllabus_parser import extract_syllabus_facts
from .catalog_parser import extract_catalog_structure_and_candidates, match_candidates_to_target
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def _log(message: str) -> None:
    try:
        # Optional: integrate with app.workflow_logger if desired later
        pass
    except Exception:
        pass
    print(f"[extraction] {message}")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _engine():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set. Set it to your Postgres SQLAlchemy URL.")
    return create_engine(DATABASE_URL, future=True)


def classify_document(filename: str) -> str:
    fn = filename.lower()
    if "syllabus" in fn:
        return "syllabus"
    return "catalog"


# ----------------------------
# DB Writers (schema-aligned)
# ----------------------------
def _create_extraction_run(conn, request_id: str) -> str:
    row = conn.execute(
        text(
            """
            INSERT INTO extraction_runs (request_id, status, started_at)
            VALUES (:request_id, 'running', NOW())
            RETURNING extraction_run_id
            """
        ),
        {"request_id": request_id},
    ).fetchone()
    return str(row[0])


def _finish_extraction_run(
    conn,
    extraction_run_id: str,
    status: str,
    manifest_uri: Optional[str],
    manifest_sha256: Optional[str],
    error_message: Optional[str],
) -> None:
    conn.execute(
        text(
            """
            UPDATE extraction_runs
            SET status=:status,
                finished_at=NOW(),
                error_message=:error_message,
                manifest_uri=:manifest_uri,
                manifest_sha256=:manifest_sha256
            WHERE extraction_run_id=:id
            """
        ),
        {
            "status": status,
            "error_message": error_message,
            "manifest_uri": manifest_uri,
            "manifest_sha256": manifest_sha256,
            "id": extraction_run_id,
        },
    )


def _insert_chunk(conn, doc_id: str, run_id: str, ch: Chunk) -> str:
    basis = f"{doc_id}|{run_id}|{ch.page_num}|{ch.span_start}|{ch.span_end}|{ch.full_text}"
    chunk_sha_id = _sha256_text(basis)

    row = conn.execute(
        text(
            """
            INSERT INTO citation_chunks (
              chunk_sha_id, doc_id, extraction_run_id, page_num, span_start, span_end, snippet_text, full_text
            )
            VALUES (
              :chunk_sha_id, :doc_id, :run_id, :page_num, :span_start, :span_end, :snippet_text, :full_text
            )
            ON CONFLICT (chunk_sha_id) DO UPDATE
              SET snippet_text = EXCLUDED.snippet_text
            RETURNING chunk_uuid
            """
        ),
        {
            "chunk_sha_id": chunk_sha_id,
            "doc_id": doc_id,
            "run_id": run_id,
            "page_num": ch.page_num,
            "span_start": ch.span_start,
            "span_end": ch.span_end,
            "snippet_text": ch.snippet_text,
            "full_text": ch.full_text,
        },
    ).fetchone()
    return str(row[0])


def _insert_evidence(
    conn,
    request_id: str,
    run_id: str,
    fact_type: str,
    fact_key: str,
    fact_value: Optional[str],
    fact_json: Optional[dict],
    unknown: bool,
    notes: Optional[str],
) -> str:
    row = conn.execute(
        text(
            """
            INSERT INTO grounded_evidence (
              request_id, extraction_run_id, fact_type, fact_key, fact_value, fact_json, unknown, notes
            )
            VALUES (
              :request_id, :run_id, :fact_type, :fact_key, :fact_value, CAST(:fact_json AS jsonb), :unknown, :notes
            )
            RETURNING evidence_id
            """
        ),
        {
            "request_id": request_id,
            "run_id": run_id,
            "fact_type": fact_type,
            "fact_key": fact_key,
            "fact_value": fact_value,
            # Pass a JSON string or None
            "fact_json": json.dumps(fact_json) if fact_json is not None else None,
            "unknown": unknown,
            "notes": notes,
        },
    ).fetchone()
    return str(row[0])

def _first_nonempty_chunk_list(page_chunk_uuids: List[List[str]]) -> List[str]:
    for cuids in page_chunk_uuids:
        if cuids:
            return cuids
    return []

def _link_evidence_to_chunks(conn, evidence_id: str, chunk_uuids: List[str]) -> None:
    if not chunk_uuids:
        raise RuntimeError(
            f"Refusing to write evidence_citations with 0 chunks for evidence_id={evidence_id}"
        )

    for cu in chunk_uuids:
        conn.execute(
            text(
                """
                INSERT INTO evidence_citations (evidence_id, chunk_uuid)
                VALUES (:evidence_id, :chunk_uuid)
                ON CONFLICT DO NOTHING
                """
            ),
            {"evidence_id": evidence_id, "chunk_uuid": cu},
        )



def _get_active_documents_for_request(conn, request_id: str) -> List[Dict[str, str]]:
    rows = conn.execute(
        text(
            """
            SELECT doc_id, filename, storage_uri
            FROM documents
            WHERE request_id = :request_id AND is_active = TRUE
            ORDER BY created_at ASC
            """
        ),
        {"request_id": request_id},
    ).fetchall()

    return [{"doc_id": str(r[0]), "filename": r[1], "storage_uri": r[2]} for r in rows]


def _set_request_status(conn, request_id: str, status: str) -> None:
    conn.execute(
        text("UPDATE requests SET status=:status, updated_at=NOW() WHERE request_id=:id"),
        {"status": status, "id": request_id},
    )


def _all_chunk_uuids(page_chunk_uuids: List[List[str]]) -> List[str]:
    """Flatten all per-page chunk uuid lists into one list."""
    out: List[str] = []
    for cuids in page_chunk_uuids:
        out.extend(cuids)
    return out
# ----------------------------
# Public API
# ----------------------------
def run_extraction(request_id: str, output_dir: str = "Data/Processed/manifests") -> str:
    """
    Runs information extraction + grounding for a request.
    Writes results to Postgres and writes a manifest JSON to disk.

    Returns:
      extraction_run_id (UUID string)
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    engine = _engine()

    # -------------------------
    # Phase A: create run row (must persist even if extraction fails)
    # -------------------------
    with engine.begin() as conn:
        docs = _get_active_documents_for_request(conn, request_id)
        if not docs:
            raise RuntimeError(f"No active documents found for request_id={request_id}")

        run_id = _create_extraction_run(conn, request_id)
        _set_request_status(conn, request_id, "extracting")

    # Everything below can fail; run_id will still exist in DB
    manifest: Dict[str, Any] = {
        "request_id": request_id,
        "extraction_run_id": run_id,
        "started_at": _now_utc_iso(),
        "documents": [],
        "warnings": [],
    }

    # Collect target course info from syllabi for matching catalog
    target_course_codes: set[str] = set()
    target_titles: set[str] = set()
    global_fallback_chunks: List[str] = []

    try:
        # -------------------------
        # Phase B: do extraction work in ONE transaction
        #   - if anything fails, chunks/evidence roll back
        #   - but extraction_runs row persists from Phase A
        # -------------------------
        with engine.begin() as conn:
            # Phase 1: syllabi first (so we can match catalog docs later)
            ordered = sorted(docs, key=lambda d: 0 if classify_document(d["filename"]) == "syllabus" else 1)

            for d in ordered:
                doc_id = d["doc_id"]
                filename = d["filename"]
                pdf_path = d["storage_uri"]

                _log(f"Processing doc {filename} ({doc_id}) path={pdf_path}")

                pages_text, used_ocr, ocr_path, warning = ensure_searchable_text(
                    pdf_path=pdf_path,
                    output_dir=output_dir,
                    prefer_ocr=True,
                )
                if warning:
                    manifest["warnings"].append(warning)

                # Chunk + write chunks
                page_chunk_uuids: List[List[str]] = []
                total_chunks = 0
                for i, pt in enumerate(pages_text, start=1):
                    chunks = chunk_page_text(pt, page_num=i)
                    cuids: List[str] = []
                    for ch in chunks:
                        cu = _insert_chunk(conn, doc_id, run_id, ch)
                        cuids.append(cu)
                    page_chunk_uuids.append(cuids)
                    total_chunks += len(cuids)

                doc_type = classify_document(filename)

                doc_manifest = {
                    "doc_id": doc_id,
                    "filename": filename,
                    "storage_uri": pdf_path,
                    "doc_type": doc_type,
                    "page_count": len(pages_text),
                    "used_ocr": used_ocr,
                    "ocr_output_pdf": ocr_path,
                    "chunks_written": total_chunks,
                    "evidence_written": 0,
                }
                all_chunks = _all_chunk_uuids(page_chunk_uuids)
                doc_fallback_chunks = _first_nonempty_chunk_list(page_chunk_uuids)

                # set global fallback once (first doc that has any chunks)
                if doc_fallback_chunks and not global_fallback_chunks:
                    global_fallback_chunks = doc_fallback_chunks

                # if we got 0 chunks for this doc, record a warning (very useful)
                if total_chunks == 0:
                    manifest["warnings"].append(
                        f"No chunks extracted for doc_id={doc_id} filename={filename}. "
                        f"Document may be image-only or have unsupported text encoding."
                    )

                # Evidence extraction + citations
                if doc_type == "syllabus":
                    facts = extract_syllabus_facts(pages_text)

                    if facts.get("course_code"):
                        target_course_codes.add(facts["course_code"])
                    if facts.get("title"):
                        target_titles.add(facts["title"])

                    for key in ("course_code", "title", "credits_or_units", "description", "prerequisites"):
                        val = facts.get(key)
                        unknown = val is None
                        notes = None if val else f"Missing {key} in syllabus"
                        ev_id = _insert_evidence(
                            conn=conn,
                            request_id=request_id,
                            run_id=run_id,
                            fact_type="syllabus_course",
                            fact_key=key,
                            fact_value=val,
                            fact_json=None,
                            unknown=unknown,
                            notes=notes,
                        )
                        cite_chunks = doc_fallback_chunks or global_fallback_chunks
                        _link_evidence_to_chunks(conn, ev_id, cite_chunks)
                        doc_manifest["evidence_written"] += 1

                else:
                    structure_type, candidates = extract_catalog_structure_and_candidates(pages_text)

                    # 1) Always record catalog structure_type with a safe citation fallback
                    ev_id = _insert_evidence(
                        conn=conn,
                        request_id=request_id,
                        run_id=run_id,
                        fact_type="catalog_document",
                        fact_key="structure_type",
                        fact_value=structure_type,
                        fact_json=None,
                        unknown=False,
                        notes=None,
                    )
                    cite_chunks = doc_fallback_chunks or global_fallback_chunks
                    _link_evidence_to_chunks(conn, ev_id, cite_chunks)
                    doc_manifest["evidence_written"] += 1

                    # 2) Match candidates to syllabus target (may be None)
                    target_code = next(iter(target_course_codes), None)
                    target_title = next(iter(target_titles), None)

                    best, reason = match_candidates_to_target(candidates, target_code, target_title)

                    if best is not None:
                        key = f"match::{best.get('course_code') or (target_code or 'unknown')}"
                        ev_id = _insert_evidence(
                            conn=conn,
                            request_id=request_id,
                            run_id=run_id,
                            fact_type="catalog_course_match",
                            fact_key=key,
                            fact_value=best.get("course_code"),
                            fact_json=best,
                            unknown=False,
                            notes=f"Catalog matched via {reason}",
                        )

                        # Prefer cited pages from the match; fallback if empty/invalid
                        cite: List[str] = []
                        for p in ((best or {}).get("source_pages") or []):
                            if 1 <= p <= len(page_chunk_uuids):
                                cite.extend(page_chunk_uuids[p - 1])

                        if not cite:
                            cite = doc_fallback_chunks or global_fallback_chunks

                        _link_evidence_to_chunks(conn, ev_id, cite)
                        doc_manifest["evidence_written"] += 1

                    else:
                        key = f"match::{target_code or 'unknown'}"
                        ev_id = _insert_evidence(
                            conn=conn,
                            request_id=request_id,
                            run_id=run_id,
                            fact_type="catalog_course_match",
                            fact_key=key,
                            fact_value=None,
                            fact_json={
                                "target_course_code": target_code,
                                "target_title": target_title,
                                "reason": reason,
                                "candidate_count": len(candidates),
                            },
                            unknown=True,
                            notes="No matching course found in catalog document",
                        )
                        cite_chunks = doc_fallback_chunks or global_fallback_chunks
                        _link_evidence_to_chunks(conn, ev_id, cite_chunks)
                        doc_manifest["evidence_written"] += 1

                manifest["documents"].append(doc_manifest)

        # -------------------------
        # Phase C: write manifest + mark run completed (fresh transaction)
        # -------------------------
        manifest["finished_at"] = _now_utc_iso()
        manifest_path = str(Path(output_dir) / f"extraction_manifest_{request_id}_{run_id}.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        manifest_sha = _sha256_file(manifest_path)

        with engine.begin() as conn:
            _finish_extraction_run(
                conn=conn,
                extraction_run_id=run_id,
                status="completed",
                manifest_uri=manifest_path,
                manifest_sha256=manifest_sha,
                error_message=None,
            )
            _set_request_status(conn, request_id, "ready_for_decision")

        _log(f"Extraction completed. run_id={run_id}")
        return run_id

    except Exception as e:
        # mark run failed in a fresh transaction (always works)
        with engine.begin() as conn:
            _finish_extraction_run(
                conn=conn,
                extraction_run_id=run_id,
                status="failed",
                manifest_uri=None,
                manifest_sha256=None,
                error_message=str(e),
            )
            _set_request_status(conn, request_id, "needs_info")

        _log(f"Extraction failed. run_id={run_id} error={e}")
        raise