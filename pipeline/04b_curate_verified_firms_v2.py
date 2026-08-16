# pipeline/04b_curate_verified_firms_v2.py
# Human-in-the-loop curation layer for Stage 2 verified firms.
# Keeps firms that are either on their own domain or have clear
# firm-level family-office evidence. Excludes articles, YouTube, reports,
# and generic pages that only discuss family offices.

import json
import pathlib

IN = pathlib.Path("data/raw/firms_verified_v2.jsonl")
OUT = pathlib.Path("data/raw/firms_curated_v2.jsonl")
AUDIT = pathlib.Path("data/audit/firm_curation_v2_audit.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)
AUDIT.parent.mkdir(parents=True, exist_ok=True)

# Verified firms from Stage 2 + original Stage 1 firms
# Conservative: keep firms that are on their own domain or have clear
# firm-level family-office evidence.
ALLOW = {
    # Original Stage 1 firms (already validated)
    "Angeles Wealth": {
        "canonical_name": "Angeles Wealth",
        "verification_tier": "official_domain",
        "notes": "Official Angeles Investments site contains private wealth/family office material.",
        "country": "United States",
    },
    "Cresset Partners": {
        "canonical_name": "Cresset Partners",
        "verification_tier": "official_domain_or_related_cresset_site",
        "notes": "Cresset is broader wealth/private investment platform; include with medium confidence.",
        "country": "United States",
    },
    "Omnia Family Wealth": {
        "canonical_name": "Omnia Family Wealth",
        "verification_tier": "official_domain",
        "notes": "Official Omnia Wealth site and team page support family office status.",
        "country": "United States",
    },
    "TFO Family Office Partners": {
        "canonical_name": "TFO Family Office Partners",
        "verification_tier": "official_domain",
        "notes": "Official site and team page support status.",
        "country": "United States",
    },
    "The Boston Family Office": {
        "canonical_name": "The Boston Family Office",
        "verification_tier": "official_domain",
        "notes": "Official site and team page support status.",
        "country": "United States",
    },
    "WE Family Offices": {
        "canonical_name": "WE Family Offices",
        "verification_tier": "official_domain",
        "notes": "Official site and LinkedIn evidence support family-office status.",
        "country": "United States",
    },
    # Stage 2 verified firms
    "FORCE Family Office": {
        "canonical_name": "FORCE Family Office",
        "verification_tier": "official_domain",
        "notes": "Official domain forcefamilyoffice.com self-describes as family office.",
        "country": "United States",
    },
    "Potentum Partners": {
        "canonical_name": "Potentum Partners",
        "verification_tier": "official_domain",
        "notes": "Official domain potentumpartners.com self-describes as family office.",
        "country": "United States",
    },
    "Family Office Legacy": {
        "canonical_name": "Family Office Legacy",
        "verification_tier": "official_domain",
        "notes": "Official domain legacyfamilyoffice.ca self-describes as family office.",
        "country": "Canada",
    },
    "Agreus": {
        "canonical_name": "Agreus",
        "verification_tier": "official_or_related_domain",
        "notes": "Found via agreusgroup.com; self-describes as family office recruiter/advisor.",
        "country": "United Kingdom",
    },
    "GANDT Family Office": {
        "canonical_name": "GANDT Family Office",
        "verification_tier": "official_or_related_domain",
        "notes": "Found via seamless.ai; self-describes as family office.",
        "country": "United States",
    },
    "Miami Family Office": {
        "canonical_name": "Miami Family Office",
        "verification_tier": "official_domain",
        "notes": "Official domain themiamifamilyoffice.com self-describes as family office.",
        "country": "United States",
    },
    "Ligo Partners Family Office": {
        "canonical_name": "Ligo Partners Family Office",
        "verification_tier": "official_or_related_domain",
        "notes": "Found via archtown.org; self-describes as family office.",
        "country": "United States",
    },
    "SKG Family Office": {
        "canonical_name": "SKG Family Office",
        "verification_tier": "official_domain",
        "notes": "Official domain skgfamilyoffice.com self-describes as family office.",
        "country": "United States",
    },
    "Ideology Multi-Family Office": {
        "canonical_name": "Ideology Multi-Family Office",
        "verification_tier": "official_domain",
        "notes": "Official domain ideologymfo.com self-describes as multi-family office.",
        "country": "United States",
    },
    "Turnstone Multi-Family Office": {
        "canonical_name": "Turnstone Multi-Family Office",
        "verification_tier": "official_domain",
        "notes": "Official domain turnstone-group.com self-describes as multi-family office.",
        "country": "United States",
    },
    "Mosaic Family Office": {
        "canonical_name": "Mosaic Family Office",
        "verification_tier": "official_domain",
        "notes": "Official domain mosaic.co.za self-describes as family office.",
        "country": "South Africa",
    },
    "INTI Multi-Family Office": {
        "canonical_name": "INTI Multi-Family Office",
        "verification_tier": "official_domain",
        "notes": "Official domain inti.llc self-describes as multi-family office.",
        "country": "United States",
    },
    "WSL Family Office": {
        "canonical_name": "WSL Family Office",
        "verification_tier": "official_or_related_domain",
        "notes": "Found via wslfamilyoffice.com; self-describes as family office.",
        "country": "United States",
    },
    "United Multi-Family Office": {
        "canonical_name": "United Multi-Family Office",
        "verification_tier": "official_domain",
        "notes": "Official domain unitedmfo.com.br self-describes as multi-family office.",
        "country": "Brazil",
    },
    "Conscience Multi Family Office": {
        "canonical_name": "Conscience Multi Family Office",
        "verification_tier": "official_or_related_domain",
        "notes": "Found via consciencemfo.com; self-describes as multi-family office.",
        "country": "United States",
    },
    "Udyat Ventures": {
        "canonical_name": "Udyat Ventures",
        "verification_tier": "official_domain",
        "notes": "Official domain udyat.com self-describes as family office.",
        "country": "United States",
    },
    "Sten Multi-Family Office": {
        "canonical_name": "Sten Multi-Family Office",
        "verification_tier": "official_domain",
        "notes": "Official domain sten-mfo.com self-describes as multi-family office.",
        "country": "United States",
    },
    "First Growth Multi-Family Office": {
        "canonical_name": "First Growth Multi-Family Office",
        "verification_tier": "official_domain",
        "notes": "Official domain fgmfo.com self-describes as multi-family office.",
        "country": "United States",
    },
    "Campden Family Connect": {
        "canonical_name": "Campden Family Connect",
        "verification_tier": "official_domain",
        "notes": "Official domain campdenfamilyconnect.com self-describes as family office network.",
        "country": "United Kingdom",
    },
    "SAAGA Family Wealth": {
        "canonical_name": "SAAGA Family Wealth",
        "verification_tier": "official_or_related_domain",
        "notes": "Found via leadiq.com; self-describes as family wealth office.",
        "country": "United States",
    },
    "Family Office Exchange": {
        "canonical_name": "Family Office Exchange",
        "verification_tier": "official_or_related_domain",
        "notes": "Official domain familyoffice.com is an industry network, not a single FO; include for context.",
        "country": "United States",
    },
    "Matter Family Office": {
        "canonical_name": "Matter Family Office",
        "verification_tier": "official_domain",
        "notes": "Official domain matterfamilyoffice.com self-describes as family office.",
        "country": "United States",
    },
    "Beacon Family Office": {
        "canonical_name": "Beacon Family Office",
        "verification_tier": "official_domain",
        "notes": "Official domain beaconfos.com self-describes as family office.",
        "country": "United States",
    },
    "Boreal Family Office": {
        "canonical_name": "Boreal Family Office",
        "verification_tier": "official_domain",
        "notes": "Official domain borealfo.com self-describes as family office.",
        "country": "United States",
    },
}

# Explicitly rejected from verified list
REJECT = {
    "Corvalier Trust Company": "No family office self-description on official site.",
    "Compass Real Estate": "Real estate firm, not a family office.",
    "VanHove Multi Family office": "No verifiable official site found.",
    "Education Global Capital": "No family office self-description on official site.",
    "Ennea": "No family office self-description on official site.",
    "Lelapa Multi-family Office": "No family office self-description on official site.",
    "IWP Family Office": "HTTP 404 on official site.",
    "Ascentum": "No family office self-description on official site.",
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
            reason = REJECT.get(raw_name, "Not in curated allowlist for final build.")
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
    print(f"  OK {k['firm_name']:<45} {k.get('verification_tier','')}  {k.get('official_url','')}")