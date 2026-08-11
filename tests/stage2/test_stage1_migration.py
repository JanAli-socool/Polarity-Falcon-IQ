from stage2.import_stage1 import LEGACY_CSV, LEGACY_JSONL, migrate
from stage2.io import read_jsonl


def test_stage1_csv_becomes_quarantine_and_four_marketing_rows_are_rejected(tmp_path):
    canonical = tmp_path / "records.jsonl"
    rejections = tmp_path / "stage1_drift.jsonl"
    result = migrate(
        csv_path=LEGACY_CSV,
        legacy_jsonl_path=LEGACY_JSONL,
        canonical_path=canonical,
        rejection_path=rejections,
    )
    assert result == {"quarantined_stage1_records": 26, "rejected_jsonl_only_rows": 4}
    records = read_jsonl(canonical)
    assert len(records) == 26
    assert all(record["lifecycle_status"] == "quarantine" for record in records)
    assert all(record["release_decision"]["reason_codes"] for record in records)

    rejected = read_jsonl(rejections)
    assert [row["legacy_record_id"] for row in rejected] == ["FOC_007", "FOC_008", "FOC_009", "FOC_010"]
    assert {row["person_text"] for row in rejected} == {
        "Allow Us",
        "Ted Chartier’s Private",
        "Matt Sayers’ Private",
        "Connect With",
    }
