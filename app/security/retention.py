# app/security/retention.py
# Retention enforcement for audit log files in app/logs/
# Every log line written by workflow_logger.py contains an "expires_at" field.
# This module scans those files, removes expired lines, and deletes empty files.
# Default retention: 1825 days (5 years, FERPA-aligned)
# PDF retention is planned — pending expires_at column addition to
# the documents table. See retention policy documentation.
# Usage:
#   from app.security.retention import run_retention_sweep
#   result = run_retention_sweep()

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from sqlalchemy import create_engine, text
DATABASE_URL: str = os.environ.get("DATABASE_URL", "")

logger = logging.getLogger(__name__)

LOG_DIR: Path = Path(__file__).resolve().parent.parent / "logs"


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class RetentionSweepResult:
    log_lines_removed: int = 0
    log_files_deleted: int = 0
    log_files_scanned: int = 0

    pdfs_deleted: int = 0
    pdfs_skipped: int = 0
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core sweep
# ---------------------------------------------------------------------------

def purge_expired_log_lines(
    log_dir: Path = LOG_DIR,
    dry_run: bool = False,
) -> RetentionSweepResult:
    """
    Scan every .log file in log_dir.
    Remove lines whose expires_at field is in the past.
    Delete the file entirely if all lines are expired.

    Each line is a JSON object written by workflow_logger.log_event().
    Lines missing expires_at are kept (fail-safe).

    Returns a RetentionSweepResult with counts.
    """
    result = RetentionSweepResult()
    now = datetime.now(tz=timezone.utc)

    if not log_dir.exists():
        logger.info("Log directory %s does not exist — nothing to purge.", log_dir)
        return result

    for log_file in sorted(log_dir.glob("*.log")):
        result.log_files_scanned += 1
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                raw_lines = f.readlines()

            surviving = []
            removed = 0

            for line in raw_lines:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                    expires_at_str = record.get("expires_at")
                    if expires_at_str:
                        expires_at = datetime.fromisoformat(expires_at_str)
                        if expires_at < now:
                            removed += 1
                            continue
                except (json.JSONDecodeError, ValueError):
                    # Malformed line — keep it, don't silently lose data
                    pass
                surviving.append(stripped)

            if removed == 0:
                continue

            if dry_run:
                logger.info(
                    "[DRY RUN] %s — would remove %d expired line(s), %d would remain",
                    log_file.name, removed, len(surviving),
                )
                result.log_lines_removed += removed
                continue

            if not surviving:
                log_file.unlink()
                result.log_files_deleted += 1
                result.log_lines_removed += removed
                logger.info(
                    "Deleted %s — all %d line(s) expired",
                    log_file.name, removed,
                )
            else:
                with open(log_file, "w", encoding="utf-8") as f:
                    f.write("\n".join(surviving) + "\n")
                result.log_lines_removed += removed
                logger.info(
                    "Purged %d expired line(s) from %s — %d line(s) remain",
                    removed, log_file.name, len(surviving),
                )

        except Exception as exc:
            msg = f"Error processing {log_file.name}: {exc}"
            logger.error(msg)
            result.errors.append(msg)

    return result


def purge_expired_pdfs(dry_run: bool = False) -> tuple[int, int]:
    if not DATABASE_URL:
        logger.warning("DATABASE_URL not set — skipping PDF purge.")
        return 0, 0
    now_str = datetime.now(tz=timezone.utc).isoformat()
    query = """
        SELECT doc_id, storage_uri, expires_at
        FROM documents
        WHERE expires_at IS NOT NULL
          AND expires_at < :now
          AND storage_uri IS NOT NULL
          AND storage_uri != ''
    """
    deleted = 0
    skipped = 0
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            rows = conn.execute(text(query), {"now": now_str}).fetchall()
        for doc_id, storage_uri, expires_at in rows:
            file_path = Path(storage_uri)
            if not file_path.exists():
                logger.warning("PDF for doc %s not found on disk: %s", doc_id, storage_uri)
                skipped += 1
                _null_storage_uri(engine, str(doc_id))
                continue
            if dry_run:
                logger.info("[DRY RUN] Would delete PDF doc_id=%s path=%s (expired %s)", doc_id, storage_uri, expires_at)
                deleted += 1
                continue
            try:
                file_path.unlink()
                _null_storage_uri(engine, str(doc_id))
                logger.info("Deleted PDF doc_id=%s path=%s", doc_id, storage_uri)
                deleted += 1
            except OSError as exc:
                logger.error("Failed to delete PDF doc_id=%s: %s", doc_id, exc)
                skipped += 1
    except Exception as exc:
        logger.error("PDF purge query failed: %s", exc)
    return deleted, skipped


def _null_storage_uri(engine, doc_id: str) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE documents SET storage_uri = NULL WHERE doc_id = :id"),
                {"id": doc_id},
            )
    except Exception as exc:
        logger.error("Failed to null storage_uri for doc %s: %s", doc_id, exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_retention_sweep(
    dry_run: bool = False,
    log_dir: Path = LOG_DIR,
) -> RetentionSweepResult:
    """
    Run the retention sweep on audit log files.

    Example::

        from app.security.retention import run_retention_sweep
        result = run_retention_sweep()
        print(f"Removed {result.log_lines_removed} expired log lines.")
    """
    logger.info("Starting retention sweep (dry_run=%s) on %s", dry_run, log_dir)
    result = purge_expired_log_lines(log_dir=log_dir, dry_run=dry_run)

    try:
        result.pdfs_deleted, result.pdfs_skipped = purge_expired_pdfs(dry_run=dry_run)
    except Exception as exc:
        msg = f"PDF purge failed: {exc}"
        logger.error(msg)
        result.errors.append(msg)

    if result.errors:
        logger.warning("Sweep finished with %d error(s).", len(result.errors))
    else:
        logger.info(
            "Sweep complete — scanned: %d files | lines removed: %d | files deleted: %d",
            result.log_files_scanned,
            result.log_lines_removed,
            result.log_files_deleted,
        )
    return result


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    parser = argparse.ArgumentParser(description="Audit log retention sweep.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview what would be deleted without actually deleting.",
    )
    args = parser.parse_args()

    result = run_retention_sweep(dry_run=args.dry_run)

    print(f"\nRetention sweep {'(DRY RUN) ' if args.dry_run else ''}complete:")
    print(f"  Files scanned  : {result.log_files_scanned}")
    print(f"  Lines removed  : {result.log_lines_removed}")
    print(f"  Files deleted  : {result.log_files_deleted}")
    print(f"  PDFs deleted      : {result.pdfs_deleted}")
    print(f"  PDFs skipped      : {result.pdfs_skipped}")
    if result.errors:
        print(f"  Errors         : {len(result.errors)}")
        for e in result.errors:
            print(f"    - {e}")