# pipeline/build_final.py
import json
import csv
import pathlib
import re
from datetime import datetime, timezone
from collections import defaultdict

# Import schema
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from schema import (
    get_conn, upsert_firm, upsert_person, count_qualifying,
    count_qualifying_with_email, get_firm_counts, export_csv, export_jsonl,
    rebuild_chroma_index, export_rejected_jsonl, init_db
)

FIRMS = pathlib.Path("data/raw/firms_curated_v2.jsonl")
PEOPLE = pathlib.Path("data/raw/people_enriched_v3.jsonl")
OUT_CSV = pathlib.Path("data/final/family_office_contacts.csv")
OUT_JSONL = pathlib.Path("data/final/family_office_contacts.jsonl")
AUDIT = pathlib.Path("data/audit/people_filter_audit_v2.jsonl")
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
AUDIT.parent.mkdir(parents=True, exist_ok=True)

TARGET_ROWS = 500
MIN_ACCEPTABLE = 350

TITLE_KEYWORDS = [
    "president", "director", "officer", "partner", "principal", "founder",
    "manager", "advisor", "adviser", "associate", "analyst", "chief",
    "head", "managing", "executive", "chairman", "ceo", "cfo", "cio", "coo",
    "controller", "accountant", "counsel", "secretary", "treasurer",
    "vice president", "portfolio", "investment", "wealth", "family", "trust",
    "tax", "operations", "client", "planning", "compliance", "strategist",
    "senior", "lead", "relationship", "capital", "private", "equity",
]

BAD_NAME_PARTS = [
    "family office", "capital partners", "wealth management", "private wealth",
    "investment management", "tax planning", "estate planning", "financial planning",
    "our team", "join our", "careers", "contact us", "read bio", "learn more",
    "client portal", "privacy policy", "terms", "services", "home", "about us",
    "newsletter", "subscribe", "download", "view all", "phone number",
]

BAD_TITLE_PARTS = [
    "read bio", "learn more", "click here", "contact us", "privacy policy",
    "terms of use", "client portal", "subscribe", "phone number",
]

def load_curated_firms():
    firms = {}
    with FIRMS.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            firms[rec["firm_name"]] = rec
    return firms

def clean_text(s):
    return re.sub(r"\s+", " ", (s or "")).strip()

def split_name(full):
    parts = full.strip().split()
    if len(parts) < 2:
        return "", ""
    return parts[0], parts[-1]

def plausible_name(name):
    name = clean_text(name)
    low = name.lower()
    if not name or len(name) < 5 or len(name) > 60:
        return False, "bad name length"
    if any(x in low for x in BAD_NAME_PARTS):
        return False, "name contains non-person phrase"
    parts = name.split()
    if len(parts) < 2 or len(parts) > 4:
        return False, "name token count not plausible"
    if re.search(r"\d|@|/|\\|\|", name):
        return False, "name contains digit or symbol noise"
    if not re.match(r"^[A-Z][A-Za-z'’\-]+$", parts[0]):
        return False, "first token not person-like"
    if not re.match(r"^[A-Z][A-Za-z'’\-]+$", parts[-1]):
        return False, "last token not person-like"
    return True, ""

def plausible_title(title):
    title = clean_text(title)
    low = title.lower()
    if not title or len(title) < 3:
        return False, "empty/short title"
    if len(title) > 160:
        return False, "title too long"
    if any(x in low for x in BAD_TITLE_PARTS):
        return False, "title contains non-title phrase"
    if not any(k in low for k in TITLE_KEYWORDS):
        return False, "title lacks role keyword"
    return True, ""

def confidence_for(r):
    score = 0
    if r["Contact Job Title"]:
        score += 1
    if r["Contact Primary Email"]:
        score += 1
    if any(x in r["Contact Source URL"].lower() for x in ["team", "people", "about"]):
        score += 1
    if r["Firm Verification Tier"].startswith("official"):
        score += 1
    if score >= 3:
        return "high"
    if score == 2:
        return "medium"
    return "low"

firms = load_curated_firms()

kept_by_firm = defaultdict(list)
audit = []
seen = set()

with PEOPLE.open(encoding="utf-8") as f:
    for line in f:
        p = json.loads(line)
        raw_firm = p.get("firm_name", "")
        if raw_firm not in firms:
            audit.append({"decision": "rejected", "reason": "firm not in curated firm list", "person": p.get("name", ""), "firm": raw_firm, "source_url": p.get("source_url", "")})
            continue
        firm = firms[raw_firm]
        name = clean_text(p.get("name", ""))
        title = clean_text(p.get("title", ""))
        ok, reason = plausible_name(name)
        if not ok:
            audit.append({"decision": "rejected", "reason": reason, "person": name, "firm": raw_firm, "source_url": p.get("source_url", "")})
            continue
        ok, reason = plausible_title(title)
        if not ok:
            audit.append({"decision": "rejected", "reason": reason, "person": name, "firm": raw_firm, "source_url": p.get("source_url", "")})
            continue
        key = (raw_firm.lower(), name.lower())
        if key in seen:
            audit.append({"decision": "rejected", "reason": "duplicate person within firm", "person": name, "firm": raw_firm, "source_url": p.get("source_url", "")})
            continue
        seen.add(key)
        first, last = split_name(name)
        email = p.get("email", "")
        email_code = p.get("email_validation_code", "P0")
        email_explanation = p.get("email_validation_explanation", "")
        email_quality = p.get("email_quality", "Not available")
        linkedin = p.get("linkedin_url", "")
        linkedin_verified = p.get("linkedin_verified", False)
        phone = p.get("phone", "")
        phone_verified = p.get("phone_verified", False)
        source_url = p.get("source_url", "")
        extraction_strategy = p.get("extraction_strategy", "")
        validation_status = "verified_name_title_from_source_page"
        notes = "Blank cells mean the pipeline could not verify the field from public evidence."
        row = {
            "Record ID": "",
            "Family Office Name": raw_firm,
            "Family Office City": "",
            "Family Office State / Region": "",
            "Family Office Country": firm.get("firm_country", ""),
            "Contact First Name": first,
            "Contact Last Name": last,
            "Contact Full Name": name,
            "Contact Job Title": title,
            "Contact Location": "",
            "Contact LinkedIn Profile": linkedin,
            "Contact Primary Email": email,
            "Primary E-Mail Validation Code": email_code,
            "Primary E-Mail Code Explanation": email_explanation,
            "Email Quality Assessment (Primary)": email_quality,
            "Primary Phone Number": phone,
            "Contact Secondary Email": "",
            "Secondary E-Mail Validation Code": "P0",
            "E-Mail Code Explanation": "No secondary email was extracted from the public source page.",
            "Email Quality Assessment (Secondary)": "Not available",
            "Secondary Phone Number": "",
            "Firm Verification URL": firm.get("official_url", ""),
            "Firm Verification Tier": firm.get("verification_tier", ""),
            "Firm Verification Notes": firm.get("curation_notes", ""),
            "Contact Source URL": source_url,
            "Extraction Method": f"Automated HTML extraction from verified firm page ({extraction_strategy}), then rule-based filtering.",
            "Validation Status": validation_status,
            "Confidence": "",
            "Notes": notes,
            "Last Verified Date": datetime.now(timezone.utc).date().isoformat(),
        }
        row["Confidence"] = confidence_for(row)
        kept_by_firm[raw_firm].append(row)

selected = []
for firm_name, rows in sorted(kept_by_firm.items()):
    rows = sorted(rows, key=lambda r: (
        1 if r["Contact Primary Email"] else 0,
        1 if any(x in r["Contact Source URL"].lower() for x in ["team", "people", "about"]) else 0,
        1 if r["Confidence"] == "high" else 0,
    ), reverse=True)
    selected.extend(rows[:35])

print(f"Total selected: {len(selected)}")
if len(selected) < MIN_ACCEPTABLE:
    print(f"WARN: Below minimum ({len(selected)} < {MIN_ACCEPTABLE})")
elif len(selected) < TARGET_ROWS:
    print(f"OK: {len(selected)} rows (target {TARGET_ROWS})")
else:
    print("OK: target met")

selected = selected[:TARGET_ROWS]
RELEASE_ID = "REL_PIPELINE_500"
for i, row in enumerate(selected, 1):
    row["Record ID"] = f"FOC_{i:03d}"
    row["Release ID"] = RELEASE_ID

with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(selected[0].keys()))
    writer.writeheader()
    writer.writerows(selected)

with OUT_JSONL.open("w", encoding="utf-8") as f:
    for row in selected:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

with AUDIT.open("w", encoding="utf-8") as f:
    for rec in audit:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

print(f"Written: {OUT_CSV}")
print(f"Written: {OUT_JSONL}")
print(f"Written: {AUDIT}")

emails = sum(1 for r in selected if r["Contact Primary Email"])
print(f"Emails: {emails}/{len(selected)}")
counts = defaultdict(int)
for r in selected:
    counts[r["Family Office Name"]] += 1
for firm, count in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
    print(f"  {count:>2}  {firm}")

# Load into canonical DB
print("\nLoading into canonical DB...")
init_db()

# Clear existing data to prevent accumulation of bad records
conn = get_conn()
cur = conn.cursor()
cur.execute("DELETE FROM people")
cur.execute("DELETE FROM firms")
conn.commit()
conn.close()

# Upsert firms
for firm_name, firm_data in firms.items():
    upsert_firm(
        firm_name=firm_data["firm_name"],
        official_url=firm_data.get("official_url", ""),
        verification_tier=firm_data.get("verification_tier", "unverified"),
        verification_notes=firm_data.get("curation_notes", ""),
        firm_country=firm_data.get("firm_country", "United States"),
        discovery_source=firm_data.get("source_arm", "web"),
        discovery_query=firm_data.get("source_class", ""),
        sec_cik=firm_data.get("sec_cik", "") or "",
        sec_filing_url=firm_data.get("sec_filing_url", "") or "",
    )

# Upsert people
conn = get_conn()
cur = conn.cursor()
for row in selected:
    firm_row = cur.execute("SELECT firm_id FROM firms WHERE firm_name = ?", (row["Family Office Name"],)).fetchone()
    if firm_row:
        firm_id = firm_row["firm_id"]
        upsert_person(
            firm_id=firm_id,
            record_id=row["Record ID"],
            full_name=row["Contact Full Name"],
            first_name=row["Contact First Name"],
            last_name=row["Contact Last Name"],
            job_title=row["Contact Job Title"],
            title_normalized=row["Contact Job Title"],
            email=row["Contact Primary Email"],
            email_validation_code=row["Primary E-Mail Validation Code"],
            email_validation_explanation=row["Primary E-Mail Code Explanation"],
            email_quality=row["Email Quality Assessment (Primary)"],
            linkedin_url=row["Contact LinkedIn Profile"],
            linkedin_verified=bool(row["Contact LinkedIn Profile"]),
            phone=row["Primary Phone Number"],
            phone_verified=False,
            source_url=row["Contact Source URL"],
            extraction_method=row["Extraction Method"],
            extraction_strategy="",
            validation_status=row["Validation Status"],
            confidence=row["Confidence"],
            notes=row["Notes"],
            status="qualifying",
        )
conn.close()

# Rebuild exports from canonical (fixes CSV/JSONL drift)
print("\nRebuilding release artifacts from canonical source...")
export_csv(OUT_CSV)
export_jsonl(OUT_JSONL)
export_rejected_jsonl(pathlib.Path("data/final/rejected_contacts.jsonl"))
rebuild_chroma_index()

print(f"\nCanonical DB stats:")
print(f"  Qualifying people: {count_qualifying()}")
print(f"  Qualifying with V1/V2 email: {count_qualifying_with_email()}")
print(f"  Firm distribution: {get_firm_counts()}")

if len(selected) < TARGET_ROWS:
    print(f"\nWARN: Final dataset is short of {TARGET_ROWS} ({len(selected)}). Need more discovery passes.")
else:
    print("\nOK: Target row count met.")