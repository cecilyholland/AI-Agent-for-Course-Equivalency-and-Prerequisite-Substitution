# app/workflow_logger.py
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Optional

_LOG_PATH: Optional[Path] = None

# One File produced per run
# First call creates logs/run_YYYYMMDD_HHMMSS.log
def _get_log_path() -> Path:
    global _LOG_PATH
    if _LOG_PATH is None:
        log_dir = Path(__file__).resolve().parent / "logs" 
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        _LOG_PATH = log_dir / f"run_{ts}.log"
    return _LOG_PATH

def log_event(event: str, request_id: Optional[str]=None, actor: str="system", status: Optional[str] = None, step: Optional[str]=None, extra: Optional[dict[str, Any]]=None) -> None:
    record = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, "request_id": request_id, "actor": actor, "status": status, "step": step, "extra": extra or {},
              }
    try:
        with _get_log_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
            #line = json.dumps(record, default=str)
            #print(line, flush=True)
    except Exception: pass

