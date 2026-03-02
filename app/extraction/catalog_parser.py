# extract_catalog_candidates + match_to_target_course

# app/extraction/catalog_parser.py
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

COURSE_CODE_RE = re.compile(r"\b([A-Z]{2,6})\s*([0-9]{3,4}[A-Z]?)\b")

# MIT-style dot notation: 10.213, 5.12, 18.03
MIT_COURSE_CODE_RE = re.compile(r"\b(\d{1,2})\.(\d{2,4}[A-Z]?)\b")

# Looser header: "MED 2150. General Pathology. 4 Credit Hours."
CATALOG_HEADER_RE = re.compile(
    r"^(?P<subj>[A-Z]{2,6})\s*(?P<num>\d{3,4}[A-Z]?)\.\s*(?P<title>.+?)\.\s*(?P<credits>\d+)\s*Credit\s*Hours?\.?\s*$"
)

# Even looser: "MED 2150. General Pathology."
CATALOG_HEADER_NO_CREDITS_RE = re.compile(
    r"^(?P<subj>[A-Z]{2,6})\s*(?P<num>\d{3,4}[A-Z]?)\.\s*(?P<title>.+?)\.?\s*$"
)

# MIT-style header: "10.213 Chemical and Biological Engineering Thermodynamics"
MIT_HEADER_RE = re.compile(
    r"^(?P<code>\d{1,2}\.\d{2,4}[A-Z]?)\s+(?P<title>[A-Z][A-Za-z,\s&\-]+?)(?:\s*,|\s*$)"
)

# Pattern to split lines at course code boundaries (for mid-line course detection)
# Matches: "MED 2150." or "BIOL 0420." patterns that start a new course entry
COURSE_SPLIT_RE = re.compile(r"(?=\b[A-Z]{2,6}\s*\d{3,4}[A-Z]?\.)")

# MIT-style split pattern: split at "10.213 " (number.number followed by space and capital letter)
MIT_SPLIT_RE = re.compile(r"(?=\b\d{1,2}\.\d{2,4}[A-Z]?\s+[A-Z])")

EXPECTED_BG_RE = re.compile(r"Expected(?: background)?:\s*(.+)$", re.IGNORECASE)


def normalize_course_code(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    code = code.strip()
    code = re.sub(r"\s+", " ", code)
    return code


def extract_catalog_structure_and_candidates(pages_text: List[str]) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Parse course blocks from a catalog-like PDF that may contain multiple courses.
    Returns (structure_type, candidates).

    Each candidate includes:
      - course_code, subject, course_number, title
      - credits_or_units (optional)
      - description (string)
      - prerequisites (optional)
      - source_pages (list[int])
    """
    combined = "\n".join(pages_text)
    has_courseish = (
        bool(COURSE_CODE_RE.search(combined)) or
        bool(MIT_COURSE_CODE_RE.search(combined)) or
        any((CATALOG_HEADER_RE.search(p) or CATALOG_HEADER_NO_CREDITS_RE.search(p)) for p in pages_text)
    )
    if not has_courseish:
        return ("program_level", [])

    candidates: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    current_pages: set[int] = set()

    def flush():
        nonlocal current, current_pages
        if current:
            current["source_pages"] = sorted(current_pages)
            # normalize empty
            for k in ("credits_or_units", "description", "prerequisites"):
                if isinstance(current.get(k), str) and not current[k].strip():
                    current[k] = None
            candidates.append(current)
        current = None
        current_pages = set()

    for pi, page in enumerate(pages_text, start=1):
        raw_lines = [ln.strip() for ln in page.splitlines() if ln.strip()]
        # Split lines at course code boundaries to handle mid-line course entries
        lines = []
        for raw_ln in raw_lines:
            # First split on traditional course codes (MED 2150.)
            split_parts = COURSE_SPLIT_RE.split(raw_ln)
            # Then split on MIT-style codes (10.213 Title)
            final_parts = []
            for part in split_parts:
                mit_split = MIT_SPLIT_RE.split(part)
                final_parts.extend(mit_split)
            for part in final_parts:
                part = part.strip()
                if part:
                    lines.append(part)
        for ln in lines:
            hm = CATALOG_HEADER_RE.match(ln)
            hm2 = CATALOG_HEADER_NO_CREDITS_RE.match(ln)
            hm_mit = MIT_HEADER_RE.match(ln)

            if hm:
                flush()
                subj = hm.group("subj")
                num = hm.group("num")
                title = hm.group("title").strip()
                credits = hm.group("credits").strip()

                current = {
                    "course_code": f"{subj} {num}",
                    "subject": subj,
                    "course_number": num,
                    "title": title,
                    "credits_or_units": credits,
                    "description": "",
                    "prerequisites": None,
                }
                current_pages.add(pi)
                continue

            if hm2:
                flush()
                subj = hm2.group("subj")
                num = hm2.group("num")
                title = hm2.group("title").strip()

                current = {
                    "course_code": f"{subj} {num}",
                    "subject": subj,
                    "course_number": num,
                    "title": title,
                    "credits_or_units": None,
                    "description": "",
                    "prerequisites": None,
                }
                current_pages.add(pi)
                continue

            # MIT-style header: "10.213 Chemical and Biological Engineering Thermodynamics"
            if hm_mit:
                flush()
                code = hm_mit.group("code")
                title = hm_mit.group("title").strip()
                # Extract subject (department number) and course number from MIT code
                mit_parts = code.split(".")
                subj = mit_parts[0] if mit_parts else code
                num = mit_parts[1] if len(mit_parts) > 1 else ""

                current = {
                    "course_code": code,
                    "subject": subj,
                    "course_number": num,
                    "title": title,
                    "credits_or_units": None,
                    "description": "",
                    "prerequisites": None,
                }
                current_pages.add(pi)
                continue

            # body lines for current course
            if current is not None:
                current_pages.add(pi)
                em = EXPECTED_BG_RE.search(ln)
                if em and not current.get("prerequisites"):
                    current["prerequisites"] = em.group(1).strip()
                else:
                    # keep it modest so we don't gobble entire page headers/footers
                    if len(ln) <= 350:
                        current["description"] = (current["description"] + " " + ln).strip()

    flush()
    return ("course_catalog_structured", candidates)


def match_candidates_to_target(
    candidates: List[Dict[str, Any]],
    target_course_code: Optional[str],
    target_title: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Deterministic matching:
      1) exact normalized course_code match
      2) fallback: title match (normalized) if provided
      3) else None
    """
    tcode = normalize_course_code(target_course_code)
    if tcode:
        for c in candidates:
            if normalize_course_code(c.get("course_code")) == tcode:
                return c, "matched_by_course_code"

    if target_title:
        t = re.sub(r"\s+", " ", target_title.strip().lower())
        for c in candidates:
            ct = (c.get("title") or "").strip().lower()
            ct = re.sub(r"\s+", " ", ct)
            if ct and ct == t:
                return c, "matched_by_title"

    return None, "no_match"