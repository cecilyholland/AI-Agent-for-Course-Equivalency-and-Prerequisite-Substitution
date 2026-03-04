# choose best chunks for each fact

# app/extraction/citation_selector.py
from __future__ import annotations

import re
from typing import Dict, List, Optional


DEFAULT_FACT_KEYWORDS: Dict[str, List[str]] = {
    "course_code": ["course", "catalog", "code"],
    "title": ["title"],
    "credits_or_units": ["credit", "credits", "hours", "units"],
    "description": ["description", "objective", "about this course", "overview"],
    "prerequisites": ["prerequisite", "prerequisites", "expected background", "enrollment policy"],
}


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def pick_best_chunk_uuids_for_fact(
    fact_key: str,
    fact_value: Optional[str],
    pages_text: List[str],
    page_chunk_uuids: List[List[str]],
    max_pages_to_scan: int = 3,
) -> List[str]:
    """
    Choose citations for a fact by scanning for keywords on the first few pages.
    Returns chunk UUIDs from pages where keywords appear.
    Fallback: first page chunks.

    This is lightweight and deterministic; it does not require searching inside full chunk text.
    """
    if not page_chunk_uuids:
        return []

    keywords = DEFAULT_FACT_KEYWORDS.get(fact_key, [])
    # include fact_value tokens if useful (e.g., MED 2150)
    if fact_value and len(fact_value) <= 40:
        keywords = keywords + [fact_value]

    keywords_n = [_normalize(k) for k in keywords if k.strip()]

    picked: List[str] = []
    pages_to_scan = min(len(pages_text), max_pages_to_scan)

    for i in range(pages_to_scan):
        hay = _normalize(pages_text[i] or "")
        if any(k in hay for k in keywords_n):
            picked.extend(page_chunk_uuids[i])

    if picked:
        # de-dupe while preserving order
        seen = set()
        out: List[str] = []
        for x in picked:
            if x not in seen:
                out.append(x)
                seen.add(x)
        return out

    # fallback
    return page_chunk_uuids[0]
