#!/usr/bin/env python3
"""Execute and preserve manual and agent packets for the three required goals."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stage2.agent import run_agent  # noqa: E402
from stage2.goals import GOALS, manual_retrieval  # noqa: E402
from stage2.io import write_json, write_jsonl  # noqa: E402
from stage2.paths import GOAL_OUTPUTS, RELEASE_MANIFEST, ensure_data_dirs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-model", action="store_true", help="Use and label deterministic fallback planning.")
    args = parser.parse_args()
    ensure_data_dirs()
    at = datetime.now(timezone.utc).replace(microsecond=0)
    run_id = at.strftime("RUN_%Y%m%dT%H%M%SZ")
    run_dir = GOAL_OUTPUTS / run_id
    manifest = json.loads(RELEASE_MANIFEST.read_text(encoding="utf-8"))
    index = {
        "run_id": run_id,
        "executed_at": at.isoformat().replace("+00:00", "Z"),
        "release_id": manifest["release_id"],
        "release_ready": manifest["release_ready"],
        "record_count": manifest["record_count"],
        "qualifying_email_count": manifest["qualifying_email_count"],
        "requested_planner_mode": "deterministic" if args.no_model else "model_with_logged_fallback",
        "goals": [],
    }
    for goal_key, exact_goal in GOALS.items():
        goal_dir = run_dir / goal_key
        manual = manual_retrieval(goal_key)
        agent_result = run_agent(exact_goal, use_model=not args.no_model, save_trace=True)
        structured = {key: value for key, value in agent_result.items() if key not in {"trace", "trace_path"}}
        write_json(goal_dir / "goal.json", {"goal_key": goal_key, "exact_goal": exact_goal})
        write_json(goal_dir / "manual_retrieval.json", manual)
        write_json(goal_dir / "structured_agent_output.json", structured)
        write_jsonl(goal_dir / "raw_trace.jsonl", agent_result["trace"])
        index["goals"].append({
            "goal_key": goal_key,
            "exact_goal": exact_goal,
            "status": agent_result["status"],
            "planner_mode": agent_result["planner_mode"],
            "trace_id": agent_result["trace_id"],
            "directory": str(goal_dir.relative_to(ROOT)),
        })
    write_json(run_dir / "index.json", index)
    write_json(GOAL_OUTPUTS / "latest.json", index)
    print(json.dumps(index, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
