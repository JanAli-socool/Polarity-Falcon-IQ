# pipeline/migrate_stage1.py
# Migrate Stage 1 CSV (26 qualifying records) into canonical SQLite.
# This becomes the single source of truth — all exports derive from here.

import csv
import pathlib
from pipeline.schema import (
    get_conn, upsert_firm, upsert_person, count_qualifying,
    count_qualifying_with_email, get_firm_counts, export_csv, export_jsonl,
    rebuild_chroma_index, now_iso
)

CSV_PATH = pathlib.Path("data/final/family_office_contacts.csv")

# Map Stage 1 firm names to canonical info
FIRM_INFO = {
    "Angeles Wealth": {
        "official_url": "https://www.angelesinvestments.com/",
        "verification_tier": "official_domain",
        "verification_notes": "Official Angeles Investments site contains private wealth/family office material.",
        "firm_country": "United States",
        "discovery_source": "web_search",
        "discovery_query": '"family office" appointed OR promoted OR joined 2024',
    },
    "Cresset Partners": {
        "official_url": "https://cressetpartners.com/private-equity/",
        "verification_tier": "official_domain_or_related_cresset_site",
        "verification_notes": "Cresset is broader wealth/private investment platform; include with medium confidence.",
        "firm_country": "United States",
        "discovery_source": "web_search",
        "discovery_query": '"multi-family office" founded OR established United States',
    },
    "Omnia Family Wealth": {
        "official_url": "https://omniawealth.com/newly-formed-florida-based-1-4-billion-omnia-family-wealth-launches-as-one-of-the-leading-independent-multi-family-offices-in-u-s/",
        "verification_tier": "official_domain",
        "verification_notes": "Extractor over-captured '$1.4 Billion'; canonicalized to Omnia Family Wealth.",
        "firm_country": "United States",
        "discovery_source": "web_search",
        "discovery_query": '"multi-family office" founded OR established United States',
    },
    "TFO Family Office Partners": {
        "official_url": "https://tfofamilyoffice.com/",
        "verification_tier": "official_domain",
        "verification_notes": "Official site and team page support status.",
        "firm_country": "United States",
        "discovery_source": "web_search",
        "discovery_query": '"family office" "team" OR "our people" site:*.com',
    },
    "The Boston Family Office": {
        "official_url": "https://www.bosfam.com/",
        "verification_tier": "official_domain",
        "verification_notes": "Official site and team page support status.",
        "firm_country": "United States",
        "discovery_source": "web_search",
        "discovery_query": '"family office" "team" OR "our people" site:*.com',
    },
    "WE Family Offices": {
        "official_url": "https://www.wefamilyoffices.com/",
        "verification_tier": "official_domain",
        "verification_notes": "Official site and LinkedIn evidence support family-office status.",
        "firm_country": "United States",
        "discovery_source": "web_search",
        "discovery_query": 'site:linkedin.com/company "family office" United States',
    },
}


def split_name(full_name: str):
    parts = full_name.strip().split()
    if len(parts) < 2:
        return full_name, ""
    return parts[0], parts[-1]


def normalize_title(title: str) -> str:
    """Extract clean role from verbose title."""
    if not title:
        return ""
    # If title is a bio sentence, try to extract the role
    title_lower = title.lower()
    role_keywords = [
        "chief investment officer", "chief executive officer", "chief financial officer",
        "chief operating officer", "chief compliance officer", "chief tax officer",
        "managing partner", "managing director", "founder", "partner",
        "portfolio manager", "director", "president", "ceo", "cfo", "cio", "coo",
        "senior managing director", "executive vice president", "vice president"
    ]
    for role in sorted(role_keywords, key=len, reverse=True):
        if role in title_lower:
            # Return properly capitalized
            return " ".join(w.capitalize() for w in role.split())
    return title


def main():
    print("[info] Migrating Stage 1 CSV to canonical DB...")

    # First, upsert all firms
    firm_ids = {}
    for firm_name, info in FIRM_INFO.items():
        fid = upsert_firm(
            firm_name=firm_name,
            official_url=info["official_url"],
            verification_tier=info["verification_tier"],
            verification_notes=info["verification_notes"],
            firm_country=info["firm_country"],
            discovery_source=info["discovery_source"],
            discovery_query=info["discovery_query"],
        )
        firm_ids[firm_name] = fid
        print(f"  Firm: {firm_name} -> ID {fid}")

    # Now migrate people from CSV
    with CSV_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, 1):
            firm_name = row["Family Office Name"]
            firm_id = firm_ids.get(firm_name)
            if not firm_id:
                print(f"  [warn] Unknown firm: {firm_name}, skipping")
                continue

            full_name = row["Contact Full Name"]
            first, last = split_name(full_name)
            title_normalized = normalize_title(row["Contact Job Title"])

            upsert_person(
                firm_id=firm_id,
                record_id=row["Record ID"],
                full_name=full_name,
                first_name=first,
                last_name=last,
                job_title=row["Contact Job Title"],
                title_normalized=title_normalized,
                email=row["Contact Primary Email"],
                email_validation_code=row["Primary E-Mail Validation Code"],
                email_validation_explanation=row["Primary E-Mail Code Explanation"],
                email_quality=row["Email Quality Assessment (Primary)"],
                linkedin_url=row["Contact LinkedIn Profile"],
                phone=row["Primary Phone Number"],
                source_url=row["Contact Source URL"],
                extraction_method=row["Extraction Method"],
                extraction_strategy="heading_tag_dom",
                validation_status=row["Validation Status"],
                confidence=row["Confidence"],
                notes=row["Notes"],
                status="qualifying",
            )
            print(f"  Person {i}: {full_name} @ {firm_name} -> {row['Record ID']}")

    print(f"\n[ok] Migration complete")
    print(f"Qualifying count: {count_qualifying()}")
    print(f"Qualifying with email (V1/V2): {count_qualifying_with_email()}")
    print(f"Firm distribution: {get_firm_counts()}")

    # Rebuild exports from canonical source (this fixes the CSV/JSONL drift)
    print("\n[info] Rebuilding release artifacts from canonical source...")
    export_csv(pathlib.Path("data/final/family_office_contacts.csv"))
    export_jsonl(pathlib.Path("data/final/family_office_contacts.jsonl"))
    rebuild_chroma_index()
    print("[ok] All artifacts rebuilt from single source of truth")


if __name__ == "__main__":
    main()