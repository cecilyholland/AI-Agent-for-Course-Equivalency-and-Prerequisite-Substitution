# chunk_page_text, Chunk dataclass

# app/extraction/chunking.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Chunk:
    page_num: int
    span_start: int
    span_end: int
    snippet_text: str
    full_text: str


def chunk_page_text(page_text: str, page_num: int, max_chars: int = 900) -> List[Chunk]:
    """
    Deterministic chunking:
    - Prefer paragraph-ish chunks (split on blank lines).
    - Pack paragraphs into ~max_chars.
    - Fallback to fixed windows if no paragraph structure.
    """
    if not page_text:
        return []

    paras = [p.strip() for p in re.split(r"\n\s*\n", page_text) if p.strip()]
    chunks: List[Chunk] = []

    if len(paras) <= 1:
        t = page_text
        i = 0
        while i < len(t):
            j = min(i + max_chars, len(t))
            full = t[i:j]
            chunks.append(
                Chunk(
                    page_num=page_num,
                    span_start=i,
                    span_end=j,
                    snippet_text=full[:200],
                    full_text=full,
                )
            )
            i = j
        return chunks

    buf = ""
    buf_start = 0
    running_idx = 0

    for p in paras:
        if not buf:
            buf_start = running_idx

        if len(buf) + len(p) + 2 <= max_chars:
            buf = (buf + "\n\n" + p).strip()
        else:
            end = buf_start + len(buf)
            chunks.append(
                Chunk(
                    page_num=page_num,
                    span_start=buf_start,
                    span_end=end,
                    snippet_text=buf[:200],
                    full_text=buf,
                )
            )
            buf = p
            buf_start = running_idx

        running_idx += len(p) + 2

    if buf:
        end = buf_start + len(buf)
        chunks.append(
            Chunk(
                page_num=page_num,
                span_start=buf_start,
                span_end=end,
                snippet_text=buf[:200],
                full_text=buf,
            )
        )

    return chunks