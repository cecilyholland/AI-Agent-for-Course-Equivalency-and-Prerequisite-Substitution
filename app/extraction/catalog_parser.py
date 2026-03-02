# extract_catalog_candidates + match_to_target_course

# app/extraction/catalog_parser.py
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple, Set

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


# ==============================================================================
# Smart Catalog Search - TOC detection and targeted page extraction
# ==============================================================================

# TOC entry pattern: "Section Name ... page_number" or "Section Name page_number"
TOC_ENTRY_RE = re.compile(
    r"^(?P<section>.+?)\s*[\.·…]+\s*(?P<page>\d{1,4})\s*$"
)
TOC_ENTRY_SIMPLE_RE = re.compile(
    r"^(?P<section>[A-Z][A-Za-z\s,&\-\(\)]+)\s+(?P<page>\d{1,4})\s*$"
)

# Department/subject mappings for course code to section matching
SUBJECT_TO_SECTION_KEYWORDS = {
    # Brown University
    "MED": ["medicine", "medical", "biology and medicine", "division of biology"],
    "BIOL": ["biology", "biological"],
    "PHP": ["public health"],
    "NEUR": ["neuroscience"],
    "CHEM": ["chemistry"],
    "PHYS": ["physics"],
    "ECON": ["economics"],
    "CSCI": ["computer science"],
    "MATH": ["mathematics"],
    # Georgia Tech
    "APPH": ["applied physiology", "health", "physiology"],
    "EAS": ["earth", "environmental", "atmospheric"],
    "CS": ["computer science"],
    "ECE": ["electrical", "computer engineering"],
    # MIT (Course numbers)
    "10": ["chemical engineering"],
    "5": ["chemistry"],
    "6": ["electrical engineering", "computer science"],
    "7": ["biology"],
    "8": ["physics"],
    "18": ["mathematics"],
}


def detect_toc_pages(pages_text: List[str], max_pages: int = 20) -> List[int]:
    """
    Detect which pages contain a Table of Contents.
    Returns list of 1-indexed page numbers.
    """
    toc_pages = []

    for i, text in enumerate(pages_text[:max_pages], start=1):
        text_lower = text.lower()
        # Look for TOC indicators
        has_toc_header = (
            "table of contents" in text_lower or
            "contents" in text_lower[:200]  # "Contents" near top of page
        )
        # Count dotted lines (common in TOC)
        dotted_count = len(re.findall(r"\.{3,}|…+", text))
        # Count page number patterns at end of lines
        page_num_count = len(TOC_ENTRY_RE.findall(text))

        if has_toc_header or (dotted_count > 5 and page_num_count > 3):
            toc_pages.append(i)

    return toc_pages


def parse_toc_entries(toc_text: str) -> Dict[str, int]:
    """
    Parse TOC text into section name -> page number mapping.
    Returns dict like {"Biology": 44, "Chemistry": 298, ...}
    """
    entries = {}

    for line in toc_text.splitlines():
        line = line.strip()
        if not line:
            continue

        # Try dotted pattern first
        m = TOC_ENTRY_RE.match(line)
        if m:
            section = m.group("section").strip()
            page = int(m.group("page"))
            if section and page > 0:
                entries[section] = page
            continue

        # Try simple pattern (Section Name 123)
        m2 = TOC_ENTRY_SIMPLE_RE.match(line)
        if m2:
            section = m2.group("section").strip()
            page = int(m2.group("page"))
            if section and page > 0 and len(section) > 3:
                entries[section] = page

    return entries


def find_section_for_subject(subject: str, toc_entries: Dict[str, int]) -> Optional[Tuple[str, int]]:
    """
    Given a subject code (e.g., "MED", "BIOL", "10"), find the matching TOC section.
    Returns (section_name, start_page) or None.
    """
    subject_upper = subject.upper()
    keywords = SUBJECT_TO_SECTION_KEYWORDS.get(subject_upper, [])

    # Also search for the subject code itself
    keywords = keywords + [subject_upper.lower()]

    for section, page in toc_entries.items():
        section_lower = section.lower()
        for kw in keywords:
            if kw in section_lower:
                return (section, page)

    return None


def detect_page_offset(pages_text: List[str], max_check: int = 20) -> int:
    """
    Detect offset between printed page numbers and PDF page numbers.
    Looks for patterns like "42 The Division" at top of page.
    Returns offset to ADD to TOC page numbers to get PDF page numbers.
    """
    import re
    for pdf_page_idx in range(min(max_check, len(pages_text))):
        text = pages_text[pdf_page_idx]
        # Look for page number at start of page (e.g., "42 The Division")
        m = re.match(r"^\s*(\d{1,3})\s+[A-Z]", text)
        if m:
            printed_page = int(m.group(1))
            pdf_page = pdf_page_idx + 1
            offset = pdf_page - printed_page
            if offset != 0:
                return offset
    return 0


def get_page_range_for_section(
    section: str,
    start_page: int,
    toc_entries: Dict[str, int],
    total_pages: int,
    buffer: int = 5,
    page_offset: int = 0
) -> Tuple[int, int]:
    """
    Given a section start page, find a reasonable end page.
    Uses the next TOC entry's page as a guide.
    Returns (start_page, end_page) as 1-indexed PDF page numbers.

    Args:
        page_offset: Offset to add to TOC page numbers to get PDF page numbers.
                    (e.g., if TOC says page 42 but PDF page is 48, offset = 6)
    """
    # Find entries sorted by page
    sorted_entries = sorted(toc_entries.items(), key=lambda x: x[1])

    # Find the next section after ours
    end_page = total_pages
    found_current = False
    for sec_name, sec_page in sorted_entries:
        if found_current:
            # Apply offset and buffer
            end_page = sec_page + page_offset + buffer
            break
        if sec_page == start_page:
            found_current = True

    # Apply offset to start page
    start = max(1, start_page + page_offset - 2)
    end = min(total_pages, end_page + page_offset)

    # Ensure we have a reasonable range (at least 20 pages for course sections)
    if end - start < 20:
        end = min(total_pages, start + 30)

    return (start, end)


def search_pages_for_course_code(
    pages_text: List[str],
    target_code: str,
    context_pages: int = 2
) -> List[int]:
    """
    Direct search for course code in page text.
    Returns list of 1-indexed page numbers where course appears.
    Includes surrounding pages for context.
    """
    matching_pages: Set[int] = set()

    # Normalize target code for flexible matching
    target_patterns = [
        target_code,  # exact: "MED 2150"
        target_code.replace(" ", ""),  # no space: "MED2150"
        re.sub(r"\s+", r"\\s*", re.escape(target_code)),  # flexible space
    ]

    for i, text in enumerate(pages_text, start=1):
        for pattern in target_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                # Add this page and context pages
                for p in range(max(1, i - context_pages), min(len(pages_text), i + context_pages) + 1):
                    matching_pages.add(p)
                break

    return sorted(matching_pages)


def smart_page_selection(
    pages_text: List[str],
    target_course_code: Optional[str],
    target_subject: Optional[str] = None,
) -> Tuple[List[int], str, bool]:
    """
    Intelligently select which pages to parse for a target course.

    Strategy:
    1. Direct search - if course code found in text, return those pages
    2. TOC search - if TOC found, find relevant section pages
    3. Fallback - return all pages

    Returns: (list of 1-indexed page numbers, strategy_used, needs_ocr)
    """
    total_pages = len(pages_text)

    if not target_course_code:
        return (list(range(1, total_pages + 1)), "no_target_full_scan", False)

    # Extract subject from course code if not provided
    if not target_subject:
        # Traditional: "MED 2150" -> "MED"
        m = COURSE_CODE_RE.search(target_course_code)
        if m:
            target_subject = m.group(1)
        else:
            # MIT style: "10.213" -> "10"
            m2 = MIT_COURSE_CODE_RE.search(target_course_code)
            if m2:
                target_subject = m2.group(1)

    # Strategy 1: Direct text search
    direct_pages = search_pages_for_course_code(pages_text, target_course_code)
    if direct_pages:
        return (direct_pages, "direct_text_search", False)

    # Strategy 2: TOC-based search
    toc_page_nums = detect_toc_pages(pages_text)
    if toc_page_nums and target_subject:
        # Combine TOC pages text
        toc_text = "\n".join(pages_text[p - 1] for p in toc_page_nums)
        toc_entries = parse_toc_entries(toc_text)

        if toc_entries:
            section_match = find_section_for_subject(target_subject, toc_entries)
            if section_match:
                section_name, start_page = section_match
                # Detect page offset from early text pages
                page_offset = detect_page_offset(pages_text)
                start, end = get_page_range_for_section(
                    section_name, start_page, toc_entries, total_pages,
                    page_offset=page_offset
                )
                selected_pages = list(range(start, end + 1))
                # Check if selected pages are image-only (need OCR)
                needs_ocr = all(len(pages_text[p-1]) < 50 for p in selected_pages if p <= total_pages)
                return (selected_pages, f"toc_section:{section_name}", needs_ocr)

    # Strategy 3: For catalogs without TOC, check if alphabetically organized
    # Look for index/navigation pages in first 100 pages
    if target_subject:
        for i in range(min(100, total_pages)):
            text = pages_text[i]
            # Look for alphabetical index pattern with our subject
            if target_subject in text and len(text) > 200:
                # Check if this looks like an index page
                if re.search(r"[A-Z]\s+[A-Z]\s+[A-Z]", text):  # Letter spacing pattern
                    # This might be near the subject listings
                    return (list(range(max(1, i - 5), min(total_pages, i + 50))),
                            "alphabetical_search", True)

    # Strategy 4: Fallback to full scan
    # Check if most pages are image-only
    image_pages = sum(1 for t in pages_text if len(t) < 50)
    needs_ocr = (image_pages / max(total_pages, 1)) > 0.5
    return (list(range(1, total_pages + 1)), "fallback_full_scan", needs_ocr)


def ocr_selected_pages(
    pdf_path: str,
    page_numbers: List[int],
    poppler_path: Optional[str] = None,
) -> Dict[int, str]:
    """
    OCR specific pages from a PDF.
    Returns dict of page_number -> extracted_text.

    Requires: pytesseract, pdf2image, poppler
    """
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError as e:
        raise RuntimeError(f"OCR dependencies not installed: {e}")

    import os
    import re

    # Get poppler path
    if not poppler_path:
        poppler_path = os.environ.get(
            "POPPLER_PATH",
            r"C:\tools\poppler\poppler-25.12.0\Library\bin"
        )
    from pathlib import Path
    if not Path(poppler_path).exists():
        poppler_path = None

    results: Dict[int, str] = {}

    for page_num in page_numbers:
        try:
            # Convert single page
            images = convert_from_path(
                pdf_path,
                dpi=200,
                first_page=page_num,
                last_page=page_num,
                poppler_path=poppler_path
            )
            if images:
                text = pytesseract.image_to_string(images[0], lang="eng")
                text = re.sub(r"[ \t]+", " ", text)
                results[page_num] = text.strip()
        except Exception as e:
            results[page_num] = f"[OCR ERROR: {e}]"

    return results


def search_catalog_by_ocr_batches(
    pdf_path: str,
    total_pages: int,
    target_code: str,
    batch_size: int = 50,
    max_batches: int = 30,
    poppler_path: Optional[str] = None,
) -> Tuple[List[int], Dict[int, str]]:
    """
    Search for a course code in an image-based catalog by OCR-ing in batches.
    Uses a smart search pattern: start from middle, then expand outward.

    Returns: (pages_containing_target, ocr_results_dict)
    """
    import re

    # Build search pattern
    target_patterns = [
        re.escape(target_code),
        re.escape(target_code.replace(" ", "")),
    ]
    pattern = re.compile("|".join(target_patterns), re.IGNORECASE)

    # Extract subject for section detection
    subj_match = COURSE_CODE_RE.search(target_code)
    if subj_match:
        subject = subj_match.group(1)
        # Also search for subject prefix (e.g., "APPH 6" for APPH courses)
        subject_pattern = re.compile(rf"\b{re.escape(subject)}\s*\d", re.IGNORECASE)
    else:
        subject = None
        subject_pattern = None

    all_ocr: Dict[int, str] = {}
    found_pages: List[int] = []
    subject_pages: List[int] = []

    # Start from middle, then expand
    mid = total_pages // 2
    batch_starts = []
    for i in range(max_batches):
        # Alternate above and below middle
        if i % 2 == 0:
            start = mid + (i // 2) * batch_size
        else:
            start = mid - ((i // 2) + 1) * batch_size

        if 1 <= start <= total_pages:
            batch_starts.append(start)

    for batch_idx, start in enumerate(batch_starts):
        end = min(start + batch_size - 1, total_pages)
        pages = list(range(start, end + 1))

        ocr_results = ocr_selected_pages(pdf_path, pages, poppler_path)
        all_ocr.update(ocr_results)

        for page_num, text in ocr_results.items():
            # Check for exact target
            if pattern.search(text):
                found_pages.append(page_num)
            # Check for subject section
            elif subject_pattern and subject_pattern.search(text):
                subject_pages.append(page_num)

        # If we found the target, get surrounding pages and return
        if found_pages:
            # Also get a few pages before/after
            min_p = max(1, min(found_pages) - 3)
            max_p = min(total_pages, max(found_pages) + 3)
            extra_pages = [p for p in range(min_p, max_p + 1) if p not in all_ocr]
            if extra_pages:
                extra_ocr = ocr_selected_pages(pdf_path, extra_pages, poppler_path)
                all_ocr.update(extra_ocr)
            return (found_pages, all_ocr)

        # If we found subject section, expand search there
        if subject_pages and batch_idx > 3:
            # Focus on subject area
            subj_min = max(1, min(subject_pages) - 10)
            subj_max = min(total_pages, max(subject_pages) + 10)
            subj_range = [p for p in range(subj_min, subj_max + 1) if p not in all_ocr]
            if subj_range:
                subj_ocr = ocr_selected_pages(pdf_path, subj_range, poppler_path)
                all_ocr.update(subj_ocr)

                for page_num, text in subj_ocr.items():
                    if pattern.search(text):
                        found_pages.append(page_num)

                if found_pages:
                    return (found_pages, all_ocr)

    # Return subject pages if no exact match
    if subject_pages:
        return (subject_pages, all_ocr)

    return ([], all_ocr)


def extract_from_selected_pages(
    pages_text: List[str],
    selected_pages: List[int],
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Run extraction on only the selected pages.
    Preserves original page numbers in source_pages.
    """
    # Build subset with original page numbers
    subset_with_pages = [(pages_text[p - 1], p) for p in selected_pages if 0 < p <= len(pages_text)]

    if not subset_with_pages:
        return ("no_pages_selected", [])

    # Extract using the standard function but track original page numbers
    combined = "\n".join(text for text, _ in subset_with_pages)
    has_courseish = (
        bool(COURSE_CODE_RE.search(combined)) or
        bool(MIT_COURSE_CODE_RE.search(combined)) or
        bool(CATALOG_HEADER_RE.search(combined)) or
        bool(CATALOG_HEADER_NO_CREDITS_RE.search(combined))
    )
    if not has_courseish:
        return ("program_level", [])

    candidates: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    current_pages: Set[int] = set()

    def flush():
        nonlocal current, current_pages
        if current:
            current["source_pages"] = sorted(current_pages)
            for k in ("credits_or_units", "description", "prerequisites"):
                if isinstance(current.get(k), str) and not current[k].strip():
                    current[k] = None
            candidates.append(current)
        current = None
        current_pages = set()

    for page_text, original_page_num in subset_with_pages:
        raw_lines = [ln.strip() for ln in page_text.splitlines() if ln.strip()]
        lines = []
        for raw_ln in raw_lines:
            split_parts = COURSE_SPLIT_RE.split(raw_ln)
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
                current = {
                    "course_code": f"{subj} {num}",
                    "subject": subj,
                    "course_number": num,
                    "title": hm.group("title").strip(),
                    "credits_or_units": hm.group("credits").strip(),
                    "description": "",
                    "prerequisites": None,
                }
                current_pages.add(original_page_num)
                continue

            if hm2:
                flush()
                subj = hm2.group("subj")
                num = hm2.group("num")
                current = {
                    "course_code": f"{subj} {num}",
                    "subject": subj,
                    "course_number": num,
                    "title": hm2.group("title").strip(),
                    "credits_or_units": None,
                    "description": "",
                    "prerequisites": None,
                }
                current_pages.add(original_page_num)
                continue

            if hm_mit:
                flush()
                code = hm_mit.group("code")
                mit_parts = code.split(".")
                current = {
                    "course_code": code,
                    "subject": mit_parts[0] if mit_parts else code,
                    "course_number": mit_parts[1] if len(mit_parts) > 1 else "",
                    "title": hm_mit.group("title").strip(),
                    "credits_or_units": None,
                    "description": "",
                    "prerequisites": None,
                }
                current_pages.add(original_page_num)
                continue

            if current is not None:
                current_pages.add(original_page_num)
                em = EXPECTED_BG_RE.search(ln)
                if em and not current.get("prerequisites"):
                    current["prerequisites"] = em.group(1).strip()
                elif len(ln) <= 350:
                    current["description"] = (current["description"] + " " + ln).strip()

    flush()
    return ("course_catalog_structured", candidates)