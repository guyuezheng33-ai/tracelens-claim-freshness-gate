"""TraceLens run audit log.

Every CLI invocation appends structured JSON lines to a file-backed logger.
The logger writes only to the file: stdout stays reserved for machine-readable
command output (judge verdicts, query results, report summaries), so adding
logging can never corrupt downstream JSON consumers.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG = ROOT / "logs" / "tracelens.log"
LOGGER = logging.getLogger("tracelens.audit")


def configure_log(path: str | Path | None = None) -> Path:
    """Attach (or re-attach) a file handler and return the resolved log path."""
    target = Path(path) if path is not None else DEFAULT_LOG
    target.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False
    for old in list(LOGGER.handlers):
        LOGGER.removeHandler(old)
        old.close()
    handler = logging.FileHandler(target, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(handler)
    return target


def log_event(event: str, **fields: Any) -> None:
    """Append one JSON line: timestamp, event name, and command context."""
    payload: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "event": event,
    }
    payload.update(fields)
    LOGGER.info(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))


def read_events(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Read back a log file as structured records (for verification)."""
    target = Path(path) if path is not None else DEFAULT_LOG
    if not target.exists():
        return []
    return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
