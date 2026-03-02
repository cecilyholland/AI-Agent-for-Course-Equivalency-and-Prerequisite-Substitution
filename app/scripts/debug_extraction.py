"""
Verbose extraction debug script
Shows all extracted fields, chunks, and grounding
"""
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from app.extraction.pdf_text import ensure_searchable_text
from app.extraction.chunking import chunk_page_text, Chunk
from app.extraction.syllabus_parser import extract_syllabus_facts
from app.extraction.catalog_parser import extract_catalog_structure_and_candidates, match_candidates_to_target


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def classify_document(filename: str) -> str:
    return "syllabus" if "syllabus" in filename.lower() else "catalog"


def run_debug_extraction():
    # Test files from CASE01
    test_docs = [
        {
            "doc_id": "doc-001-syllabus",
            "filename": "MED_2150_General_Pathology_Syllabus_CASE01.pdf",
            "path": "Data/Raw/StudentTestCases/CASE01/MED_2150_General_Pathology_Syllabus_CASE01.pdf"
        },
        {
            "doc_id": "doc-002-catalog",
            "filename": "brown_MED2045_CASE01.pdf",
            "path": "Data/Raw/StudentTestCases/CASE01/brown_MED2045_CASE01.pdf"
        }
    ]

    print("=" * 80)
    print("EXTRACTION DEBUG RUN")
    print("=" * 80)

    run_id = f"debug-run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    request_id = "CASE01-debug"

    manifest = {
        "request_id": request_id,
        "extraction_run_id": run_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "documents": [],
        "evidence": [],
        "chunks": [],
    }

    print(f"\n[MANIFEST METADATA]")
    print(f"  run_id:      {run_id}")
    print(f"  request_id:  {request_id}")
    print(f"  started_at:  {manifest['started_at']}")

    # Track target info from syllabus for catalog matching
    target_course_codes = set()
    target_titles = set()

    # Sort: syllabus first
    sorted_docs = sorted(test_docs, key=lambda d: 0 if classify_document(d["filename"]) == "syllabus" else 1)

    for doc in sorted_docs:
        doc_id = doc["doc_id"]
        filename = doc["filename"]
        pdf_path = doc["path"]
        doc_type = classify_document(filename)

        print(f"\n{'=' * 80}")
        print(f"[DOCUMENT: {filename}]")
        print(f"  doc_id:   {doc_id}")
        print(f"  doc_type: {doc_type}")
        print(f"  path:     {pdf_path}")
        print("=" * 80)

        # Extract text
        print(f"\n[TEXT EXTRACTION]")
        pages_text, used_ocr, ocr_path, warning = ensure_searchable_text(
            pdf_path=pdf_path,
            output_dir="Data/Processed/manifests",
            prefer_ocr=True,
        )
        print(f"  pages:    {len(pages_text)}")
        print(f"  used_ocr: {used_ocr}")
        if warning:
            print(f"  warning:  {warning}")
        for i, pt in enumerate(pages_text[:3], 1):
            print(f"  page {i}: {len(pt)} chars")

        # Chunking
        print(f"\n[CITATION CHUNKS]")
        all_chunks = []
        chunk_idx = 0
        for page_num, pt in enumerate(pages_text, start=1):
            page_chunks = chunk_page_text(pt, page_num=page_num)
            for ch in page_chunks:
                chunk_id = f"chunk-{chunk_idx:03d}"
                chunk_sha = sha256_text(f"{doc_id}|{run_id}|{ch.page_num}|{ch.span_start}|{ch.span_end}")
                all_chunks.append({
                    "chunk_id": chunk_id,
                    "chunk_sha": chunk_sha,
                    "page_num": ch.page_num,
                    "span": f"{ch.span_start}-{ch.span_end}",
                    "snippet": ch.snippet_text[:200],
                    "full_text": ch.full_text,
                })
                chunk_idx += 1

        print(f"  total_chunks: {len(all_chunks)}")
        print(f"\n  {'ID':<12} {'Page':<6} {'Span':<12} {'Text (first 100 chars)'}")
        print(f"  {'-'*12} {'-'*6} {'-'*12} {'-'*50}")
        for ch in all_chunks[:15]:
            text_preview = ch["snippet"][:100].replace("\n", " ")
            print(f"  {ch['chunk_id']:<12} {ch['page_num']:<6} {ch['span']:<12} {text_preview}")
        if len(all_chunks) > 15:
            print(f"  ... and {len(all_chunks) - 15} more chunks")

        manifest["chunks"].extend(all_chunks)

        # Field extraction
        print(f"\n[EXTRACTED FIELDS]")
        evidence_items = []

        if doc_type == "syllabus":
            facts = extract_syllabus_facts(pages_text)

            if facts.get("course_code"):
                target_course_codes.add(facts["course_code"])
            if facts.get("title"):
                target_titles.add(facts["title"])

            print(f"  Syllabus Facts:")
            for key, val in facts.items():
                unknown = val is None
                status = "UNKNOWN" if unknown else "FOUND"
                val_preview = str(val)[:80] if val else "null"
                print(f"    {key:<20}: [{status}] {val_preview}")

                evidence_items.append({
                    "fact_type": "syllabus_course",
                    "fact_key": key,
                    "fact_value": val,
                    "unknown": unknown,
                    "grounded_to": ["chunk-000"] if not unknown else ["chunk-000"],
                })

        else:  # catalog
            structure_type, candidates = extract_catalog_structure_and_candidates(pages_text)

            print(f"  Catalog Structure: {structure_type}")
            print(f"  Candidates Found:  {len(candidates)}")

            evidence_items.append({
                "fact_type": "catalog_document",
                "fact_key": "structure_type",
                "fact_value": structure_type,
                "unknown": False,
                "grounded_to": ["chunk-000"],
            })

            # Show some candidates
            if candidates:
                print(f"\n  Sample Candidates (first 5):")
                for i, cand in enumerate(candidates[:5]):
                    code = cand.get("course_code", "?")
                    title = cand.get("title", "?")[:50]
                    print(f"    [{i}] {code}: {title}")

            # Match to target
            target_code = next(iter(target_course_codes), None)
            target_title = next(iter(target_titles), None)
            print(f"\n  Matching to target: code={target_code}, title={target_title}")

            best, reason = match_candidates_to_target(candidates, target_code, target_title)

            if best:
                print(f"\n  MATCH FOUND ({reason}):")
                for k, v in best.items():
                    v_str = str(v)[:100] if v else "null"
                    print(f"    {k:<20}: {v_str}")

                evidence_items.append({
                    "fact_type": "catalog_course_match",
                    "fact_key": f"match::{best.get('course_code', 'unknown')}",
                    "fact_value": best.get("course_code"),
                    "fact_json": best,
                    "unknown": False,
                    "grounded_to": [f"chunk-{i:03d}" for i in range(min(3, len(all_chunks)))],
                })
            else:
                print(f"\n  NO MATCH FOUND (reason: {reason})")
                evidence_items.append({
                    "fact_type": "catalog_course_match",
                    "fact_key": f"match::{target_code or 'unknown'}",
                    "fact_value": None,
                    "unknown": True,
                    "grounded_to": ["chunk-000"],
                })

        # Field-level grounding summary
        print(f"\n[FIELD-LEVEL GROUNDING]")
        print(f"  {'Fact Type':<25} {'Fact Key':<25} {'Grounded To':<30} {'Status'}")
        print(f"  {'-'*25} {'-'*25} {'-'*30} {'-'*10}")
        for ev in evidence_items:
            status = "UNKNOWN" if ev["unknown"] else "GROUNDED"
            chunks_str = ", ".join(ev["grounded_to"][:3])
            if len(ev["grounded_to"]) > 3:
                chunks_str += f"... (+{len(ev['grounded_to'])-3})"
            print(f"  {ev['fact_type']:<25} {ev['fact_key']:<25} {chunks_str:<30} {status}")

        manifest["evidence"].extend(evidence_items)
        manifest["documents"].append({
            "doc_id": doc_id,
            "filename": filename,
            "doc_type": doc_type,
            "page_count": len(pages_text),
            "chunk_count": len(all_chunks),
            "evidence_count": len(evidence_items),
        })

    # Final summary
    print(f"\n{'=' * 80}")
    print("[EXTRACTION SUMMARY]")
    print("=" * 80)
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    print(f"  run_id:           {manifest['extraction_run_id']}")
    print(f"  request_id:       {manifest['request_id']}")
    print(f"  started_at:       {manifest['started_at']}")
    print(f"  finished_at:      {manifest['finished_at']}")
    print(f"  documents:        {len(manifest['documents'])}")
    print(f"  total_chunks:     {len(manifest['chunks'])}")
    print(f"  total_evidence:   {len(manifest['evidence'])}")

    print(f"\n[PARSEDDATA.CSV EQUIVALENT]")
    print(f"  (Would write one row per evidence item)")
    for ev in manifest["evidence"]:
        val = str(ev.get("fact_value", ""))[:50]
        print(f"    {ev['fact_type']}/{ev['fact_key']}: {val}")

    print(f"\n[MANIFEST SHA256]")
    manifest_json = json.dumps(manifest, indent=2, default=str)
    manifest_sha = hashlib.sha256(manifest_json.encode()).hexdigest()
    print(f"  sha256: {manifest_sha}")

    print(f"\n{'=' * 80}")
    print("DEBUG RUN COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    run_debug_extraction()
