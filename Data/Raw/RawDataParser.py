#!/usr/bin/env python3
"""
UTC Course Catalog PDF Parser
Inputs:  Data/Raw/Inputs/*.pdf
Outputs: Data/Processed/ParsedData.csv
         Data/Processed/CitationChunks.csv
         Data/Processed/extraction_manifest.json

Design goals:
- Deterministic extraction
- Clear provenance + grounding artifacts for citations
- Safe defaults (never mutates Raw inputs)
"""
import pdfplumber
import argparse
import csv
import hashlib
import json
import os
import platform
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple


# -----------------------------
# Regex patterns tuned to UTC layout
# -----------------------------
COURSE_HEADER_RE = re.compile(
    r"^(?P<subject>[A-Z]{2,5})\s+(?P<number>\d{4})(?P<suffix>[A-Z]{0,2}|R|L)?\s+-\s+(?P<title>.+)$"
)

# Current “canonical” credits line for the Course Descriptions PDFs:
# (3) Credit Hours
CREDITS_RE = re.compile(
    r"^\((?P<credits>[\d.]+(?:\s*-\s*[\d.]+)?)\)\s+Credit Hours$",
    re.IGNORECASE
)

GENED_IN_TITLE_RE = re.compile(
    r"\((?P<codes>[A-Z]{1,2}(?:\s+or\s+[A-Z]{1,2})?(?:\s*,\s*[A-Z]{1,2})*)\)\s*$"
)

# Common noise patterns (headers/footers) you can expand over time:
TIMESTAMP_LINE_RE = re.compile(
    r"^\d{1,2}/\d{1,2}/\d{2},\s+\d{1,2}:\d{2}\s+(AM|PM)\s+Course Descriptions",
    re.IGNORECASE
)
PAGE_NAV_RE = re.compile(r"^Page:\s+\d+\s+\|", re.IGNORECASE)


# -----------------------------
# Utilities
# -----------------------------
def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def norm(s: str) -> str:
    """Normalize whitespace without changing content meaning."""
    return re.sub(r"\s+", " ", s).strip()


def sha_id(*parts: str, length: int = 32) -> str:
    """Stable short ID for chunks/records."""
    h = hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()
    return h[:length]


def sha256_file(path: str, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def try_git_commit_hash(repo_root: str) -> str:
    """Best-effort git commit hash; returns empty string if not a git repo."""
    try:
        out = subprocess.check_output(
            ["git", "-C", repo_root, "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True
        ).strip()
        return out
    except Exception:
        return ""


def credit_range(raw: str) -> Tuple[Optional[float], Optional[float]]:
    raw = raw.replace(" ", "").strip()
    if not raw:
        return None, None
    if "-" in raw:
        a, b = raw.split("-", 1)
        return float(a), float(b)
    return float(raw), float(raw)


def clean_line(ln: str) -> str:
    """Remove empty lines + typical headers/footers without harming content."""
    ln = ln.strip()
    if not ln:
        return ""

    # UTC catalog header/footer patterns (adjust as needed)
    if ln.startswith("2025-2026 Undergraduate Catalog"):
        return ""
    if "https://catalog.utc.edu" in ln:
        return ""
    if TIMESTAMP_LINE_RE.match(ln):
        return ""
    if ln.startswith("Contract All Courses"):
        return ""
    if PAGE_NAV_RE.match(ln):
        return ""

    return ln


def extract_prereqs(text: str) -> Tuple[str, str, str]:
    """Extract prereq/coreq strings as raw text (keep unparsed for now)."""
    prereq = coreq = pre_or_coreq = ""

    m = re.search(r"Prerequisites:\s*(.+?)(?:\.\s|$)", text, flags=re.IGNORECASE)
    if m:
        prereq = norm(m.group(1))

    m = re.search(r"Corequisites:\s*(.+?)(?:\.\s|$)", text, flags=re.IGNORECASE)
    if m:
        coreq = norm(m.group(1))

    m = re.search(r"Pre or Corequisites:\s*(.+?)(?:\.\s|$)", text, flags=re.IGNORECASE)
    if m:
        pre_or_coreq = norm(m.group(1))

    return prereq, coreq, pre_or_coreq


def extract_gened_category(text: str) -> str:
    m = re.search(r"General Education Category:\s*(.+)", text)
    return m.group(1).strip() if m else ""


def extract_term_offered(text: str) -> str:
    m = re.search(
        r"(Every semester\.|Fall semester\.|Spring semester\.|Fall and Spring semesters\.|"
        r"Fall or Spring semester\.|Every other Fall semester\.|On demand\.)",
        text
    )
    return m.group(1).rstrip(".") if m else ""


def extract_flags(text: str) -> str:
    """Simple derived flags you can expand later."""
    flags = []
    if "Laboratory/studio course fee will be assessed" in text:
        flags.append("lab_fee")
    if "Satisfactory/No Credit" in text:
        flags.append("s_nc")
    if "Only open to" in text or "Restricted to" in text:
        flags.append("restriction")
    if "Credit not allowed" in text:
        flags.append("credit_restriction")
    return ",".join(flags)


# -----------------------------
# Data models
# -----------------------------
@dataclass
class ParsedCourse:
    row: Dict[str, object]


@dataclass
class CitationChunk:
    row: Dict[str, object]


# -----------------------------
# Core parsing
# -----------------------------
def parse_pdf(pdf_path: str, warnings: List[str]) -> Tuple[List[ParsedCourse], List[CitationChunk]]:
    """
    Parse one PDF into:
      - ParsedData rows (courses)
      - CitationChunks rows (grounding)
    """
    courses: List[ParsedCourse] = []
    chunks: List[CitationChunk] = []

    source_doc = os.path.basename(pdf_path)

    # Collect (page_number, line_text)
    lines: List[Tuple[int, str]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for pageno, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for raw_ln in text.splitlines():
                ln = clean_line(raw_ln)
                if ln:
                    lines.append((pageno, ln))

    # Split into course blocks
    blocks: List[List[Tuple[int, str]]] = []
    current: List[Tuple[int, str]] = []

    for pageno, ln in lines:
        if COURSE_HEADER_RE.match(ln):
            if current:
                blocks.append(current)
            current = [(pageno, ln)]
        else:
            if current:
                current.append((pageno, ln))
    if current:
        blocks.append(current)

    if not blocks:
        warnings.append(f"[{source_doc}] No course blocks detected. Check PDF format or noise filters.")
        return courses, chunks

    # Credits patterns (try in order; keep your canonical format first)
    CREDITS_PATTERNS = [
        CREDITS_RE,
        re.compile(r'^\s*Credit\s*Hours?\s*:\s*(?P<credits>.+?)\s*$', re.IGNORECASE),
        re.compile(r'^\s*Credits?\s*:\s*(?P<credits>.+?)\s*$', re.IGNORECASE),
        # Examples: "3 credit hours", "3 credits", "3 hours"
        re.compile(r'^\s*(?P<credits>\d+(?:\.\d+)?)\s*(?:credit\s*hours?|credits?|hours?)\b.*$', re.IGNORECASE),
        # Examples: "3 (3)" or "3-0-3"
        re.compile(r'^\s*(?P<credits>\d+)\s*\(\s*\d+\s*\)\s*$', re.IGNORECASE),
        re.compile(r'^\s*(?P<credits>\d+)\s*-\s*\d+\s*-\s*\d+\s*$', re.IGNORECASE),
    ]

    # OPTIONAL debug (set True to print credit scan lines for missing-credit courses)
    DEBUG_CREDITS = False
    CREDITS_SCAN_LINES = 12  # only scan top of block to avoid false matches later

    # Parse each block
    for block in blocks:
        header_page, header = block[0]
        m = COURSE_HEADER_RE.match(header)
        if not m:
            warnings.append(f"[{source_doc}] Skipped block with non-matching header on page {header_page}: {header}")
            continue

        subject = m.group("subject")
        number = m.group("number")
        suffix = m.group("suffix") or ""
        title_full = m.group("title").strip()

        # Optional GenEd code at end of title
        gened_codes_in_title = ""
        title = title_full
        m2 = GENED_IN_TITLE_RE.search(title_full)
        if m2:
            gened_codes_in_title = norm(m2.group("codes"))
            title = title_full[:m2.start()].rstrip()

        # -------------------------
        # Credits parsing
        # -------------------------
        credits_min: Optional[float] = None
        credits_max: Optional[float] = None
        credits_raw = ""
        credit_idx: Optional[int] = None
        credit_page = header_page
        credit_line = ""

        scan_slice = block[1:1 + CREDITS_SCAN_LINES]

        for idx, (pageno, ln) in enumerate(scan_slice, start=1):
            for cre in CREDITS_PATTERNS:
                # Use search() so patterns can match even if there's leading text/formatting oddities
                cm = cre.search(ln)
                if cm:
                    credits_raw = cm.group("credits").strip()
                    credits_min, credits_max = credit_range(credits_raw)
                    credit_idx = idx
                    credit_page = pageno
                    credit_line = ln
                    break
            if credit_idx is not None:
                break

        if credit_idx is None:
            warnings.append(
                f"[{source_doc}] Missing credits line for {subject} {number}{suffix} near page {header_page}"
            )
            if DEBUG_CREDITS:
                print("\n--- CREDITS DEBUG (missing) ---")
                print(f"{source_doc} | {subject} {number}{suffix} | header page {header_page}")
                for p, l in scan_slice:
                    print(f"p{p}: {l}")
                print("--- END ---\n")

        # -------------------------
        # Description parsing
        # -------------------------
        # Description = everything after credits (or after header if missing credits)
        desc_items = block[credit_idx + 1:] if credit_idx is not None else block[1:]
        desc_pages = sorted(set(p for p, _ in desc_items)) or [header_page]
        desc_text_raw = " ".join(ln for _, ln in desc_items)
        desc_text = norm(desc_text_raw)

        prereq, coreq, pre_or_coreq = extract_prereqs(desc_text)
        gened_category_text = extract_gened_category(desc_text)
        term_offered = extract_term_offered(desc_text)
        flags = extract_flags(desc_text)

        course_code = f"{subject} {number}{suffix}"

        # -------------------------
        # Citation chunks
        # -------------------------
        header_chunk_sha_id = sha_id(source_doc, str(header_page), course_code, "header", header)
        chunks.append(CitationChunk({
            "chunk_sha_id": header_chunk_sha_id,
            "course_code": course_code,
            "source_doc": source_doc,
            "page": header_page,
            "chunk_type": "header",
            "chunk_text": header
        }))

        credit_chunk_sha_id = ""
        if credit_line:
            credit_chunk_sha_id = sha_id(source_doc, str(credit_page), course_code, "credits", credit_line)
            chunks.append(CitationChunk({
                "chunk_sha_id": credit_chunk_sha_id,
                "course_code": course_code,
                "source_doc": source_doc,
                "page": credit_page,
                "chunk_type": "credits",
                "chunk_text": credit_line
            }))

        # Store description as one chunk (simple + reliable); can be split later if needed.
        desc_chunk_sha_id = sha_id(source_doc, ",".join(map(str, desc_pages)), course_code, "description", desc_text[:200])
        chunks.append(CitationChunk({
            "chunk_sha_id": desc_chunk_sha_id,
            "course_code": course_code,
            "source_doc": source_doc,
            "page": desc_pages[0],
            "chunk_type": "description",
            "chunk_text": desc_text
        }))

        chunk_sha_ids = [header_chunk_sha_id]
        if credit_chunk_sha_id:
            chunk_sha_ids.append(credit_chunk_sha_id)
        chunk_sha_ids.append(desc_chunk_sha_id)

        # -------------------------
        # Parsed course row
        # -------------------------
        courses.append(ParsedCourse({
            "course_code": course_code,
            "subject": subject,
            "number": number,
            "suffix": suffix,
            "title": title,
            "gened_codes_in_title": gened_codes_in_title,
            "credits_min": credits_min,
            "credits_max": credits_max,
            "term_offered": term_offered,
            "gened_category_text": gened_category_text,
            "prerequisites": prereq,
            "corequisites": coreq,
            "pre_or_corequisites": pre_or_coreq,
            "flags": flags,
            "description": desc_text,
            "source_doc": source_doc,
            "source_pages": ",".join(map(str, sorted(set([header_page] + desc_pages)))),
            "chunk_sha_ids": "|".join(chunk_sha_ids),
        }))

    return courses, chunks


# -----------------------------
# CSV + manifest writers
# -----------------------------
def write_csv(path: str, rows: List[Dict[str, object]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not rows:
        # still write header? depends on preference; here we hard-fail to surface issues
        raise ValueError(f"No rows to write for {path}")

    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def write_extraction_manifest(
    manifest_path: str,
    repo_root: str,
    script_path: str,
    input_dir: str,
    input_files: List[str],
    outputs: Dict[str, str],
    metrics: Dict[str, object],
    warnings: List[str],
    errors: List[str],
) -> None:
    # Input fingerprints
    input_items = []
    for fpath in sorted(input_files):
        stat = os.stat(fpath)
        input_items.append({
            "path": os.path.relpath(fpath, repo_root),
            "filename": os.path.basename(fpath),
            "bytes": stat.st_size,
            "modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
            "sha256": sha256_file(fpath),
        })

    # Output fingerprints
    output_items: Dict[str, Dict[str, object]] = {}
    for k, out_path in outputs.items():
        abs_out = out_path if os.path.isabs(out_path) else os.path.join(repo_root, out_path)
        if os.path.exists(abs_out):
            stat = os.stat(abs_out)
            output_items[k] = {
                "path": os.path.relpath(abs_out, repo_root),
                "bytes": stat.st_size,
                "modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
                "sha256": sha256_file(abs_out),
            }
        else:
            output_items[k] = {
                "path": os.path.relpath(abs_out, repo_root),
                "missing": True,
            }

    manifest = {
        "run": {
            "run_id": sha_id(utc_now_iso(), platform.node(), length=16),
            "started_utc": utc_now_iso(),
            "host": platform.node(),
            "python": platform.python_version(),
            "os": f"{platform.system()} {platform.release()}",
            "git_commit": try_git_commit_hash(repo_root),
            "script_path": os.path.relpath(script_path, repo_root),
        },
        "inputs": {
            "input_dir": os.path.relpath(input_dir, repo_root),
            "files": input_items,
        },
        "outputs": output_items,
        "metrics": metrics,
        "warnings": warnings,
        "errors": errors,
    }

    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


# -----------------------------
# Entry point
# -----------------------------
def find_repo_root_from_script(script_path: str) -> str:
    """
    Assumes script is located at: <repo_root>/Data/Raw/RawDataParser.py
    So repo_root is 3 levels up from this file.
    """
    return os.path.abspath(os.path.join(os.path.dirname(script_path), "..", ".."))


def main():
    ap = argparse.ArgumentParser(description="Parse UTC course description PDFs into CSV + citation chunks + manifest.")
    ap.add_argument("--input_dir", default=None, help="Defaults to Data/Raw/Inputs relative to repo root")
    ap.add_argument("--processed_dir", default=None, help="Defaults to Data/Processed relative to repo root")
    ap.add_argument("--courses_csv", default="ParsedData.csv", help="Filename inside processed_dir")
    ap.add_argument("--chunks_csv", default="CitationChunks.csv", help="Filename inside processed_dir")
    ap.add_argument("--manifest_json", default="extraction_manifest.json", help="Filename inside processed_dir")
    args = ap.parse_args()

    script_path = os.path.abspath(__file__)
    repo_root = find_repo_root_from_script(script_path)

    input_dir = args.input_dir or os.path.join(repo_root, "Data", "Raw", "Inputs")
    processed_dir = args.processed_dir or os.path.join(repo_root, "Data", "Processed")

    courses_out = os.path.join(processed_dir, args.courses_csv)
    chunks_out = os.path.join(processed_dir, args.chunks_csv)
    manifest_out = os.path.join(processed_dir, args.manifest_json)

    warnings: List[str] = []
    errors: List[str] = []

    if not os.path.isdir(input_dir):
        raise SystemExit(f"Input dir not found: {input_dir}")

    pdf_files = [
        os.path.join(input_dir, f)
        for f in os.listdir(input_dir)
        if f.lower().endswith(".pdf")
    ]
    if not pdf_files:
        raise SystemExit(f"No PDFs found in {input_dir}")

    all_courses: List[ParsedCourse] = []
    all_chunks: List[CitationChunk] = []

    for pdf in sorted(pdf_files):
        try:
            courses, chunks = parse_pdf(pdf, warnings)
            all_courses.extend(courses)
            all_chunks.extend(chunks)
        except Exception as e:
            errors.append(f"[{os.path.basename(pdf)}] {type(e).__name__}: {e}")

    # Flatten rows
    course_rows = [c.row for c in all_courses]
    chunk_rows = [c.row for c in all_chunks]

    # Write outputs if we have something usable
    if course_rows:
        write_csv(courses_out, course_rows)
    else:
        errors.append("No course rows parsed. ParsedData.csv not written.")

    if chunk_rows:
        write_csv(chunks_out, chunk_rows)
    else:
        errors.append("No chunk rows parsed. CitationChunks.csv not written.")

    metrics = {
        "pdf_count": len(pdf_files),
        "courses_rows": len(course_rows),
        "chunks_rows": len(chunk_rows),
    }

    write_extraction_manifest(
        manifest_path=manifest_out,
        repo_root=repo_root,
        script_path=script_path,
        input_dir=input_dir,
        input_files=pdf_files,
        outputs={
            "courses_csv": courses_out,
            "chunks_csv": chunks_out,
            "manifest_json": manifest_out,
        },
        metrics=metrics,
        warnings=warnings,
        errors=errors,
    )

    print("Extraction complete")
    print(f"  PDFs processed: {metrics['pdf_count']}")
    print(f"  Courses parsed: {metrics['courses_rows']} -> {courses_out}")
    print(f"  Chunks created: {metrics['chunks_rows']} -> {chunks_out}")
    print(f"  Manifest: {manifest_out}")

    if warnings:
        print(f"  Warnings: {len(warnings)} (see manifest)")
    if errors:
        print(f"  Errors: {len(errors)} (see manifest)")


if __name__ == "__main__":
    main()
