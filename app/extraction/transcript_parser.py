# app/extraction/transcript_parser.py
"""
Transcript parser for extracting course records from student transcript PDFs.

Extracts:
  - course_code: The course identifier (e.g., "CPSC 1100", "MATH 1530")
  - grade: Letter grade received (e.g., "A", "B+", "CR")
  - term_taken: Academic term (e.g., "Fall 2023", "Spring 2024")

The parser matches extracted course codes against the case's grounded_evidence
(from syllabus/catalog uploads) using the request_id as the link.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Set
from uuid import UUID
from sqlalchemy import create_engine, text

# Common course code patterns
# Standard format: "CPSC 1100", "MATH 1530", "BIOL 1110"
# Also matches no-space format: "BIOL1010", "CHEM1120"
COURSE_CODE_RE = re.compile(r"\b([A-Z]{2,6})\s*(\d{3,4}[A-Z]?)\b")

# MIT-style course codes: "5.111", "18.01", "10.301"
MIT_COURSE_CODE_RE = re.compile(r"\b(\d{1,2})\.(\d{2,3}[A-Z]?)\b")

# Grade patterns - letter grades with optional +/-
# Must have word boundary or whitespace to avoid matching within words
# Order matters: check +/- variants first to avoid partial matches
GRADE_RE = re.compile(r"(?<![A-Za-z])([A-DF][+-]|[A-DF]|CR|NC|P|NP|W|WP|WF|IP|AU)(?![A-Za-z])")

# Term patterns - various formats
TERM_PATTERNS = [
    # "Fall 2023", "Spring 2024", "Summer 2023"
    re.compile(r"\b(Fall|Spring|Summer|Winter)\s+(\d{4})\b", re.IGNORECASE),
    # "FA23", "SP24", "SU23"
    re.compile(r"\b(FA|SP|SU|WI)(\d{2})\b", re.IGNORECASE),
    # "2023 Fall", "2024 Spring"
    re.compile(r"\b(\d{4})\s+(Fall|Spring|Summer|Winter)\b", re.IGNORECASE),
    # "202310" (YYYYMM format used by some systems)
    re.compile(r"\b(20\d{2})(0[1-9]|1[0-2])\b"),
]

# Common transcript section headers to detect structure
SECTION_HEADERS = [
    "course", "title", "grade", "credits", "hours", "points",
    "term", "semester", "quarter", "gpa", "attempted", "earned"
]


@dataclass
class TranscriptCourse:
    """Represents a single course record extracted from a transcript."""
    course_code: str
    grade: str
    term_taken: str
    credits: Optional[str] = None
    title: Optional[str] = None
    source_page: Optional[int] = None


def normalize_term(term_str: str) -> str:
    """
    Normalize term string to consistent format: "Season YYYY"
    Examples:
        "FA23" -> "Fall 2023"
        "202310" -> "Fall 2023"
        "Spring 2024" -> "Spring 2024"
    """
    term_str = term_str.strip()

    # Already in good format
    if re.match(r"(Fall|Spring|Summer|Winter)\s+\d{4}", term_str, re.IGNORECASE):
        return term_str.title()

    # Short format: FA23, SP24
    short_match = re.match(r"(FA|SP|SU|WI)(\d{2})", term_str, re.IGNORECASE)
    if short_match:
        season_map = {"FA": "Fall", "SP": "Spring", "SU": "Summer", "WI": "Winter"}
        season = season_map.get(short_match.group(1).upper(), short_match.group(1))
        year = "20" + short_match.group(2)
        return f"{season} {year}"

    # YYYYMM format
    yyyymm_match = re.match(r"(20\d{2})(0[1-9]|1[0-2])", term_str)
    if yyyymm_match:
        year = yyyymm_match.group(1)
        month = int(yyyymm_match.group(2))
        if month in [1, 2]:
            season = "Spring"
        elif month in [5, 6, 7]:
            season = "Summer"
        elif month in [8, 9]:
            season = "Fall"
        else:
            season = "Fall"  # Default
        return f"{season} {year}"

    # Year Season format: "2024 Spring"
    reverse_match = re.match(r"(\d{4})\s+(Fall|Spring|Summer|Winter)", term_str, re.IGNORECASE)
    if reverse_match:
        return f"{reverse_match.group(2).title()} {reverse_match.group(1)}"

    return term_str


def normalize_grade(grade_str: str) -> str:
    """Normalize grade to uppercase standard format."""
    return grade_str.strip().upper()


def normalize_course_code(code: str) -> str:
    """
    Normalize course code to standard format: "SUBJ NNNN" or "N.NNN" for MIT.
    Examples:
        "CPSC1100" -> "CPSC 1100"
        "cpsc 1100" -> "CPSC 1100"
        "5.111" -> "5.111" (MIT format kept as-is)
    """
    code = code.strip().upper()
    # Check for MIT-style format first (keep as-is with period)
    mit_match = re.match(r"(\d{1,2})\.(\d{2,3}[A-Z]?)", code)
    if mit_match:
        return f"{mit_match.group(1)}.{mit_match.group(2)}"
    # Ensure space between subject and number for standard format
    match = re.match(r"([A-Z]{2,6})\s*(\d{3,4}[A-Z]?)", code)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return code


def extract_term_from_context(lines: List[str], current_idx: int) -> Optional[str]:
    """
    Look for term information in surrounding context.
    Transcripts often have term headers above course listings.
    """
    # Search backwards up to 10 lines for a term header
    for i in range(max(0, current_idx - 10), current_idx):
        line = lines[i]
        for pattern in TERM_PATTERNS:
            match = pattern.search(line)
            if match:
                return match.group(0)
    return None


def get_case_course_codes_from_db(request_id: UUID) -> List[str]:
    """
    Fetch course codes associated with a case from grounded_evidence table.

    This looks up the syllabus/catalog extraction results for the given request_id
    to find what course codes the student uploaded documents for.

    Args:
        request_id: UUID of the case/request

    Returns:
        List of course codes (normalized format like "MED 2150")
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")

    engine = create_engine(database_url, future=True)

    with engine.connect() as conn:
        # Get course codes from syllabus extractions
        rows = conn.execute(
            text("""
                SELECT DISTINCT fact_value
                FROM grounded_evidence
                WHERE request_id = :request_id
                  AND fact_key = 'course_code'
                  AND fact_value IS NOT NULL
            """),
            {"request_id": str(request_id)}
        ).fetchall()

        course_codes = [row[0] for row in rows if row[0]]

        # Also get from catalog matches if available
        rows2 = conn.execute(
            text("""
                SELECT DISTINCT fact_value
                FROM grounded_evidence
                WHERE request_id = :request_id
                  AND fact_type = 'catalog_course_match'
                  AND fact_value IS NOT NULL
            """),
            {"request_id": str(request_id)}
        ).fetchall()

        for row in rows2:
            if row[0] and row[0] not in course_codes:
                course_codes.append(row[0])

    return course_codes


def extract_tabular_transcript_courses(pages_text: List[str]) -> List[TranscriptCourse]:
    """
    Extract courses from tabular transcript format.

    Handles formats like:
        Course Code | Course Title | Credits | Grade | Term
        BIOL1010    | General Biology I | 4 | B+ | Fall 2023

    Also handles multi-line terms where season and year are on separate lines:
        Spring
        BIOL1020    | General Biology II | 4 | A-
        2024

    In this case, "Spring" appears on the line BEFORE the course,
    and "2024" appears on the line AFTER.
    """
    courses: List[TranscriptCourse] = []
    pending_season: Optional[str] = None  # Season from previous line

    for page_num, page_text in enumerate(pages_text, start=1):
        lines = page_text.splitlines()

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            if not line:
                i += 1
                continue

            # Check if this line contains a season word (for next course)
            # Handle patterns like "Spring", "Brown Spring", etc.
            season_only = re.match(r"^(Fall|Spring|Summer|Winter)$", line, re.IGNORECASE)
            if season_only:
                pending_season = season_only.group(1).title()
                i += 1
                continue

            # Handle pattern like "Brown Spring" or "Institution Spring"
            season_with_prefix = re.search(r"(Fall|Spring|Summer|Winter)\s*$", line, re.IGNORECASE)
            if season_with_prefix and not COURSE_CODE_RE.match(line):
                pending_season = season_with_prefix.group(1).title()
                i += 1
                continue

            # Check if this line is just a year or "Institution YYYY" pattern
            # Skip it here - we'll look ahead when processing course lines
            if re.match(r"^\d{4}$", line):
                i += 1
                continue

            # Handle pattern like "University 2027"
            if re.match(r"^(University|College|Institute)\s+\d{4}$", line, re.IGNORECASE):
                i += 1
                continue

            # Look for course code at start of line (standard format like "BIOL 1100")
            code_match = COURSE_CODE_RE.match(line)
            is_mit_format = False
            if not code_match:
                # Try MIT format (like "5.111", "18.01")
                code_match = MIT_COURSE_CODE_RE.match(line)
                if code_match:
                    is_mit_format = True
            if not code_match:
                # Try to find course code anywhere in line (handles weird PDF layouts)
                code_match = COURSE_CODE_RE.search(line)
                if not code_match:
                    code_match = MIT_COURSE_CODE_RE.search(line)
                    if code_match:
                        is_mit_format = True
                if not code_match:
                    # Don't reset pending_season if line contains institution name
                    # (could be multi-line wrapping)
                    if not re.search(r"\b(University|College|Institute)\b", line, re.IGNORECASE):
                        pending_season = None
                    i += 1
                    continue

            # Build the course code string based on format
            if is_mit_format:
                course_code = normalize_course_code(f"{code_match.group(1)}.{code_match.group(2)}")
            else:
                course_code = normalize_course_code(f"{code_match.group(1)} {code_match.group(2)}")
            rest_of_line = line[code_match.end():]

            # Look for grade - need to find it after title and credits
            grade = None
            grade_pos = -1

            for gm in GRADE_RE.finditer(rest_of_line):
                grade = gm.group(1)
                grade_pos = gm.start()
                break

            if not grade:
                pending_season = None
                i += 1
                continue

            grade = normalize_grade(grade)

            # Look for term - check current line first
            term = None
            for pattern in TERM_PATTERNS:
                term_match = pattern.search(line)
                if term_match:
                    term = normalize_term(term_match.group(0))
                    break

            # If term not on current line, check for split term pattern
            if not term:
                # Pattern 1: Season BEFORE course line, Year AFTER
                # e.g., Line N-1: "Spring", Line N: "BIOL1020...", Line N+1: "2024"
                # Also handles: Line N-1: "Brown Spring", Line N: "BIOL0280...", Line N+1: "University 2027"
                # Also handles: Line N-1: "...Brown Spring", Line N: "BIOL0380...", Line N+1: "...University 2025"
                if pending_season and i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    # Check for plain year
                    year_match = re.match(r"^(\d{4})$", next_line)
                    if year_match:
                        term = f"{pending_season} {year_match.group(1)}"
                    else:
                        # Check for "University 2027" or "Institution 2027" pattern at start
                        inst_year_match = re.match(r"^(?:University|College|Institute)\s+(\d{4})$", next_line, re.IGNORECASE)
                        if inst_year_match:
                            term = f"{pending_season} {inst_year_match.group(1)}"
                        else:
                            # Check for "...University YYYY" or "...Institution YYYY" anywhere in line
                            # Handles: "Infectious Disease University 2025"
                            inst_year_search = re.search(r"(?:University|College|Institute)\s+(\d{4})\s*$", next_line, re.IGNORECASE)
                            if inst_year_search:
                                term = f"{pending_season} {inst_year_search.group(1)}"

                # Pattern 2: Season at end of current line, Year on next line
                if not term:
                    season_match = re.search(r"(Fall|Spring|Summer|Winter)\s*$", line, re.IGNORECASE)
                    if season_match and i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        year_match = re.match(r"^(\d{4})$", next_line)
                        if year_match:
                            term = f"{season_match.group(1).title()} {year_match.group(1)}"

            if not term:
                term = "Unknown Term"

            # Reset pending season after using it
            pending_season = None

            # Extract credits - look for number before grade
            credits = None
            pre_grade = rest_of_line[:grade_pos] if grade_pos > 0 else rest_of_line
            credits_matches = list(re.finditer(r"\b(\d+)\b", pre_grade))
            if credits_matches:
                credits = credits_matches[-1].group(1)

            # Extract title (text between course code and credits)
            title = None
            if credits_matches:
                title_end = credits_matches[-1].start()
                potential_title = pre_grade[:title_end].strip()
            else:
                potential_title = pre_grade.strip()

            potential_title = re.sub(r"^[\s\|\-:]+", "", potential_title)
            potential_title = re.sub(r"[\s\|\-:]+$", "", potential_title)
            potential_title = re.sub(r"\s+\d+\s*$", "", potential_title)
            if potential_title and 3 < len(potential_title) < 100:
                title = potential_title

            courses.append(TranscriptCourse(
                course_code=course_code,
                grade=grade,
                term_taken=term,
                credits=credits,
                title=title,
                source_page=page_num,
            ))

            i += 1

    return courses


def detect_transcript_format(pages_text: List[str]) -> str:
    """
    Detect the format/structure of the transcript.
    Returns: "tabular", "grouped_by_term", "linear", or "unknown"
    """
    combined = "\n".join(pages_text[:3])  # Check first few pages
    combined_lower = combined.lower()

    # Check for tabular format indicators
    tab_count = combined.count("\t")
    has_table_headers = any(
        all(h in combined_lower for h in ["course", "grade"])
        for _ in [1]
    )

    if tab_count > 20 or has_table_headers:
        return "tabular"

    # Check for term-grouped format
    term_headers = len(re.findall(r"(Fall|Spring|Summer|Winter)\s+\d{4}", combined, re.IGNORECASE))
    if term_headers >= 2:
        return "grouped_by_term"

    # Check for linear/continuous format
    course_matches = COURSE_CODE_RE.findall(combined)
    if len(course_matches) > 5:
        return "linear"

    return "unknown"


def extract_transcript_courses(pages_text: List[str]) -> List[TranscriptCourse]:
    """
    Extract course records from transcript PDF text.

    Handles multiple transcript formats:
    - Tabular (columns for course, title, grade, credits)
    - Grouped by term (term header followed by courses)
    - Linear (course info on single lines)

    Returns list of TranscriptCourse objects.
    """
    format_type = detect_transcript_format(pages_text)

    # For tabular format, use specialized parser
    if format_type == "tabular":
        courses = extract_tabular_transcript_courses(pages_text)
        if courses:
            return courses
        # Fall through to generic parser if tabular didn't find anything

    courses: List[TranscriptCourse] = []
    current_term: Optional[str] = None

    for page_num, page_text in enumerate(pages_text, start=1):
        lines = page_text.splitlines()
        stripped_lines = [ln.strip() for ln in lines if ln.strip()]

        for line_idx, line in enumerate(stripped_lines):
            # Check for term header
            for pattern in TERM_PATTERNS:
                term_match = pattern.search(line)
                if term_match:
                    # If line is mostly a term (likely a header)
                    if len(line) < 50 or line.lower().startswith(("term", "semester")):
                        current_term = normalize_term(term_match.group(0))
                    break

            # Look for course code (standard format like "BIOL 1100")
            code_match = COURSE_CODE_RE.search(line)
            is_mit_format = False
            if not code_match:
                # Try MIT format (like "5.111", "18.01")
                code_match = MIT_COURSE_CODE_RE.search(line)
                if code_match:
                    is_mit_format = True
            if not code_match:
                continue

            # Build the course code string based on format
            if is_mit_format:
                course_code = normalize_course_code(f"{code_match.group(1)}.{code_match.group(2)}")
            else:
                course_code = normalize_course_code(f"{code_match.group(1)} {code_match.group(2)}")

            # Look for grade on same line or nearby
            grade_match = GRADE_RE.search(line[code_match.end():])
            if not grade_match:
                # Check next line for grade
                if line_idx + 1 < len(stripped_lines):
                    grade_match = GRADE_RE.search(stripped_lines[line_idx + 1])

            if not grade_match:
                # No grade found, might not be a completed course
                continue

            grade = normalize_grade(grade_match.group(1))

            # Determine term - check line first
            term = None
            for pattern in TERM_PATTERNS:
                tm = pattern.search(line)
                if tm:
                    term = normalize_term(tm.group(0))
                    break

            # Check for split term (Season on this line, Year on next)
            if not term:
                season_match = re.search(r"(Fall|Spring|Summer|Winter)\s*$", line, re.IGNORECASE)
                if season_match and line_idx + 1 < len(stripped_lines):
                    next_line = stripped_lines[line_idx + 1]
                    year_match = re.match(r"^(\d{4})\b", next_line)
                    if year_match:
                        term = f"{season_match.group(1).title()} {year_match.group(1)}"

            # Fall back to current term from header
            if not term:
                term = current_term

            # Try context search
            if not term:
                term_from_context = extract_term_from_context(stripped_lines, line_idx)
                if term_from_context:
                    term = normalize_term(term_from_context)

            if not term:
                term = "Unknown Term"

            # Extract credits if present (look for number followed by credit indicators)
            credits = None
            credits_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:cr|credits?|hrs?|hours?|units?)", line, re.IGNORECASE)
            if credits_match:
                credits = credits_match.group(1)

            # Try to extract title (text between course code and grade)
            title = None
            title_start = code_match.end()
            title_end = grade_match.start() if grade_match else len(line)
            potential_title = line[title_start:title_end].strip()
            # Clean up title
            potential_title = re.sub(r"^\s*[-:]\s*", "", potential_title)
            potential_title = re.sub(r"\s+\d+(?:\.\d+)?\s*$", "", potential_title)  # Remove trailing credits
            if potential_title and len(potential_title) > 3 and len(potential_title) < 100:
                title = potential_title.strip()

            courses.append(TranscriptCourse(
                course_code=course_code,
                grade=grade,
                term_taken=term,
                credits=credits,
                title=title,
                source_page=page_num,
            ))

    return courses


def match_transcript_to_case_courses(
    transcript_courses: List[TranscriptCourse],
    case_course_codes: List[str],
) -> List[TranscriptCourse]:
    """
    Filter transcript courses to only those matching case documents.

    Args:
        transcript_courses: All courses extracted from transcript
        case_course_codes: Course codes from syllabus/catalog uploads for this case

    Returns:
        Filtered list of transcript courses that match case documents
    """
    # Normalize case course codes for matching
    normalized_case_codes = {normalize_course_code(c) for c in case_course_codes}

    matched = []
    for tc in transcript_courses:
        if tc.course_code in normalized_case_codes:
            matched.append(tc)

    return matched


def save_transcript_records(
    db_session: Any,
    request_id: UUID,
    courses: List[TranscriptCourse],
) -> List[UUID]:
    """
    Save extracted transcript courses to the database.

    Args:
        db_session: SQLAlchemy database session
        request_id: UUID of the case/request
        courses: List of TranscriptCourse objects to save

    Returns:
        List of created transcript_ids
    """
    from app.models import Transcript

    transcript_ids = []

    for course in courses:
        transcript = Transcript(
            request_id=request_id,
            course_code=course.course_code,
            grade=course.grade,
            term_taken=course.term_taken,
        )
        db_session.add(transcript)
        db_session.flush()  # Get the ID
        transcript_ids.append(transcript.transcript_id)

    db_session.commit()
    return transcript_ids


def process_transcript_pdf(
    pdf_path: str,
    request_id: UUID,
    db_session: Any,
    case_course_codes: Optional[List[str]] = None,
    filter_to_case: bool = True,
) -> Dict[str, Any]:
    """
    Main entry point: Extract transcript data from PDF and save to DB.

    The function links transcript records to case documents via request_id:
    1. Looks up course codes from grounded_evidence for this request_id
    2. Extracts all courses from the transcript PDF
    3. Filters to only courses matching the case (if filter_to_case=True)
    4. Saves matching courses to the transcripts table

    Args:
        pdf_path: Path to the transcript PDF file
        request_id: UUID of the case/request this transcript belongs to
        db_session: SQLAlchemy database session
        case_course_codes: Optional explicit list of course codes to match against.
                          If not provided, will be fetched from grounded_evidence.
        filter_to_case: If True, only save courses matching case documents.
                       If False, save all extracted courses.

    Returns:
        Dict with extraction results:
        {
            "status": "success" | "partial" | "failed",
            "total_extracted": int,
            "matched_count": int,
            "saved_count": int,
            "transcript_ids": List[UUID],
            "courses": List[dict],  # Saved course data
            "all_courses": List[dict],  # All extracted courses
            "case_course_codes": List[str],  # Course codes from case
            "errors": List[str],
        }
    """
    from app.extraction.pdf_text import extract_pdf_text_by_page

    result = {
        "status": "failed",
        "total_extracted": 0,
        "matched_count": 0,
        "saved_count": 0,
        "transcript_ids": [],
        "courses": [],
        "all_courses": [],
        "case_course_codes": [],
        "errors": [],
    }

    try:
        # Get case course codes from DB if not provided
        if case_course_codes is None and filter_to_case:
            try:
                case_course_codes = get_case_course_codes_from_db(request_id)
                result["case_course_codes"] = case_course_codes
            except Exception as e:
                result["errors"].append(f"Could not fetch case course codes: {e}")
                case_course_codes = []
        elif case_course_codes:
            result["case_course_codes"] = case_course_codes

        # Extract text from PDF
        pages_text = extract_pdf_text_by_page(pdf_path)

        if not pages_text or all(len(p.strip()) < 50 for p in pages_text):
            result["errors"].append("PDF appears to be image-based or empty. OCR may be required.")
            return result

        # Extract courses
        all_courses = extract_transcript_courses(pages_text)
        result["total_extracted"] = len(all_courses)
        result["all_courses"] = [
            {
                "course_code": c.course_code,
                "grade": c.grade,
                "term_taken": c.term_taken,
                "credits": c.credits,
                "title": c.title,
                "source_page": c.source_page,
            }
            for c in all_courses
        ]

        if not all_courses:
            result["errors"].append("No course records found in transcript.")
            result["status"] = "partial"
            return result

        # Filter to case-relevant courses if requested
        if filter_to_case and case_course_codes:
            courses_to_save = match_transcript_to_case_courses(all_courses, case_course_codes)
            result["matched_count"] = len(courses_to_save)

            if not courses_to_save:
                result["errors"].append(
                    f"No transcript courses match case documents. "
                    f"Extracted {len(all_courses)} courses but none matched case codes: {case_course_codes}"
                )
                result["status"] = "partial"
                return result
        else:
            courses_to_save = all_courses
            result["matched_count"] = len(all_courses)

        # Save to database
        transcript_ids = save_transcript_records(db_session, request_id, courses_to_save)

        result["status"] = "success"
        result["saved_count"] = len(transcript_ids)
        result["transcript_ids"] = transcript_ids
        result["courses"] = [
            {
                "course_code": c.course_code,
                "grade": c.grade,
                "term_taken": c.term_taken,
                "credits": c.credits,
                "title": c.title,
                "source_page": c.source_page,
            }
            for c in courses_to_save
        ]

    except Exception as e:
        result["errors"].append(f"Extraction failed: {str(e)}")
        result["status"] = "failed"

    return result
