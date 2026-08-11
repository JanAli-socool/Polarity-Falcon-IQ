"""Migrate the authoritative Stage 1 CSV into Stage 2 quarantine.

The Stage 1 CSV is used because evaluator feedback established that it was the
representation actually indexed and served. JSONL-only rows are never copied
into canonical state; they are recorded in a separate rejection audit.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from stage2.io import read_jsonl, write_jsonl
from stage2.paths import QUARANTINE, ROOT, ensure_data_dirs

LEGACY_CSV = ROOT / "data" / "stage1" / "family_office_contacts.csv"
LEGACY_JSONL = ROOT / "data" / "stage1" / "family_office_contacts.jsonl"
from stage2.policy import build_record, evaluate_record


SOURCE_LABEL = "stage1_authoritative_csv"


def _evidence(url: str, observed_at: str, quote: str) -> dict[str, str]:
    return {
        "url": url,
        "observed_at": observed_at,
        "quote": quote,
        "support": "supported" if url and quote else "unresolved",
        "source_role": "stage1_migration_only",
    }


def migrate(
    csv_path: Path = LEGACY_CSV,
    legacy_jsonl_path: Path = LEGACY_JSONL,
    canonical_path: Path = QUARANTINE / "stage1_records.jsonl",
    rejection_path: Path | None = None,
) -> dict[str, int]:
    ensure_data_dirs()
    rejection_path = rejection_path or (QUARANTINE / "stage1_sibling_drift.jsonl")
    with csv_path.open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    legacy_json_rows = read_jsonl(legacy_jsonl_path)
    csv_identities = {
        (row.get("Family Office Name", "").casefold(), row.get("Contact Full Name", "").casefold())
        for row in csv_rows
    }

    canonical: list[dict] = []
    for row in csv_rows:
        observed_at = f"{row.get('Last Verified Date', '')}T00:00:00Z" if row.get("Last Verified Date") else ""
        firm_url = row.get("Firm Verification URL", "")
        person_url = row.get("Contact Source URL", "")
        firm_name = row.get("Family Office Name", "")
        person_name = row.get("Contact Full Name", "")
        title = row.get("Contact Job Title", "")
        record = build_record(
            firm={
                "name": firm_name,
                "type": "unresolved_stage1_classification",
                "country": row.get("Family Office Country", ""),
                "classification_evidence": _evidence(
                    firm_url,
                    observed_at,
                    row.get("Firm Verification Notes", "") or f"Stage 1 treated {firm_name} as a family office.",
                ),
            },
            person={
                "name": person_name,
                "title": title,
                "role_class": "unresolved_stage1_role",
                "role_evidence": _evidence(person_url, observed_at, f"{person_name} — {title}"),
            },
            discovery={
                "source_class": "search_discovery",
                "url": person_url or firm_url,
                "observed_at": observed_at,
                "stage1_legacy_record_id": row.get("Record ID", ""),
            },
            enrichments=[],
            contact_routes=[],
            freshness={
                "trust_state": "quarantined",
                "last_evidence_check_at": observed_at,
                "reason": "Stage 1 record has no route to the named person and has not passed the Stage 2 inclusion policy.",
            },
            lifecycle_status="quarantine",
        )
        evaluation = evaluate_record(record)
        record["release_decision"] = {
            "decision": "quarantine",
            "reason_codes": evaluation["reasons"],
            "policy": "stage2_minimum_inclusion_v1",
        }
        record["provenance"] = {"migration_source": SOURCE_LABEL}
        canonical.append(record)

    rejected: list[dict] = []
    for row in legacy_json_rows:
        legacy_id = row.get("Record ID", "")
        legacy_identity = (
            row.get("Family Office Name", "").casefold(),
            row.get("Contact Full Name", "").casefold(),
        )
        if legacy_identity not in csv_identities:
            rejected.append({
                "legacy_record_id": legacy_id,
                "person_text": row.get("Contact Full Name", ""),
                "firm_text": row.get("Family Office Name", ""),
                "source_url": row.get("Contact Source URL", ""),
                "decision": "rejected",
                "reason_code": "stage1.jsonl_not_in_authoritative_csv",
                "reason": "The Stage 1 customer JSONL drifted from the CSV/index. Evaluator feedback identified its four extra FCS rows as marketing text rather than people.",
            })

    write_jsonl(canonical_path, canonical, sort_key="record_id")
    write_jsonl(rejection_path, rejected, sort_key="legacy_record_id")
    return {"quarantined_stage1_records": len(canonical), "rejected_jsonl_only_rows": len(rejected)}


def main() -> None:
    print(json.dumps(migrate(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
