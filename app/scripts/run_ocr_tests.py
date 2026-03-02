#!/usr/bin/env python3
"""
run_ocr_tests.py

Tests OCR extraction on all PDFs in Data/Raw/StudentTestCases.
Verifies Ghostscript + pytesseract + pdf2image are working correctly.

Usage:
    python -m app.scripts.run_ocr_tests

Requirements for OCR:
    - Ghostscript: C:\\Program Files\\gs\\gs10.06.0\\bin\\gswin64c.exe
    - Poppler: Download from https://github.com/oschwartz10612/poppler-windows/releases
      Extract to C:\\tools\\poppler and add C:\\tools\\poppler\\Library\\bin to PATH
    - pytesseract + tesseract-ocr
"""

from __future__ import annotations

import os
import sys
import time
import shutil
from pathlib import Path
from typing import List, Tuple, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Common paths for Ghostscript and Poppler on Windows
GS_PATHS = [
    r"C:\Program Files\gs\gs10.06.0\bin",
    r"C:\Program Files\gs\gs10.05.0\bin",
    r"C:\Program Files (x86)\gs\gs10.06.0\bin",
]
POPPLER_PATHS = [
    r"C:\tools\poppler\Library\bin",
    r"C:\tools\poppler\bin",
    r"C:\Program Files\poppler\Library\bin",
    r"C:\Program Files\poppler\bin",
    r"C:\poppler\Library\bin",
]

def find_poppler_path() -> Optional[str]:
    """Find poppler bin directory, including versioned subdirectories."""
    import glob

    # Check explicit paths first
    for path in POPPLER_PATHS:
        if os.path.exists(path) and os.path.isfile(os.path.join(path, "pdftoppm.exe")):
            return path

    # Search for versioned directories (e.g., poppler-25.12.0)
    search_patterns = [
        r"C:\tools\poppler\poppler-*\Library\bin",
        r"C:\tools\poppler\poppler-*\bin",
        r"C:\Program Files\poppler\poppler-*\Library\bin",
    ]
    for pattern in search_patterns:
        matches = glob.glob(pattern)
        for match in matches:
            if os.path.isfile(os.path.join(match, "pdftoppm.exe")):
                return match

    # Check if already in PATH
    if shutil.which("pdftoppm"):
        return "in PATH"

    return None

def setup_paths() -> Tuple[Optional[str], Optional[str]]:
    """Find and add Ghostscript and Poppler to PATH."""
    gs_found = None
    poppler_found = None

    # Add Ghostscript
    for gs_path in GS_PATHS:
        if os.path.exists(gs_path):
            os.environ["PATH"] = gs_path + os.pathsep + os.environ.get("PATH", "")
            gs_found = gs_path
            break

    # Add Poppler (using enhanced search)
    poppler_found = find_poppler_path()
    if poppler_found and poppler_found != "in PATH":
        os.environ["PATH"] = poppler_found + os.pathsep + os.environ.get("PATH", "")

    return gs_found, poppler_found

from app.extraction.pdf_text import (
    extract_pdf_text_by_page,
    looks_like_image_only,
    ocr_pdf_with_pytesseract,
)


def find_test_pdfs() -> List[Path]:
    """Find all PDFs in StudentTestCases directory."""
    test_dir = PROJECT_ROOT / "Data" / "Raw" / "StudentTestCases"
    if not test_dir.exists():
        print(f"ERROR: Test directory not found: {test_dir}")
        return []
    return sorted(test_dir.rglob("*.pdf"))


def test_pdf_extraction(pdf_path: Path) -> Tuple[bool, str, int, int, bool]:
    """
    Test extraction on a single PDF.

    Returns: (success, message, page_count, char_count, used_ocr)
    """
    try:
        # First try pdfplumber
        pages = extract_pdf_text_by_page(str(pdf_path))
        page_count = len(pages)
        total_chars = sum(len(p) for p in pages)

        needs_ocr = looks_like_image_only(pages)
        used_ocr = False

        if needs_ocr:
            # Try OCR
            try:
                pages = ocr_pdf_with_pytesseract(str(pdf_path))
                total_chars = sum(len(p) for p in pages)
                used_ocr = True

                if looks_like_image_only(pages):
                    return False, "OCR ran but extracted minimal text", page_count, total_chars, True

            except Exception as ocr_err:
                return False, f"OCR failed: {ocr_err}", page_count, 0, False

        if total_chars < 100:
            return False, f"Extracted only {total_chars} chars", page_count, total_chars, used_ocr

        return True, "OK", page_count, total_chars, used_ocr

    except Exception as e:
        return False, f"Extraction error: {e}", 0, 0, False


def main() -> int:
    print("=" * 70)
    print("OCR Test Suite - Testing Ghostscript + pdf2image + pytesseract")
    print("=" * 70)

    # Setup paths
    gs_found, poppler_found = setup_paths()

    print(f"\nGhostscript: {gs_found or 'NOT FOUND'}")
    print(f"Poppler: {poppler_found or 'NOT FOUND'}")

    if not gs_found:
        print("\nWARNING: Ghostscript not found. Some PDF operations may fail.")

    if not poppler_found:
        print("\n" + "!" * 70)
        print("WARNING: Poppler not found!")
        print("OCR requires poppler to convert PDFs to images.")
        print("\nTo install poppler on Windows:")
        print("  1. Download: https://github.com/oschwartz10612/poppler-windows/releases")
        print("  2. Extract to: C:\\tools\\poppler")
        print("  3. Add C:\\tools\\poppler\\Library\\bin to PATH")
        print("     Or re-run this script after extraction.")
        print("!" * 70)

    # Find test PDFs
    pdfs = find_test_pdfs()
    print(f"\nFound {len(pdfs)} PDF files to test\n")

    if not pdfs:
        return 1

    results = []
    passed = 0
    failed = 0
    ocr_count = 0

    for pdf_path in pdfs:
        relative_path = pdf_path.relative_to(PROJECT_ROOT / "Data" / "Raw" / "StudentTestCases")
        case_name = relative_path.parts[0]

        start = time.time()
        success, msg, pages, chars, used_ocr = test_pdf_extraction(pdf_path)
        elapsed = time.time() - start

        status = "PASS" if success else "FAIL"
        ocr_tag = " [OCR]" if used_ocr else ""

        print(f"[{status}] {case_name}/{pdf_path.name}")
        print(f"       Pages: {pages}, Chars: {chars:,}, Time: {elapsed:.2f}s{ocr_tag}")

        if not success:
            print(f"       Error: {msg}")

        results.append({
            "case": case_name,
            "file": pdf_path.name,
            "success": success,
            "message": msg,
            "pages": pages,
            "chars": chars,
            "used_ocr": used_ocr,
            "time": elapsed,
        })

        if success:
            passed += 1
        else:
            failed += 1

        if used_ocr:
            ocr_count += 1

        print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total PDFs tested: {len(pdfs)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Required OCR: {ocr_count}")
    print()

    # Group by case
    cases = {}
    for r in results:
        case = r["case"]
        if case not in cases:
            cases[case] = {"pass": 0, "fail": 0}
        if r["success"]:
            cases[case]["pass"] += 1
        else:
            cases[case]["fail"] += 1

    print("Results by case:")
    for case in sorted(cases.keys()):
        status = "OK" if cases[case]["fail"] == 0 else "ISSUES"
        print(f"  {case}: {cases[case]['pass']} passed, {cases[case]['fail']} failed [{status}]")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
