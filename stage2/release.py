"""Generate and reconcile every customer dataset representation in one step."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from stage2.io import canonical_json, read_jsonl, sha256_file, write_json
from stage2.paths import CANONICAL_RECORDS, RELEASE_CSV, RELEASE_JSONL, RELEASE_MANIFEST, ensure_data_dirs
from stage2.policy import email_qualifies, evaluate_record, route_qualifies

MINIMUM_RECORDS = 500
MINIMUM_EMAILS = 200
CSV_FIELDS = [
    "Release ID",
    "Record ID",
    "Family Office Name",
    "Family Office Type",
    "Family Office Country",
    "Contact Full Name",
    "Contact Job Title",
    "Contact Role",
    "Primary Route Type",
    "Primary Route Value",
    "Route Ownership Basis",
    "Route Current-Use Basis",
    "Route Evidence URL",
    "Qualifying Professional Email",
    "Discovery Source Class",
    "Discovery Source URL",
    "Decision-Relevant Intelligence",
    "Intelligence Kind",
    "Intelligence Evidence URL",
    "Firm Classification Evidence URL",
    "Last Evidence Check At",
    "Trust State",
    "Known Limitations",
]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _release_id(records: list[dict[str, Any]], created_at: str) -> str:
    material = "".join(canonical_json(record) for record in records) + created_at
    return f"REL_{hashlib.sha256(material.encode('utf-8')).hexdigest()[:16].upper()}"


def _select_primary_route(record: dict[str, Any]) -> dict[str, Any]:
    routes = [route for route in record.get("contact_routes", []) if route_qualifies(route)]
    priority = {"email": 0, "linkedin": 1, "direct_phone": 2}
    routes.sort(key=lambda route: (priority.get(route.get("type"), 99), str(route.get("value", ""))))
    if not routes:
        raise ValueError(f"{record.get('record_id')}: no qualifying route after release evaluation")
    return routes[0]


def _primary_enrichment(record: dict[str, Any]) -> dict[str, Any]:
    enrichments = sorted(
        record.get("enrichments", []),
        key=lambda item: (str(item.get("kind", "")), str(item.get("value", ""))),
    )
    if not enrichments:
        raise ValueError(f"{record.get('record_id')}: no enrichment after release evaluation")
    return enrichments[0]


def flatten_record(record: dict[str, Any], release_id: str) -> dict[str, str]:
    route = _select_primary_route(record)
    enrichment = _primary_enrichment(record)
    route_evidence = route.get("evidence", {})
    enrichment_evidence = enrichment.get("evidence", {})
    limitations = record.get("known_limitations", [])
    if isinstance(limitations, str):
        limitations = [limitations]
    return {
        "Release ID": release_id,
        "Record ID": str(record["record_id"]),
        "Family Office Name": str(record["firm"].get("name", "")),
        "Family Office Type": str(record["firm"].get("type", "")),
        "Family Office Country": str(record["firm"].get("country", "")),
        "Contact Full Name": str(record["person"].get("name", "")),
        "Contact Job Title": str(record["person"].get("title", "")),
        "Contact Role": str(record["person"].get("role_class", "")),
        "Primary Route Type": str(route.get("type", "")),
        "Primary Route Value": str(route.get("value", "")),
        "Route Ownership Basis": str(route.get("ownership_status", "")),
        "Route Current-Use Basis": str(route.get("current_status", "")),
        "Route Evidence URL": str(route_evidence.get("url", "")),
        "Qualifying Professional Email": "yes" if email_qualifies(route) else "no",
        "Discovery Source Class": str(record["discovery"].get("source_class", "")),
        "Discovery Source URL": str(record["discovery"].get("url", "")),
        "Decision-Relevant Intelligence": str(enrichment.get("value", "")),
        "Intelligence Kind": str(enrichment.get("kind", "")),
        "Intelligence Evidence URL": str(enrichment_evidence.get("url", "")),
        "Firm Classification Evidence URL": str(record["firm"].get("classification_evidence", {}).get("url", "")),
        "Last Evidence Check At": str(record["freshness"].get("last_evidence_check_at", "")),
        "Trust State": str(record["freshness"].get("trust_state", "")),
        "Known Limitations": " | ".join(str(item) for item in limitations if item),
    }


def _csv_bytes(rows: Iterable[dict[str, str]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_release(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    publishable: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_identities: set[str] = set()
    for record in records:
        if record.get("lifecycle_status") != "publish":
            continue
        evaluation = evaluate_record(record)
        record_id = str(record.get("record_id", ""))
        identity = str(record.get("identity_key", ""))
        duplicate_reasons: list[str] = []
        if record_id in seen_ids:
            duplicate_reasons.append("record.duplicate_id")
        if identity in seen_identities:
            duplicate_reasons.append("record.duplicate_identity")
        seen_ids.add(record_id)
        seen_identities.add(identity)
        reasons = sorted(set(evaluation["reasons"] + duplicate_reasons))
        if reasons:
            blocked.append({"record_id": record_id, "reasons": reasons})
        else:
            publishable.append(record)
    publishable.sort(key=lambda record: str(record["record_id"]))
    return publishable, blocked


def export_release(
    canonical_path: Path = CANONICAL_RECORDS,
    csv_path: Path = RELEASE_CSV,
    jsonl_path: Path = RELEASE_JSONL,
    manifest_path: Path = RELEASE_MANIFEST,
    *,
    final_gate: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    ensure_data_dirs()
    records = read_jsonl(canonical_path)
    publishable, blocked = prepare_release(records)
    if blocked:
        sample = "; ".join(f"{item['record_id']}: {','.join(item['reasons'])}" for item in blocked[:5])
        raise ValueError(f"{len(blocked)} records requested publication but failed policy: {sample}")

    created_at = created_at or _now()
    release_id = _release_id(publishable, created_at)
    json_rows = [{"release_id": release_id, **record} for record in publishable]
    csv_rows = [flatten_record(record, release_id) for record in publishable]

    # The manifest is written last and is the transaction marker. If a process
    # dies between replacements, reconciliation rejects the incomplete release.
    _write_atomic(jsonl_path, b"".join(f"{canonical_json(row)}\n".encode("utf-8") for row in json_rows))
    _write_atomic(csv_path, _csv_bytes(csv_rows))

    email_count = sum(
        any(email_qualifies(route) for route in record.get("contact_routes", []))
        for record in publishable
    )
    source_mix = Counter(record["discovery"]["source_class"] for record in publishable)
    firm_count = len({record["firm"]["name"].casefold() for record in publishable})
    readiness_failures: list[str] = []
    if len(publishable) < MINIMUM_RECORDS:
        readiness_failures.append(f"records {len(publishable)} < {MINIMUM_RECORDS}")
    if email_count < MINIMUM_EMAILS:
        readiness_failures.append(f"qualifying_emails {email_count} < {MINIMUM_EMAILS}")

    manifest = {
        "schema_version": "2.0",
        "release_id": release_id,
        "created_at": created_at,
        "canonical_source": str(canonical_path),
        "record_count": len(publishable),
        "firm_count": firm_count,
        "qualifying_email_count": email_count,
        "source_mix": dict(sorted(source_mix.items())),
        "release_ready": not readiness_failures,
        "readiness_failures": readiness_failures,
        "representations": {
            "csv": {"path": str(csv_path), "sha256": sha256_file(csv_path)},
            "jsonl": {"path": str(jsonl_path), "sha256": sha256_file(jsonl_path)},
        },
    }
    write_json(manifest_path, manifest)
    reconcile_release(csv_path, jsonl_path, manifest_path)
    if final_gate and readiness_failures:
        raise ValueError("final release gate failed: " + "; ".join(readiness_failures))
    return manifest


def reconcile_release(csv_path: Path, jsonl_path: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    json_rows = read_jsonl(jsonl_path)
    with csv_path.open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))

    problems: list[str] = []
    if sha256_file(csv_path) != manifest["representations"]["csv"]["sha256"]:
        problems.append("csv checksum differs from manifest")
    if sha256_file(jsonl_path) != manifest["representations"]["jsonl"]["sha256"]:
        problems.append("jsonl checksum differs from manifest")
    if len(csv_rows) != len(json_rows) or len(json_rows) != manifest["record_count"]:
        problems.append("row counts disagree")
    csv_ids = [row.get("Record ID") for row in csv_rows]
    json_ids = [row.get("record_id") for row in json_rows]
    if csv_ids != json_ids:
        problems.append("record IDs or ordering disagree")
    csv_release_ids = {row.get("Release ID") for row in csv_rows}
    json_release_ids = {row.get("release_id") for row in json_rows}
    expected_release_ids = {manifest["release_id"]} if json_rows else set()
    if csv_release_ids != expected_release_ids or json_release_ids != expected_release_ids:
        problems.append("release IDs disagree")

    if problems:
        raise ValueError("release reconciliation failed: " + "; ".join(problems))
    return {
        "passed": True,
        "release_id": manifest["release_id"],
        "record_count": len(json_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final", action="store_true", help="Fail below the 500-record/200-email final floor")
    parser.add_argument("--reconcile-only", action="store_true")
    args = parser.parse_args()
    if args.reconcile_only:
        result = reconcile_release(RELEASE_CSV, RELEASE_JSONL, RELEASE_MANIFEST)
    else:
        result = export_release(final_gate=args.final)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
