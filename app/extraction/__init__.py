# app/extraction/__init__.py
"""
Extraction & grounding package.

Public API:
- run_extraction(request_id: str, output_dir: str = "Data/Processed/manifests") -> str
- process_transcript_pdf(pdf_path, request_id, db_session, filter_to_case) -> dict
- get_case_course_codes_from_db(request_id: UUID) -> List[str]
"""

from .pipeline import run_extraction
from .transcript_parser import (
    process_transcript_pdf,
    extract_transcript_courses,
    get_case_course_codes_from_db,
)

__all__ = [
    "run_extraction",
    "process_transcript_pdf",
    "extract_transcript_courses",
    "get_case_course_codes_from_db",
]