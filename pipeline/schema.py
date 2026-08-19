# pipeline/schema.py
# Canonical dataset schema — single source of truth for Stage 2.
# All released artifacts (CSV, JSONL, Chroma index, UI counts) are generated from this.

import sqlite3
import pathlib
import json
import csv
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
from enum import Enum
from collections import Counter

DB_PATH = pathlib.Path("data/canonical/contacts.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


class VerificationTier(str, Enum):
    OFFICIAL_DOMAIN = "official_domain"
    OFFICIAL_OR_RELATED = "official_or_related_domain"
    OFFICIAL_OR_COMPANY_PAGE = "official_domain_or_company_page"
    SEC_CORROBORATED = "sec_corroborated"
    UNVERIFIED = "unverified"


class EmailValidationCode(str, Enum):
    V1 = "V1"  # Published on source page, MX verified, belongs to named individual
    V2 = "V2"  # Published on source page, MX verified
    U1 = "U1"  # Published on source page, MX unverified
    U2 = "U2"  # Published on source page, MX lookup failed
    P0 = "P0"  # Not published on source page
    INFERRED = "INFERRED"  # Pattern-generated — EXCLUDED from qualifying count


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RecordStatus(str, Enum):
    QUALIFYING = "qualifying"      # Counts toward 500
    QUARANTINED = "quarantined"    # Evidence-based reason, excluded from 500
    REJECTED = "rejected"          # Failed inclusion standard


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

-- Firms table
CREATE TABLE IF NOT EXISTS firms (
    firm_id INTEGER PRIMARY KEY AUTOINCREMENT,
    firm_name TEXT NOT NULL UNIQUE,
    official_url TEXT,
    verification_tier TEXT NOT NULL,
    verification_notes TEXT,
    firm_country TEXT,
    firm_city TEXT,
    firm_state TEXT,
    discovery_source TEXT,           -- Which source class discovered this firm
    discovery_query TEXT,            -- Specific query that found it
    discovery_date TEXT NOT NULL,    -- ISO timestamp
    last_verified_date TEXT,         -- ISO timestamp of last verification
    verification_status TEXT DEFAULT 'current',  -- current, stale, failed
    sec_cik TEXT,
    sec_filing_url TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- People table (contacts)
CREATE TABLE IF NOT EXISTS people (
    person_id INTEGER PRIMARY KEY AUTOINCREMENT,
    firm_id INTEGER NOT NULL REFERENCES firms(firm_id),
    record_id TEXT NOT NULL UNIQUE,  -- FOC_001 format
    first_name TEXT,
    last_name TEXT,
    full_name TEXT NOT NULL,
    job_title TEXT,
    title_normalized TEXT,           -- Clean role string (e.g., "Managing Partner")
    email TEXT,
    email_validation_code TEXT,
    email_validation_explanation TEXT,
    email_quality TEXT,
    linkedin_url TEXT,
    linkedin_verified BOOLEAN DEFAULT FALSE,
    phone TEXT,
    phone_verified BOOLEAN DEFAULT FALSE,
    source_url TEXT NOT NULL,        -- Page where extracted
    extraction_method TEXT,
    extraction_strategy TEXT,        -- heading_tag_dom, card_block_fallback, etc.
    validation_status TEXT,          -- verified_name_title_from_source_page, etc.
    confidence TEXT NOT NULL,        -- high, medium, low
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'qualifying',  -- qualifying, quarantined, rejected
    quarantine_reason TEXT,          -- If quarantined, why
    last_verified_date TEXT,         -- ISO timestamp
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Discovery log (audit trail for every firm/person discovered)
CREATE TABLE IF NOT EXISTS discovery_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,       -- 'firm' or 'person'
    entity_id INTEGER NOT NULL,      -- firm_id or person_id
    source_class TEXT NOT NULL,      -- web_search, sec_edgar, firm_website, linkedin, etc.
    source_query TEXT,
    source_url TEXT,
    raw_evidence TEXT,               -- JSON of raw snippet/html
    extracted_fields TEXT,           -- JSON of what was extracted
    confidence_at_discovery TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Run log (for operating window tracking)
CREATE TABLE IF NOT EXISTS run_log (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_type TEXT NOT NULL,          -- scheduled, manual, goal_test
    run_started TEXT NOT NULL,
    run_ended TEXT,
    status TEXT,                     -- success, partial_failure, failure
    records_processed INTEGER DEFAULT 0,
    records_added INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    records_quarantined INTEGER DEFAULT 0,
    errors TEXT,                     -- JSON array of error objects
    notes TEXT
);

-- Staleness checks (track what changed across runs)
CREATE TABLE IF NOT EXISTS staleness_log (
    check_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER REFERENCES run_log(run_id),
    entity_type TEXT NOT NULL,       -- 'firm' or 'person'
    entity_id INTEGER NOT NULL,
    check_type TEXT NOT NULL,        -- content_changed, source_gone, contradicted, email_bounced
    previous_value TEXT,
    current_value TEXT,
    action_taken TEXT,               -- refreshed, quarantined, flagged, no_change
    evidence TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_people_firm ON people(firm_id);
CREATE INDEX IF NOT EXISTS idx_people_status ON people(status);
CREATE INDEX IF NOT EXISTS idx_people_email ON people(email);
CREATE INDEX IF NOT EXISTS idx_firms_verification ON firms(verification_tier);
CREATE INDEX IF NOT EXISTS idx_discovery_entity ON discovery_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_staleness_entity ON staleness_log(entity_type, entity_id);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
    print(f"[ok] Canonical DB initialized at {DB_PATH}")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Firm operations ---
def upsert_firm(
    firm_name: str,
    official_url: str,
    verification_tier: str,
    verification_notes: str = "",
    firm_country: str = "United States",
    firm_city: str = "",
    firm_state: str = "",
    discovery_source: str = "web_search",
    discovery_query: str = "",
    sec_cik: str = "",
    sec_filing_url: str = "",
) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT firm_id FROM firms WHERE firm_name = ?", (firm_name,))
    row = cur.fetchone()
    if row:
        firm_id = row["firm_id"]
        cur.execute("""
            UPDATE firms SET official_url=?, verification_tier=?, verification_notes=?,
                firm_country=?, firm_city=?, firm_state=?, discovery_source=?,
                discovery_query=?, sec_cik=?, sec_filing_url=?, last_verified_date=?,
                updated_at=? WHERE firm_id=?
        """, (official_url, verification_tier, verification_notes, firm_country,
              firm_city, firm_state, discovery_source, discovery_query, sec_cik,
              sec_filing_url, now_iso(), now_iso(), firm_id))
    else:
        cur.execute("""
            INSERT INTO firms (firm_name, official_url, verification_tier, verification_notes,
                firm_country, firm_city, firm_state, discovery_source, discovery_query,
                discovery_date, sec_cik, sec_filing_url, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (firm_name, official_url, verification_tier, verification_notes,
              firm_country, firm_city, firm_state, discovery_source, discovery_query,
              now_iso(), sec_cik, sec_filing_url, now_iso(), now_iso()))
        firm_id = cur.lastrowid
    conn.commit()
    conn.close()
    return firm_id


def get_firm(firm_id: int) -> Optional[sqlite3.Row]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM firms WHERE firm_id = ?", (firm_id,))
    row = cur.fetchone()
    conn.close()
    return row


def get_all_firms() -> List[sqlite3.Row]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM firms ORDER BY firm_name")
    rows = cur.fetchall()
    conn.close()
    return rows


# --- People operations ---
def upsert_person(
    firm_id: int,
    record_id: str,
    full_name: str,
    first_name: str = "",
    last_name: str = "",
    job_title: str = "",
    title_normalized: str = "",
    email: str = "",
    email_validation_code: str = "P0",
    email_validation_explanation: str = "",
    email_quality: str = "Not available",
    linkedin_url: str = "",
    linkedin_verified: bool = False,
    phone: str = "",
    phone_verified: bool = False,
    source_url: str = "",
    extraction_method: str = "",
    extraction_strategy: str = "",
    validation_status: str = "",
    confidence: str = "low",
    notes: str = "",
    status: str = "qualifying",
    quarantine_reason: str = "",
) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT person_id FROM people WHERE record_id = ?", (record_id,))
    row = cur.fetchone()
    if row:
        person_id = row["person_id"]
        cur.execute("""
            UPDATE people SET firm_id=?, first_name=?, last_name=?, full_name=?,
                job_title=?, title_normalized=?, email=?, email_validation_code=?,
                email_validation_explanation=?, email_quality=?, linkedin_url=?,
                linkedin_verified=?, phone=?, phone_verified=?, source_url=?,
                extraction_method=?, extraction_strategy=?, validation_status=?,
                confidence=?, notes=?, status=?, quarantine_reason=?,
                last_verified_date=?, updated_at=? WHERE person_id=?
        """, (firm_id, first_name, last_name, full_name, job_title, title_normalized,
              email, email_validation_code, email_validation_explanation, email_quality,
              linkedin_url, linkedin_verified, phone, phone_verified, source_url,
              extraction_method, extraction_strategy, validation_status, confidence,
              notes, status, quarantine_reason, now_iso(), now_iso(), person_id))
    else:
        cur.execute("""
            INSERT INTO people (firm_id, record_id, first_name, last_name, full_name,
                job_title, title_normalized, email, email_validation_code,
                email_validation_explanation, email_quality, linkedin_url,
                linkedin_verified, phone, phone_verified, source_url,
                extraction_method, extraction_strategy, validation_status,
                confidence, notes, status, quarantine_reason, last_verified_date,
                created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (firm_id, record_id, first_name, last_name, full_name, job_title,
              title_normalized, email, email_validation_code, email_validation_explanation,
              email_quality, linkedin_url, linkedin_verified, phone, phone_verified,
              source_url, extraction_method, extraction_strategy, validation_status,
              confidence, notes, status, quarantine_reason, now_iso(), now_iso(), now_iso()))
        person_id = cur.lastrowid
    conn.commit()
    conn.close()
    return person_id


def get_person(record_id: str) -> Optional[sqlite3.Row]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM people WHERE record_id = ?", (record_id,))
    row = cur.fetchone()
    conn.close()
    return row


def get_qualifying_people() -> List[sqlite3.Row]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM people WHERE status = 'qualifying' ORDER BY firm_id, record_id")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_all_people() -> List[sqlite3.Row]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM people ORDER BY firm_id, record_id")
    rows = cur.fetchall()
    conn.close()
    return rows


def count_qualifying() -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM people WHERE status = 'qualifying'")
    row = cur.fetchone()
    conn.close()
    return row["c"]


def count_qualifying_with_email() -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) as c FROM people
        WHERE status = 'qualifying' AND email != '' AND email_validation_code IN ('V1','V2')
    """)
    row = cur.fetchone()
    conn.close()
    return row["c"]


def get_firm_counts() -> Dict[str, int]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT f.firm_name, COUNT(p.person_id) as cnt
        FROM firms f
        LEFT JOIN people p ON p.firm_id = f.firm_id AND p.status = 'qualifying'
        GROUP BY f.firm_id, f.firm_name
        HAVING cnt > 0
        ORDER BY cnt DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return {r["firm_name"]: r["cnt"] for r in rows}


# --- Discovery log ---
def log_discovery(entity_type: str, entity_id: int, source_class: str,
                  source_query: str = "", source_url: str = "",
                  raw_evidence: dict = None, extracted_fields: dict = None,
                  confidence_at_discovery: str = ""):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO discovery_log (entity_type, entity_id, source_class, source_query,
            source_url, raw_evidence, extracted_fields, confidence_at_discovery, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (entity_type, entity_id, source_class, source_query, source_url,
          json.dumps(raw_evidence or {}), json.dumps(extracted_fields or {}),
          confidence_at_discovery, now_iso()))
    conn.commit()
    conn.close()


# --- Run log ---
def start_run(run_type: str) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO run_log (run_type, run_started, status, created_at)
        VALUES (?, ?, 'running', ?)
    """, (run_type, now_iso(), now_iso()))
    run_id = cur.lastrowid
    conn.commit()
    conn.close()
    return run_id


def end_run(run_id: int, status: str, records_processed: int = 0,
            records_added: int = 0, records_updated: int = 0,
            records_quarantined: int = 0, errors: list = None, notes: str = ""):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE run_log SET run_ended=?, status=?, records_processed=?,
            records_added=?, records_updated=?, records_quarantined=?,
            errors=?, notes=? WHERE run_id=?
    """, (now_iso(), status, records_processed, records_added,
          records_updated, records_quarantined, json.dumps(errors or []), notes, run_id))
    conn.commit()
    conn.close()


# --- Staleness log ---
def log_staleness(run_id: int, entity_type: str, entity_id: int,
                  check_type: str, previous_value: str, current_value: str,
                  action_taken: str, evidence: str = ""):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO staleness_log (run_id, entity_type, entity_id, check_type,
            previous_value, current_value, action_taken, evidence, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (run_id, entity_type, entity_id, check_type, previous_value,
          current_value, action_taken, evidence, now_iso()))
    conn.commit()
    conn.close()


# --- Export functions (canonical source -> release artifacts) ---
def export_csv(path: pathlib.Path):
    """Export qualifying records to CSV matching Stage 1 format."""
    people = get_qualifying_people()
    firms = {f["firm_id"]: f for f in get_all_firms()}

    fieldnames = [
        "Release ID",
        "Record ID", "Family Office Name", "Family Office City", "Family Office State / Region",
        "Family Office Country", "Contact First Name", "Contact Last Name", "Contact Full Name",
        "Contact Job Title", "Contact Location", "Contact LinkedIn Profile",
        "Contact Primary Email", "Primary E-Mail Validation Code",
        "Primary E-Mail Code Explanation", "Email Quality Assessment (Primary)",
        "Primary Phone Number", "Contact Secondary Email", "Secondary E-Mail Validation Code",
        "E-Mail Code Explanation", "Email Quality Assessment (Secondary)",
        "Secondary Phone Number", "Firm Verification URL", "Firm Verification Tier",
        "Firm Verification Notes", "Contact Source URL", "Extraction Method",
        "Validation Status", "Confidence", "Notes", "Last Verified Date"
    ]

    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for p in people:
            firm = firms[p["firm_id"]]
            writer.writerow({
                "Release ID": "REL_PIPELINE_500",
                "Record ID": p["record_id"],
                "Family Office Name": firm["firm_name"],
                "Family Office City": firm["firm_city"] or "",
                "Family Office State / Region": firm["firm_state"] or "",
                "Family Office Country": firm["firm_country"] or "",
                "Contact First Name": p["first_name"] or "",
                "Contact Last Name": p["last_name"] or "",
                "Contact Full Name": p["full_name"],
                "Contact Job Title": p["job_title"] or "",
                "Contact Location": "",
                "Contact LinkedIn Profile": p["linkedin_url"] or "",
                "Contact Primary Email": p["email"] or "",
                "Primary E-Mail Validation Code": p["email_validation_code"] or "P0",
                "Primary E-Mail Code Explanation": p["email_validation_explanation"] or "",
                "Email Quality Assessment (Primary)": p["email_quality"] or "Not available",
                "Primary Phone Number": p["phone"] or "",
                "Contact Secondary Email": "",
                "Secondary E-Mail Validation Code": "P0",
                "E-Mail Code Explanation": "No secondary email was extracted from the public source page.",
                "Email Quality Assessment (Secondary)": "Not available",
                "Secondary Phone Number": "",
                "Firm Verification URL": firm["official_url"] or "",
                "Firm Verification Tier": firm["verification_tier"] or "",
                "Firm Verification Notes": firm["verification_notes"] or "",
                "Contact Source URL": p["source_url"] or "",
                "Extraction Method": p["extraction_method"] or "",
                "Validation Status": p["validation_status"] or "",
                "Confidence": p["confidence"] or "low",
                "Notes": p["notes"] or "Blank cells mean the pipeline could not verify the field from public evidence.",
                "Last Verified Date": (p["last_verified_date"] or "").split("T")[0] if p["last_verified_date"] else "",
            })
    print(f"[ok] Exported {len(people)} qualifying records to {path}")


def export_jsonl(path: pathlib.Path):
    """Export qualifying records to JSONL (identical data to CSV)."""
    people = get_qualifying_people()
    firms = {f["firm_id"]: f for f in get_all_firms()}

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for p in people:
            firm = firms[p["firm_id"]]
            rec = {
                "release_id": "REL_PIPELINE_500",
                "record_id": p["record_id"],
                "Family Office Name": firm["firm_name"],
                "Family Office City": firm["firm_city"] or "",
                "Family Office State / Region": firm["firm_state"] or "",
                "Family Office Country": firm["firm_country"] or "",
                "Contact First Name": p["first_name"] or "",
                "Contact Last Name": p["last_name"] or "",
                "Contact Full Name": p["full_name"],
                "Contact Job Title": p["job_title"] or "",
                "Contact Location": "",
                "Contact LinkedIn Profile": p["linkedin_url"] or "",
                "Contact Primary Email": p["email"] or "",
                "Primary E-Mail Validation Code": p["email_validation_code"] or "P0",
                "Primary E-Mail Code Explanation": p["email_validation_explanation"] or "",
                "Email Quality Assessment (Primary)": p["email_quality"] or "Not available",
                "Primary Phone Number": p["phone"] or "",
                "Contact Secondary Email": "",
                "Secondary E-Mail Validation Code": "P0",
                "E-Mail Code Explanation": "No secondary email was extracted from the public source page.",
                "Email Quality Assessment (Secondary)": "Not available",
                "Secondary Phone Number": "",
                "Firm Verification URL": firm["official_url"] or "",
                "Firm Verification Tier": firm["verification_tier"] or "",
                "Firm Verification Notes": firm["verification_notes"] or "",
                "Contact Source URL": p["source_url"] or "",
                "Extraction Method": p["extraction_method"] or "",
                "Validation Status": p["validation_status"] or "",
                "Confidence": p["confidence"] or "low",
                "Notes": p["notes"] or "Blank cells mean the pipeline could not verify the field from public evidence.",
                "Last Verified Date": (p["last_verified_date"] or "").split("T")[0] if p["last_verified_date"] else "",
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[ok] Exported {len(people)} qualifying records to {path}")


def export_rejected_jsonl(path: pathlib.Path):
    """Export quarantined/rejected records with reasons (audit trail)."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM people WHERE status != 'qualifying' ORDER BY firm_id, record_id")
    rows = cur.fetchall()
    conn.close()

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            rec = dict(r)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[ok] Exported {len(rows)} non-qualifying records to {path}")


def rebuild_chroma_index():
    """Rebuild Chroma index from canonical qualifying records."""
    import chromadb
    from chromadb.utils import embedding_functions

    people = get_qualifying_people()
    firms = {f["firm_id"]: f for f in get_all_firms()}

    DB_DIR = pathlib.Path("rag/chroma_db")
    DB_DIR.mkdir(parents=True, exist_ok=True)

    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    client = chromadb.PersistentClient(path=str(DB_DIR))
    try:
        client.delete_collection("fo_contacts")
    except Exception:
        pass
    col = client.create_collection("fo_contacts", embedding_function=embed_fn)

    docs, ids, metas = [], [], []
    for p in people:
        firm = firms[p["firm_id"]]
        parts = [
            f"{p['full_name']} works at {firm['firm_name']}.",
            f"Job title: {p['job_title']}." if p['job_title'] else "",
            f"Firm country: {firm['firm_country']}." if firm['firm_country'] else "",
            f"Firm city: {firm['firm_city']}." if firm['firm_city'] else "",
            f"Email: {p['email']}." if p['email'] else "",
            f"LinkedIn: {p['linkedin_url']}." if p['linkedin_url'] else "",
        ]
        docs.append(" ".join(part for part in parts if part))
        ids.append(p['record_id'])
        metas.append({
            "record_id": p['record_id'],
            "firm": firm['firm_name'],
            "person": p['full_name'],
            "title": p['job_title'] or "",
            "email": p['email'] or "",
            "source_url": p['source_url'] or "",
            "confidence": p['confidence'] or "low",
        })

    col.add(documents=docs, ids=ids, metadatas=metas)
    print(f"[ok] Rebuilt Chroma index with {len(docs)} records")


if __name__ == "__main__":
    init_db()
    print(f"Qualifying count: {count_qualifying()}")
    print(f"Qualifying with email (V1/V2): {count_qualifying_with_email()}")
    print(f"Firm distribution: {get_firm_counts()}")


def export_manifest(
    csv_path: pathlib.Path = pathlib.Path("data/final/family_office_contacts.csv"),
    jsonl_path: pathlib.Path = pathlib.Path("data/final/family_office_contacts.jsonl"),
    manifest_path: pathlib.Path = pathlib.Path("data/final/release_manifest.json"),
):
    """Generate manifest from pipeline CSV/JSONL (not Stage 2 DB)."""
    import hashlib
    from datetime import datetime, timezone
    from collections import Counter

    def sha256_file(path: pathlib.Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    # Load CSV
    csv_rows = []
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        csv_rows = list(reader)

    # Load JSONL
    jsonl_rows = []
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            jsonl_rows.append(json.loads(line))

    assert len(csv_rows) == len(jsonl_rows), "Row count mismatch"
    csv_ids = [r.get("Record ID") for r in csv_rows]
    jsonl_ids = [r.get("record_id") or r.get("Record ID") for r in jsonl_rows]
    assert csv_ids == jsonl_ids, "Record IDs disagree"

    csv_release_ids = {r.get("Release ID") for r in csv_rows}
    jsonl_release_ids = {r.get("release_id") or r.get("Release ID") for r in jsonl_rows}
    assert len(csv_release_ids) == 1, f"Multiple Release IDs in CSV: {csv_release_ids}"
    assert csv_release_ids == jsonl_release_ids, "Release IDs disagree"
    release_id = next(iter(csv_release_ids))

    # Count V1/V2 emails
    v1_v2_count = sum(1 for r in csv_rows if r.get("Primary E-Mail Validation Code") in ("V1", "V2"))

    # Count LinkedIn
    linkedin_count = sum(1 for r in csv_rows if r.get("Contact LinkedIn Profile"))

    # Source mix
    source_mix = Counter(r.get("Discovery Source Class") for r in csv_rows if r.get("Discovery Source Class"))

    # Countries
    countries = sorted(set(r.get("Family Office Country") for r in csv_rows if r.get("Family Office Country")))

    # Firm count
    firm_count = len(set(r.get("Family Office Name") for r in csv_rows))

    csv_sha = sha256_file(csv_path)
    jsonl_sha = sha256_file(jsonl_path)

    manifest = {
        "schema_version": "2.0",
        "release_id": release_id,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "canonical_source": str(csv_path),
        "record_count": len(csv_rows),
        "firm_count": firm_count,
        "qualifying_email_count": v1_v2_count,
        "linkedin_count": linkedin_count,
        "source_mix": dict(sorted(source_mix.items())),
        "release_ready": len(csv_rows) >= 500 and v1_v2_count >= 12,
        "readiness_failures": [] if (len(csv_rows) >= 500 and v1_v2_count >= 12) else [f"records {len(csv_rows)} < 500"],
        "representations": {
            "csv": {"path": str(csv_path), "sha256": csv_sha},
            "jsonl": {"path": str(jsonl_path), "sha256": jsonl_sha},
        },
    }

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"[ok] Generated manifest: {manifest_path}")
    return manifest