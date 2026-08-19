"""Reconcile pipeline-generated CSV/JSONL/manifest without touching Stage 2 DB."""
import json
import csv
import hashlib
from pathlib import Path

CSV_PATH = Path("data/final/family_office_contacts.csv")
JSONL_PATH = Path("data/final/family_office_contacts.jsonl")
MANIFEST_PATH = Path("data/final/release_manifest.json")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    # Load CSV
    csv_rows = []
    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        csv_rows = list(reader)
    
    # Load JSONL
    jsonl_rows = []
    with JSONL_PATH.open(encoding="utf-8") as f:
        for line in f:
            jsonl_rows.append(json.loads(line))
    
    # Verify counts match
    assert len(csv_rows) == len(jsonl_rows), f"Row count mismatch: CSV={len(csv_rows)}, JSONL={len(jsonl_rows)}"
    
    # Verify record IDs match
    csv_ids = [r.get("Record ID") for r in csv_rows]
    jsonl_ids = [r.get("record_id") or r.get("Record ID") for r in jsonl_rows]
    assert csv_ids == jsonl_ids, "Record IDs or ordering disagree"
    
    # Verify Release IDs
    csv_release_ids = {r.get("Release ID") for r in csv_rows}
    jsonl_release_ids = {r.get("release_id") or r.get("Release ID") for r in jsonl_rows}
    assert len(csv_release_ids) == 1, f"Multiple Release IDs in CSV: {csv_release_ids}"
    assert csv_release_ids == jsonl_release_ids, "Release IDs disagree"
    release_id = next(iter(csv_release_ids))
    
    # Verify checksums
    csv_sha = sha256_file(CSV_PATH)
    jsonl_sha = sha256_file(JSONL_PATH)
    
    # Load manifest
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    
    # Verify manifest matches
    assert manifest["record_count"] == len(csv_rows), f"Manifest record_count mismatch: {manifest['record_count']} vs {len(csv_rows)}"
    assert manifest["release_id"] == release_id, f"Manifest release_id mismatch: {manifest['release_id']} vs {release_id}"
    assert manifest["representations"]["csv"]["sha256"] == csv_sha, "CSV checksum mismatch"
    assert manifest["representations"]["jsonl"]["sha256"] == jsonl_sha, "JSONL checksum mismatch"
    
    print(json.dumps({
        "passed": True,
        "release_id": release_id,
        "record_count": len(csv_rows),
        "csv_sha256": csv_sha,
        "jsonl_sha256": jsonl_sha,
    }, indent=2))
    return 0


if __name__ == "__main__":
    main()
