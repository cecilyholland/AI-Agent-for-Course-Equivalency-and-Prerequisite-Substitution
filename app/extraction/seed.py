# app/extraction/seed.py
from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

from sqlalchemy import create_engine, text


DATABASE_URL = os.getenv("DATABASE_URL")


def _engine():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set. Set it to your Postgres SQLAlchemy URL.")
    return create_engine(DATABASE_URL, future=True)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _create_request(
    conn,
    student_id: str,
    student_name: Optional[str],
    course_requested: Optional[str],
    status: str = "uploaded",
) -> str:
    row = conn.execute(
        text(
            """
            INSERT INTO requests (student_id, student_name, course_requested, status)
            VALUES (:student_id, :student_name, :course_requested, :status)
            RETURNING request_id
            """
        ),
        {
            "student_id": student_id,
            "student_name": student_name,
            "course_requested": course_requested,
            "status": status,
        },
    ).fetchone()
    return str(row[0])


def _deactivate_existing_docs(conn, request_id: str) -> int:
    res = conn.execute(
        text(
            """
            UPDATE documents
            SET is_active = FALSE
            WHERE request_id = :rid AND is_active = TRUE
            """
        ),
        {"rid": request_id},
    )
    return res.rowcount or 0


def _insert_document_row(
    conn,
    request_id: str,
    filename: str,
    storage_uri: str,
    sha256: str,
    size_bytes: int,
    content_type: str = "application/pdf",
    is_active: bool = True,
) -> str:
    row = conn.execute(
        text(
            """
            INSERT INTO documents (
              request_id, filename, content_type, sha256, storage_uri, size_bytes, is_active
            )
            VALUES (
              :request_id, :filename, :content_type, :sha256, :storage_uri, :size_bytes, :is_active
            )
            RETURNING doc_id
            """
        ),
        {
            "request_id": request_id,
            "filename": filename,
            "content_type": content_type,
            "sha256": sha256,
            "storage_uri": storage_uri,
            "size_bytes": size_bytes,
            "is_active": is_active,
        },
    ).fetchone()
    return str(row[0])


@dataclass(frozen=True)
class SeedResult:
    request_id: str
    upload_dir: str
    documents: List[Dict[str, Any]]
    deactivated_count: int


def seed_request_with_pdfs(
    pdf_paths: List[str],
    *,
    request_id: Optional[str] = None,
    student_id: str = "student_dev",
    student_name: Optional[str] = None,
    course_requested: Optional[str] = None,
    uploads_root: str = "Data/Raw/Uploads",
    deactivate_existing: bool = True,
) -> SeedResult:
    """
    Dev helper:
    - Ensures a request exists
    - Copies given PDFs into Data/Raw/Uploads/<request_id>/
    - Inserts documents rows (is_active=true by default)

    Returns:
      SeedResult with request_id + doc metadata.
    """
    if not pdf_paths:
        raise ValueError("pdf_paths is empty.")

    engine = _engine()
    uploads_root_p = Path(uploads_root)

    with engine.begin() as conn:
        if request_id is None:
            request_id = _create_request(
                conn,
                student_id=student_id,
                student_name=student_name,
                course_requested=course_requested,
                status="uploaded",
            )

        deactivated = 0
        if deactivate_existing:
            deactivated = _deactivate_existing_docs(conn, request_id)

        upload_dir = uploads_root_p / request_id
        _ensure_dir(upload_dir)

        docs_out: List[Dict[str, Any]] = []

        for src in pdf_paths:
            src_p = Path(src)
            if not src_p.exists():
                raise FileNotFoundError(f"PDF not found: {src}")

            dest_p = upload_dir / src_p.name
            shutil.copy2(src_p, dest_p)

            sha = _sha256_file(dest_p)
            size_bytes = dest_p.stat().st_size

            doc_id = _insert_document_row(
                conn=conn,
                request_id=request_id,
                filename=dest_p.name,
                storage_uri=str(dest_p),
                sha256=sha,
                size_bytes=size_bytes,
                content_type="application/pdf",
                is_active=True,
            )

            docs_out.append(
                {
                    "doc_id": doc_id,
                    "filename": dest_p.name,
                    "storage_uri": str(dest_p),
                    "sha256": sha,
                    "size_bytes": size_bytes,
                }
            )

    return SeedResult(
        request_id=request_id,
        upload_dir=str(Path(uploads_root) / request_id),
        documents=docs_out,
        deactivated_count=deactivated,
    )


def seed_from_student_folder(
    student_folder: str,
    *,
    request_id: Optional[str] = None,
    student_id: str = "student_dev",
    student_name: Optional[str] = None,
    course_requested: Optional[str] = None,
    uploads_root: str = "Data/Raw/Uploads",
    deactivate_existing: bool = True,
) -> SeedResult:
    """
    Convenience: point at a folder like Data/Raw/StudentTestCases/Student1
    containing 2 PDFs (syllabus + course desc).
    """
    folder = Path(student_folder)
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"Folder not found: {student_folder}")

    pdfs = sorted([p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"])
    if not pdfs:
        raise ValueError(f"No PDFs found in {student_folder}")
    if len(pdfs) < 2:
        raise ValueError(f"Expected at least 2 PDFs (syllabus + course desc) in {student_folder}, found {len(pdfs)}")

    return seed_request_with_pdfs(
        [str(p) for p in pdfs],
        request_id=request_id,
        student_id=student_id,
        student_name=student_name,
        course_requested=course_requested,
        uploads_root=uploads_root,
        deactivate_existing=deactivate_existing,
    )


def seed_bulk_students(
    parent_folder: str,
    *,
    uploads_root: str = "Data/Raw/Uploads",
    student_id_prefix: str = "student",
) -> List[SeedResult]:
    """
    Bulk seed: parent folder contains Student1..Student10 subfolders.
    Returns list of SeedResult.
    """
    parent = Path(parent_folder)
    if not parent.exists() or not parent.is_dir():
        raise FileNotFoundError(f"Parent folder not found: {parent_folder}")

    results: List[SeedResult] = []
    student_dirs = sorted([p for p in parent.iterdir() if p.is_dir() and p.name.lower().startswith("student")])

    for sd in student_dirs:
        # e.g., Student1 -> student1
        sid = f"{student_id_prefix}{sd.name.replace('Student', '')}".lower()
        res = seed_from_student_folder(
            str(sd),
            student_id=sid,
            student_name=sd.name,
            course_requested=None,
            uploads_root=uploads_root,
            deactivate_existing=False,  # bulk seeding typically makes new requests
        )
        results.append(res)

    return results