# pipeline/04b_curate_verified_firms.py
# Human-in-the-loop curation layer.
# The previous verification step was intentionally broad; this script narrows
# the firm pool to records that are defensible for the final dataset.

import json
import pathlib

IN = pathlib.Path("data/raw/firms_verified.jsonl")
OUT = pathlib.Path("data/raw/firms_curated.jsonl")
AUDIT = pathlib.Path("data/audit/firm_curation_audit.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)
AUDIT.parent.mkdir(parents=True, exist_ok=True)

# raw_name -> curated metadata.
# Conservative: keep firms that are either on their own domain or have clear
# firm-level family-office evidence. Exclude articles, YouTube, reports, and
# generic pages that only discuss family offices.
ALLOW = {
    "Matter Family Office": {
        "canonical_name": "Matter Family Office",
        "verification_tier": "official_domain_or_company_page",
        "notes": "Auto verifier initially found job-board page; manually patched to official domain based on search evidence and firm site.",
        "country": "United States",
    },
    "WE Family Offices": {
        "canonical_name": "WE Family Offices",
        "verification_tier": "official_domain",
        "notes": "Official site and LinkedIn evidence support family-office status.",
        "country": "United States",
    },
    "FCS Family Office": {
        "canonical_name": "FCS Family Office",
        "verification_tier": "official_domain",
        "notes": "Official FCS Private Wealth page describes family office services.",
        "country": "United States",
    },
    "Tailwind Advisors": {
        "canonical_name": "Tailwind Advisors",
        "verification_tier": "official_domain",
        "notes": "Official website self-describes as a multi-family office.",
        "country": "United States",
    },
    "DCA Family Office": {
        "canonical_name": "DCA Family Office",
        "verification_tier": "official_domain",
        "notes": "Official domain contains DCA Family Office pages and press releases.",
        "country": "United States",
    },
    "Blu Family Office": {
        "canonical_name": "Blu Family Office",
        "verification_tier": "official_domain",
        "notes": "Official Blu-FO domain and press evidence support firm identity.",
        "country": "United Kingdom",
    },
    "Angeles Family Office": {
        "canonical_name": "Angeles Family Office",
        "verification_tier": "official_or_related_domain",
        "notes": "Related Angeles domain contains private wealth/family office pages; use cautiously.",
        "country": "United States",
    },
    "Angeles Wealth": {
        "canonical_name": "Angeles Wealth",
        "verification_tier": "official_domain",
        "notes": "Official Angeles Investments site contains private wealth/family office material.",
        "country": "United States",
    },
    "TFO Family Office Partners": {
        "canonical_name": "TFO Family Office Partners",
        "verification_tier": "official_domain",
        "notes": "Official site and team page support status.",
        "country": "United States",
    },
    "Boston Family Office": {
        "canonical_name": "The Boston Family Office",
        "verification_tier": "official_domain",
        "notes": "Official site and team page support status.",
        "country": "United States",
    },
    "Callan Family Office": {
        "canonical_name": "Callan Family Office",
        "verification_tier": "official_domain",
        "notes": "Official site and team page support status.",
        "country": "United States",
    },
    "Billion Omnia Family Wealth": {
        "canonical_name": "Omnia Family Wealth",
        "verification_tier": "official_domain",
        "notes": "Extractor over-captured '$1.4 Billion'; canonicalized to Omnia Family Wealth.",
        "country": "United States",
    },
    "Tiempo Capital": {
        "canonical_name": "Tiempo Capital",
        "verification_tier": "official_domain",
        "notes": "Official site describes single-family/multi-family office positioning.",
        "country": "United States",
    },
    "Cresset Partners": {
        "canonical_name": "Cresset Partners",
        "verification_tier": "official_domain_or_related_cresset_site",
        "notes": "Cresset is broader wealth/private investment platform; include with medium confidence.",
        "country": "United States",
    },
}

# Explicitly rejected. Keeping this list is useful for the methodology:
# it proves we did not blindly trust the scraper.
REJECT = {
    "MPI Family Office": "YouTube page, not reliable official firm website for final dataset.",
    "Startup Mindset For Family Offices": "Article title, not a firm.",
    "Find Single Family Offices": "Article/listing page, not a firm.",
    "Rise Of The Family Office": "Article title, not a firm.",
    "Evolution Of Family Office": "Academic/article title, not a firm.",
    "Inside Wealth": "YouTube/media result, not a firm.",
    "UBS Global Family Office": "UBS division/report, not a standalone family office contact dataset target.",
    "Willoughby Capital Holdings": "Only third-party profile in current evidence; not enough contact evidence for this build.",
    "Horizon Family Office": "Only third-party profile in current evidence; not enough contact evidence for this build.",
}

kept = []
audit = []

with IN.open(encoding="utf-8") as f:
    for line in f:
        rec = json.loads(line)
        raw_name = rec["firm_name"]

        if raw_name in ALLOW:
            meta = ALLOW[raw_name]
            out = dict(rec)
            out["raw_firm_name"] = raw_name
            out["firm_name"] = meta["canonical_name"]
            out["verification_tier"] = meta["verification_tier"]
            out["curation_notes"] = meta["notes"]
            out["firm_country"] = meta["country"]
            kept.append(out)
            audit.append({
                "raw_firm_name": raw_name,
                "decision": "kept",
                "reason": meta["notes"],
                "official_url": rec.get("official_url", ""),
            })
        else:
            reason = REJECT.get(raw_name, "Not in curated allowlist for final 10-hour build.")
            audit.append({
                "raw_firm_name": raw_name,
                "decision": "rejected",
                "reason": reason,
                "official_url": rec.get("official_url", ""),
            })

with OUT.open("w", encoding="utf-8") as f:
    for rec in kept:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

with AUDIT.open("w", encoding="utf-8") as f:
    for rec in audit:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

print(f"[ok] kept {len(kept)} curated firms -> {OUT}")
print(f"[ok] wrote audit trail -> {AUDIT}")
print("\n[curated firms]")
for k in kept:
    print(f"  ✅ {k['firm_name']:<35} {k.get('official_url','')}")