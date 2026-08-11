"""Append-only, replayable operating evidence for unattended cycles."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from stage2.io import write_json
from stage2.paths import OPERATING_LOGS, ensure_data_dirs


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def cycle_id() -> str:
    supplied = os.getenv("STAGE2_CYCLE_ID") or os.getenv("GITHUB_RUN_ID")
    attempt = os.getenv("GITHUB_RUN_ATTEMPT", "1")
    if supplied:
        return f"cycle-{supplied}-{attempt}"
    return f"cycle-local-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


@dataclass
class OperatingLog:
    cycle: str = field(default_factory=cycle_id)
    trigger: str = field(default_factory=lambda: os.getenv("STAGE2_TRIGGER", os.getenv("GITHUB_EVENT_NAME", "manual_local")))
    started_at: str = field(default_factory=now_utc)
    sequence: int = 0
    metrics: dict[str, int | float] = field(default_factory=lambda: {
        "http_attempts": 0,
        "http_succeeded": 0,
        "http_failed": 0,
        "retries": 0,
        "records_before": 0,
        "records_after": 0,
        "records_added": 0,
        "records_quarantined": 0,
        "model_calls": 0,
        "external_cost_usd": 0.0,
    })

    def __post_init__(self) -> None:
        ensure_data_dirs()
        self.path = OPERATING_LOGS / f"{self.cycle}.jsonl"
        self.summary_path = OPERATING_LOGS / f"{self.cycle}.summary.json"
        self._start_monotonic = time.monotonic()
        self.emit(
            "cycle.started",
            trigger=self.trigger,
            scheduler_owned=bool(os.getenv("GITHUB_ACTIONS")),
            github_run_id=os.getenv("GITHUB_RUN_ID", ""),
            github_run_attempt=os.getenv("GITHUB_RUN_ATTEMPT", ""),
            github_sha=os.getenv("GITHUB_SHA", ""),
            repository=os.getenv("GITHUB_REPOSITORY", ""),
        )

    def emit(self, event: str, **details: Any) -> dict[str, Any]:
        self.sequence += 1
        row = {
            "schema_version": "1.0",
            "cycle_id": self.cycle,
            "sequence": self.sequence,
            "at": now_utc(),
            "event": event,
            "details": details,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
            handle.flush()
        return row

    def count(self, key: str, increment: int = 1) -> None:
        self.metrics[key] = int(self.metrics.get(key, 0)) + increment

    def finish(self, status: str, **details: Any) -> dict[str, Any]:
        elapsed_ms = round((time.monotonic() - self._start_monotonic) * 1000)
        self.emit("cycle.finished", status=status, elapsed_ms=elapsed_ms, metrics=self.metrics, **details)
        summary = {
            "schema_version": "1.0",
            "cycle_id": self.cycle,
            "trigger": self.trigger,
            "started_at": self.started_at,
            "finished_at": now_utc(),
            "status": status,
            "elapsed_ms": elapsed_ms,
            "event_count": self.sequence,
            "metrics": self.metrics,
            "details": details,
            "raw_log": str(self.path.relative_to(self.path.parents[2])),
        }
        summary["summary_sha256"] = hashlib.sha256(
            json.dumps(summary, sort_keys=True).encode("utf-8")
        ).hexdigest()
        write_json(self.summary_path, summary)
        return summary
