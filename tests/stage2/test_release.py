from __future__ import annotations

import csv
import json
from copy import deepcopy

import pytest

from stage2.io import read_jsonl, write_jsonl
from stage2.release import export_release, reconcile_release


def _paths(tmp_path):
    return (
        tmp_path / "state.jsonl",
        tmp_path / "contacts.csv",
        tmp_path / "contacts.jsonl",
        tmp_path / "manifest.json",
    )


def test_one_command_writes_reconciled_representations(valid_record, tmp_path):
    canonical, csv_path, jsonl_path, manifest_path = _paths(tmp_path)
    write_jsonl(canonical, [valid_record])
    manifest = export_release(
        canonical,
        csv_path,
        jsonl_path,
        manifest_path,
        created_at="2026-08-11T08:30:00Z",
    )

    assert manifest["record_count"] == 1
    assert manifest["firm_count"] == 1
    assert manifest["qualifying_email_count"] == 1
    assert manifest["source_mix"] == {"association_directory": 1}
    assert manifest["release_ready"] is False
    assert len(read_jsonl(jsonl_path)) == 1
    with csv_path.open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    assert [row["Record ID"] for row in csv_rows] == [valid_record["record_id"]]
    assert csv_rows[0]["Primary Route Value"] == "jane.smith@example.com"
    assert reconcile_release(csv_path, jsonl_path, manifest_path)["passed"] is True


def test_requested_publish_record_that_fails_policy_blocks_export(valid_record, tmp_path):
    canonical, csv_path, jsonl_path, manifest_path = _paths(tmp_path)
    valid_record["contact_routes"][0]["inferred"] = True
    write_jsonl(canonical, [valid_record])
    with pytest.raises(ValueError, match="requested publication but failed policy"):
        export_release(canonical, csv_path, jsonl_path, manifest_path)


def test_duplicate_identity_blocks_export(valid_record, tmp_path):
    canonical, csv_path, jsonl_path, manifest_path = _paths(tmp_path)
    write_jsonl(canonical, [valid_record, deepcopy(valid_record)])
    with pytest.raises(ValueError, match="duplicate"):
        export_release(canonical, csv_path, jsonl_path, manifest_path)


def test_final_gate_can_fail_while_operating_release_remains_inspectable(valid_record, tmp_path):
    canonical, csv_path, jsonl_path, manifest_path = _paths(tmp_path)
    write_jsonl(canonical, [valid_record])
    with pytest.raises(ValueError, match="records 1 < 500"):
        export_release(canonical, csv_path, jsonl_path, manifest_path, final_gate=True)
    manifest = json.loads(manifest_path.read_text())
    assert manifest["release_ready"] is False
    assert manifest["record_count"] == 1


def test_reconciliation_detects_sibling_drift(valid_record, tmp_path):
    canonical, csv_path, jsonl_path, manifest_path = _paths(tmp_path)
    write_jsonl(canonical, [valid_record])
    export_release(canonical, csv_path, jsonl_path, manifest_path)
    with jsonl_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"record_id": "INJECTED"}) + "\n")
    with pytest.raises(ValueError, match="reconciliation failed"):
        reconcile_release(csv_path, jsonl_path, manifest_path)
