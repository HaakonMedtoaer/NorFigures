"""Run event log: one JSON line per pipeline step.

Fields: run_id, claim_id, stage, status, detail, ts. The flow map (spec
section 14, docs/flowmap.html) and the README animation read this file, and
only this file (B40); it also serves debugging and tests.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

STAGES = ("load", "validate", "extract", "map", "fetch", "compare", "provenance", "report")


def new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:6]}"


class RunLog:
    """Collects events in memory and, if given a path, appends them as JSONL."""

    def __init__(self, run_id: str | None = None, path: Path | None = None):
        self.run_id = run_id or new_run_id()
        self.path = Path(path) if path else None
        self.events: list[dict] = []
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, stage: str, status: str, claim_id: str | None = None, **detail) -> None:
        if stage not in STAGES:
            raise ValueError(f"unknown stage {stage!r}")
        event = {
            "run_id": self.run_id,
            "claim_id": claim_id,
            "stage": stage,
            "status": status,
            "detail": detail,
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        }
        self.events.append(event)
        if self.path:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
