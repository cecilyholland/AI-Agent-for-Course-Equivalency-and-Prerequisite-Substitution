# app/workflow_logger.py
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
_LOG_PATH: Path | None = None

# One File produced per run
# First call creates logs/run_YYYYMMDD_HHMMSS.log
def _get_log_path() -> Path:
    global _LOG_PATH
    if _LOG_PATH is None:
        log_dir = Path(os.getenv("WORKFLOW_LOG_DIR", "logs"))
        log_dir.mkdir(exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        _LOG_PATH = log_dir / f"run_{ts}.log"
    return _LOG_PATH

def log_event(*, request_id: str, status: str, actor: str, event: str, extra: dict | None = None) -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    extra = extra or {}

    line = (
        f"{ts} | request_id={request_id} | status={status} | actor={actor} | "
        f"{event} | json={json.dumps(extra, ensure_ascii=False)}"
    )

    # print to console for real-time monitoring
    print(line, flush=True)  
    with _get_log_path().open("a", encoding="utf-8") as f:
        f.write(line + "\n")