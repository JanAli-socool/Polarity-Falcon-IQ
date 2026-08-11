"""Repository paths shared by Stage 2 commands."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "stage2"
STATE = DATA / "state"
RAW = DATA / "raw"
QUARANTINE = DATA / "quarantine"
OPERATING_LOGS = DATA / "operating_logs"
GOAL_LOGS = DATA / "goal_logs"
GOAL_OUTPUTS = DATA / "goal_outputs"
CANONICAL_RECORDS = STATE / "records.jsonl"
CANDIDATES = STATE / "candidates.jsonl"
SOURCE_OBSERVATIONS = STATE / "source_observations.jsonl"
FINAL = ROOT / "data" / "final"
RELEASE_CSV = FINAL / "family_office_contacts.csv"
RELEASE_JSONL = FINAL / "family_office_contacts.jsonl"
RELEASE_MANIFEST = FINAL / "release_manifest.json"


def ensure_data_dirs() -> None:
    for path in (STATE, RAW, QUARANTINE, OPERATING_LOGS, GOAL_LOGS, GOAL_OUTPUTS, FINAL):
        path.mkdir(parents=True, exist_ok=True)
