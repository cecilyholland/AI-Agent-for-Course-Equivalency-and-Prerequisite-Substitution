# pdfplumber extract, image-only heuristics (later OCR)

# app/extraction/pdf_text.py
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import List, Optional


def extract_pdf_text_by_page(pdf_path: str) -> List[str]:
    """
    Extract text per page using pdfplumber.

    Notes:
    - This will return empty strings for image-only PDFs (scans).
    - OCR fallback handled elsewhere.
    """
    import pdfplumber  # local import to reduce editor import sensitivity

    pages: List[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            t = re.sub(r"[ \t]+", " ", t)
            pages.append(t.strip())
    return pages


def looks_like_image_only(pages_text: List[str], min_chars_per_page: int = 40) -> bool:
    """
    Heuristic: if >=80% pages have fewer than min_chars_per_page characters, treat as image-only.
    """
    if not pages_text:
        return True
    low = sum(1 for t in pages_text if len(t) < min_chars_per_page)
    return (low / max(len(pages_text), 1)) >= 0.8


def ocr_to_searchable_pdf(input_pdf: str, output_pdf: str) -> None:
    """
    Create a searchable PDF via ocrmypdf (must be on PATH).
    """
    try:
        subprocess.run(
            ["ocrmypdf", "--skip-text", "--force-ocr", input_pdf, output_pdf],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            "OCR is required for this PDF, but 'ocrmypdf' is not installed/available on PATH. "
            "Install it (pip install ocrmypdf) and ensure dependencies (tesseract) are installed, "
            "or defer OCR for now."
        ) from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ocrmypdf failed: {e.stderr[:500]}") from e


def ensure_searchable_text(
    pdf_path: str,
    output_dir: str,
    prefer_ocr: bool = True,
) -> tuple[list[str], bool, Optional[str], Optional[str]]:
    """
    Returns: (pages_text, used_ocr, ocr_output_pdf, warning)

    - If image-only and prefer_ocr=True, attempts OCR. If OCR unavailable, returns empty-ish pages with warning.
    """
    pages_text = extract_pdf_text_by_page(pdf_path)
    used_ocr = False
    ocr_out: Optional[str] = None
    warning: Optional[str] = None

    if prefer_ocr and looks_like_image_only(pages_text):
        used_ocr = True
        out = str(Path(output_dir) / f"ocr_{Path(pdf_path).stem}.pdf")
        try:
            ocr_to_searchable_pdf(pdf_path, out)
            ocr_out = out
            pages_text = extract_pdf_text_by_page(out)
        except Exception as e:
            # tolerant behavior: proceed without OCR, but warn
            warning = f"OCR required but unavailable/failed for {pdf_path}: {e}"
            used_ocr = False
            ocr_out = None
            # keep the original extracted text (likely empty), do not crash

    return pages_text, used_ocr, ocr_out, warning