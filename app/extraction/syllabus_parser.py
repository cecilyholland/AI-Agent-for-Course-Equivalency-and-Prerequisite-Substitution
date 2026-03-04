# extract_syllabus_facts

# app/extraction/syllabus_parser.py
from __future__ import annotations

import re
from typing import Dict, Optional

COURSE_CODE_RE = re.compile(r"\b([A-Z]{2,6})\s*([0-9]{3,4}[A-Z]?)\b")
MIT_DOT_RE = re.compile(r"\b(\d{1,2}\.\d{3,4})\b")  # e.g., 10.213


def extract_syllabus_facts(pages_text: list[str]) -> Dict[str, Optional[str]]:
    """
    Extract minimal syllabus facts:
      - course_code (e.g., MED 2150 or 10.213)
      - title
      - credits_or_units
      - description
      - prerequisites

    Tolerant: missing values return None.
    """
    text_all = "\n".join(pages_text)

    facts: Dict[str, Optional[str]] = {
        "course_code": None,
        "subject": None,
        "course_number": None,
        "title": None,
        "credits_or_units": None,
        "description": None,
        "prerequisites": None,
    }

    # course code like MED 2150
    m = COURSE_CODE_RE.search(text_all)
    if m:
        subj, num = m.group(1), m.group(2)
        facts["course_code"] = f"{subj} {num}"
        facts["subject"] = subj
        facts["course_number"] = num

    # MIT style 10.213
    if not facts["course_code"]:
        mm = MIT_DOT_RE.search(text_all)
        if mm:
            facts["course_code"] = mm.group(1)

    # Title heuristic: first meaningful line of page 1 minus leading code
    first_lines = [ln.strip() for ln in (pages_text[0].splitlines() if pages_text else []) if ln.strip()]
    if first_lines:
        line0 = first_lines[0]
        cleaned = re.sub(r"^[A-Z]{2,6}\s*\d{3,4}[A-Z]?\s*[–—-]\s*", "", line0).strip()
        cleaned = re.sub(r"^\d{1,2}\.\d{3,4}\s*[–—-]\s*", "", cleaned).strip()
        if cleaned and len(cleaned) <= 140:
            facts["title"] = cleaned

    # Credits/units
    credit_line = re.search(r"\b(\d+)\s*Credit Hour", text_all, re.IGNORECASE)
    if credit_line:
        facts["credits_or_units"] = credit_line.group(1)

    units_line = re.search(r"\bUnits?\b\s*[:\-]?\s*(\d+)", text_all, re.IGNORECASE)
    if units_line and not facts["credits_or_units"]:
        facts["credits_or_units"] = units_line.group(1)

    # Description section
    desc = None
    dm = re.search(
        r"(Course Description|About This Course|Course Objective and Description)\s*(.+)",
        text_all,
        re.IGNORECASE | re.DOTALL,
    )
    if dm:
        tail = dm.group(2)
        # stop at next likely heading (very rough)
        tail = re.split(r"\n[A-Z][A-Za-z /&]{3,}\n", tail)[0]
        desc = tail.strip()
    else:
        # fallback: first paragraph-ish block after header on page 1
        if pages_text:
            p1 = pages_text[0].strip()
            paras = [p.strip() for p in re.split(r"\n\s*\n", p1) if p.strip()]
            if len(paras) >= 2:
                desc = paras[1][:1200].strip()

    facts["description"] = desc

    # Prereqs
    pm = re.search(
        r"(Prerequisites|Expected Background / Prerequisites|Enrollment Policy|Expected Background)\s*(.+)",
        text_all,
        re.IGNORECASE | re.DOTALL,
    )
    if pm:
        tail = pm.group(2)
        tail = re.split(r"\n[A-Z][A-Za-z /&]{3,}\n", tail)[0]
        facts["prerequisites"] = tail.strip()

    return facts