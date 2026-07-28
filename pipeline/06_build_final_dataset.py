# pipeline/06_build_final_dataset.py
# Builds final customer-facing CSV from noisy extracted people.
# Keeps only curated firms, deduplicates people, validates published emails,
# and writes a field-level validation trail.

import json
import csv
import re
import pathlib
from datetime import datetime, timezone
from collections import defaultdict

import dns.resolver

FIRMS = pathlib.Path("data/raw/firms_curated.jsonl")
PEOPLE = pathlib.Path("data/raw/people_raw.jsonl")

OUT_CSV = pathlib.Path("data/final/family_office_contacts.csv")
OUT_JSONL = pathlib.Path("data/final/family_office_contacts.jsonl")
AUDIT = pathlib.Path("data/audit/people_filter_audit.jsonl")

OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
AUDIT.parent.mkdir(parents=True, exist_ok=True)

TARGET_ROWS = 50   # keep the target, but if we come in short we ship what we honestly have
MIN_ACCEPTABLE = 35  # do not pad garbage to hit 50; ship what's verified

TITLE_KEYWORDS = [
    "president", "director", "officer", "partner", "principal", "founder",
    "manager", "advisor", "adviser", "associate", "analyst", "chief",
    "head", "managing", "executive", "chairman", "ceo", "cfo", "cio", "coo",
    "controller", "accountant", "counsel", "secretary", "treasurer",
    "vice president", "portfolio", "investment", "wealth", "family", "trust",
    "tax", "operations", "client", "planning", "compliance",
]

BAD_NAME_PARTS = [
    "family office", "capital partners", "wealth management", "private wealth",
    "investment management", "tax planning", "estate planning", "financial planning",
    "our team", "join our", "careers", "contact us", "read bio", "learn more",
    "client portal", "privacy policy", "terms", "services", "home", "about us",
    "newsletter", "subscribe", "download", "view all",
]

BAD_TITLE_PARTS = [
    "read bio", "learn more", "click here", "contact us", "privacy policy",
    "terms of use", "client portal", "subscribe",
]

def load_curated_firms():
    firms = {}
    raw_to_canonical = {}
    with FIRMS.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            canonical = rec["firm_name"]
            raw = rec.get("raw_firm_name", canonical)
            firms[canonical] = rec
            raw_to_canonical[raw] = canonical
            raw_to_canonical[canonical] = canonical
    return firms, raw_to_canonical

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

    # Require 2-4 tokens.
    parts = name.split()
    if len(parts) < 2 or len(parts) > 4:
        return False, "name token count not plausible"

    # Reject names with digits or obvious punctuation noise.
    if re.search(r"\d|@|/|\\|\|", name):
        return False, "name contains digit or symbol noise"

    # Require first and last token to look like person-name tokens.
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

    if len(title) > 120:
        return False, "title too long"

    if any(x in low for x in BAD_TITLE_PARTS):
        return False, "title contains non-title phrase"

    if not any(k in low for k in TITLE_KEYWORDS):
        return False, "title lacks role keyword"

    return True, ""

def validate_email(email):
    email = clean_text(email)
    if not email:
        return {
            "email": "",
            "code": "P0",
            "explanation": "No email was published on the extracted source page.",
            "quality": "Not available",
        }

    domain = email.split("@")[-1].lower()

    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=4)
        mx_hosts = [str(r.exchange).rstrip(".") for r in answers]
        return {
            "email": email,
            "code": "V2",
            "explanation": f"Email was published on source page and domain has MX records: {', '.join(mx_hosts[:2])}",
            "quality": "Published + MX verified",
        }
    except Exception as e:
        return {
            "email": email,
            "code": "U2",
            "explanation": f"Email was published on source page, but MX lookup could not be confirmed: {type(e).__name__}",
            "quality": "Published but domain mail validation unresolved",
        }

def confidence_for(row):
    score = 0
    if row["Contact Job Title"]:
        score += 1
    if row["Contact Primary Email"]:
        score += 1
    if "team" in row["Contact Source URL"].lower() or "people" in row["Contact Source URL"].lower():
        score += 1
    if row["Firm Verification Tier"].startswith("official"):
        score += 1

    if score >= 3:
        return "high"
    if score == 2:
        return "medium"
    return "low"

firms, raw_to_canonical = load_curated_firms()

kept_by_firm = defaultdict(list)
audit = []
seen = set()

with PEOPLE.open(encoding="utf-8") as f:
    for line in f:
        p = json.loads(line)
        raw_firm = p.get("firm_name", "")
        if raw_firm not in raw_to_canonical:
            audit.append({
                "decision": "rejected",
                "reason": "firm not in curated firm list",
                "person": p.get("name", ""),
                "firm": raw_firm,
                "source_url": p.get("source_url", ""),
            })
            continue

        canonical = raw_to_canonical[raw_firm]
        firm = firms[canonical]

        name = clean_text(p.get("name", ""))
        title = clean_text(p.get("title", ""))

        ok, reason = plausible_name(name)
        if not ok:
            audit.append({
                "decision": "rejected",
                "reason": reason,
                "person": name,
                "firm": canonical,
                "source_url": p.get("source_url", ""),
            })
            continue

        ok, reason = plausible_title(title)
        if not ok:
            audit.append({
                "decision": "rejected",
                "reason": reason,
                "person": name,
                "firm": canonical,
                "source_url": p.get("source_url", ""),
            })
            continue

        key = (canonical.lower(), name.lower())
        if key in seen:
            audit.append({
                "decision": "rejected",
                "reason": "duplicate person within firm",
                "person": name,
                "firm": canonical,
                "source_url": p.get("source_url", ""),
            })
            continue
        seen.add(key)

        first, last = split_name(name)
        email_info = validate_email(p.get("email_on_page", ""))

        row = {
            "Record ID": "",
            "Family Office Name": canonical,
            "Family Office City": "",
            "Family Office State / Region": "",
            "Family Office Country": firm.get("firm_country", ""),
            "Contact First Name": first,
            "Contact Last Name": last,
            "Contact Full Name": name,
            "Contact Job Title": title,
            "Contact Location": "",
            "Contact LinkedIn Profile": p.get("linkedin_on_page", "") or "",
            "Contact Primary Email": email_info["email"],
            "Primary E-Mail Validation Code": email_info["code"],
            "Primary E-Mail Code Explanation": email_info["explanation"],
            "Email Quality Assessment (Primary)": email_info["quality"],
            "Primary Phone Number": "",
            "Contact Secondary Email": "",
            "Secondary E-Mail Validation Code": "P0",
            "E-Mail Code Explanation": "No secondary email was extracted from the public source page.",
            "Email Quality Assessment (Secondary)": "Not available",
            "Secondary Phone Number": "",
            "Firm Verification URL": firm.get("official_url", ""),
            "Firm Verification Tier": firm.get("verification_tier", ""),
            "Firm Verification Notes": firm.get("curation_notes", ""),
            "Contact Source URL": p.get("source_url", ""),
            "Extraction Method": "Automated HTML extraction from verified firm page, then rule-based filtering.",
            "Validation Status": "verified_name_title_from_source_page",
            "Confidence": "",
            "Notes": "Blank cells mean the pipeline could not verify the field from public evidence.",
            "Last Verified Date": datetime.now(timezone.utc).date().isoformat(),
        }

        row["Confidence"] = confidence_for(row)
        kept_by_firm[canonical].append(row)

# Select records with diversity: cap per firm first, then fill if needed.
selected = []

# First pass: up to 5 per firm.
for firm_name, rows in sorted(kept_by_firm.items()):
    # Prefer rows from team/about pages and rows with emails.
    rows = sorted(
        rows,
        key=lambda r: (
            1 if r["Contact Primary Email"] else 0,
            1 if ("team" in r["Contact Source URL"].lower() or "people" in r["Contact Source URL"].lower()) else 0,
            1 if r["Confidence"] == "high" else 0,
        ),
        reverse=True,
    )
    selected.extend(rows[:5])

# If still short, fill with additional rows from firms already used.
# Report the final count honestly — do NOT pad below-quality rows to hit target.
if len(selected) < MIN_ACCEPTABLE:
    print(f"\n[warn] final dataset has {len(selected)} rows, below floor {MIN_ACCEPTABLE}.")
    print("[warn] Consider a supplementary discovery pass before shipping.")
elif len(selected) < TARGET_ROWS:
    print(f"\n[ok] {len(selected)} verified rows (target was {TARGET_ROWS}). Shipping honestly rather than padding.")
else:
    print("\n[ok] target row count met.")

selected = selected[:TARGET_ROWS]

# Add IDs
for i, row in enumerate(selected, 1):
    row["Record ID"] = f"FOC_{i:03d}"

# Write final files
fieldnames = list(selected[0].keys()) if selected else []

with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(selected)

with OUT_JSONL.open("w", encoding="utf-8") as f:
    for row in selected:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

with AUDIT.open("w", encoding="utf-8") as f:
    for rec in audit:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

print(f"[ok] final dataset rows: {len(selected)} -> {OUT_CSV}")
print(f"[ok] jsonl copy -> {OUT_JSONL}")
print(f"[ok] people filter audit -> {AUDIT}")

print("\n[rows by firm]")
counts = defaultdict(int)
emails = 0
for r in selected:
    counts[r["Family Office Name"]] += 1
    if r["Contact Primary Email"]:
        emails += 1

for firm, count in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
    print(f"  {count:>2}  {firm}")

print(f"\n[stats] published primary emails in final dataset: {emails}/{len(selected)}")
print("[stats] firms represented:", len(counts))

if len(selected) < TARGET_ROWS:
    print(f"\n[warn] final dataset is short of {TARGET_ROWS}. We may need a LinkedIn-search supplement.")
else:
    print("\n[ok] target row count met.")