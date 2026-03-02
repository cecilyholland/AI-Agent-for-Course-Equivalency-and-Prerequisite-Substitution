"""
Package CLI entrypoint for extraction tooling.

Usage:
  python -m app.extraction run <request_id>
  python -m app.extraction validate <request_id>


"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional, List, Tuple

from sqlalchemy import create_engine, text

from app.extraction.pipeline import run_extraction


def _engine():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set.")
    return create_engine(db_url, future=True)


def _validate_request(request_id: str) -> bool:
    """
    Validates the latest extraction run for the request_id.
    Returns True if basic checks pass, else False.
    """
    engine = _engine()

    with engine.begin() as conn:
        run = conn.execute(
            text(
                """
                SELECT extraction_run_id, status, manifest_uri, created_at
                FROM extraction_runs
                WHERE request_id = :rid
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"rid": request_id},
        ).fetchone()

        if not run:
            print(f"[validate] ❌ No extraction_runs found for request_id={request_id}")
            return False

        run_id, status, manifest_uri, created_at = run
        print(f"[validate] request_id: {request_id}")
        print(f"[validate] latest_run_id: {run_id}")
        print(f"[validate] status: {status}")
        print(f"[validate] created_at: {created_at}")
        print(f"[validate] manifest_uri: {manifest_uri}")

        chunk_count = conn.execute(
            text("SELECT count(*) FROM citation_chunks WHERE extraction_run_id = :run_id"),
            {"run_id": run_id},
        ).scalar_one()

        evidence_count = conn.execute(
            text("SELECT count(*) FROM grounded_evidence WHERE extraction_run_id = :run_id"),
            {"run_id": run_id},
        ).scalar_one()

        unknown_count = conn.execute(
            text(
                """
                SELECT count(*)
                FROM grounded_evidence
                WHERE extraction_run_id = :run_id AND unknown = TRUE
                """
            ),
            {"run_id": run_id},
        ).scalar_one()

        print(f"[validate] chunks: {chunk_count}")
        print(f"[validate] evidence_items: {evidence_count} (unknown={unknown_count})")

        # Coverage: does every evidence_id have at least one citation?
        uncovered = conn.execute(
            text(
                """
                SELECT ge.evidence_id, ge.fact_type, ge.fact_key
                FROM grounded_evidence ge
                LEFT JOIN evidence_citations ec
                  ON ge.evidence_id = ec.evidence_id
                WHERE ge.extraction_run_id = :run_id
                GROUP BY ge.evidence_id, ge.fact_type, ge.fact_key
                HAVING count(ec.chunk_uuid) = 0
                ORDER BY ge.fact_type, ge.fact_key
                """
            ),
            {"run_id": run_id},
        ).fetchall()

        if uncovered:
            print("[validate] ❌ Evidence items missing citations:")
            for evid, ft, fk in uncovered:
                print(f"  - evidence_id={evid} fact_type={ft} fact_key={fk}")
            return False

        if status != "completed":
            print("[validate] ⚠️ Latest run is not completed (still validating citations/chunks though).")

        print("[validate] ✅ PASS: evidence items all have ≥ 1 citation")
        return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.extraction")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Run extraction for a request_id")
    p_run.add_argument("request_id", help="UUID of the request")

    p_val = sub.add_parser("validate", help="Validate latest extraction outputs for a request_id")
    p_val.add_argument("request_id", help="UUID of the request")

    args = parser.parse_args(argv)

    if args.cmd == "run":
        run_id = run_extraction(args.request_id)
        print(f"[extraction-cli] completed run_id={run_id}")
        return 0

    if args.cmd == "validate":
        ok = _validate_request(args.request_id)
        return 0 if ok else 2

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))