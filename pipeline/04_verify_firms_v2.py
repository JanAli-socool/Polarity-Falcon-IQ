# pipeline/04_verify_firms_v2.py
# Firm Verification v2: Official site + self-description + cross-source corroboration
# For each candidate firm, find its OWN website and verify it self-identifies as a family office.
# Cross-references web discovery with SEC EDGAR for stronger verification.

import json
import re
import time
import pathlib
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

IN_WEB = pathlib.Path("data/raw/firm_candidates_v3.jsonl")
IN_SEC = pathlib.Path("data/raw/sec_seed_v2.jsonl")
OUT = pathlib.Path("data/raw/firms_verified_v2.jsonl")
AUDIT = pathlib.Path("data/audit/firm_verification_v2_audit.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)
AUDIT.parent.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0 (research; contact@example.com)"}
ddgs = DDGS()

# SEC filings that are clearly not family offices (public companies, etc.)
SEC_NON_FO_TOKENS = {
    "inc", "inc.", "incorporated", "corp", "corp.", "corporation",
    "ltd", "ltd.", "limited", "llc", "l.l.c.", "lp", "l.p.",
    "pharma", "pharmaceuticals", "biopharma", "therapeutics",
    "health", "healthcare", "medical", "pharma", "drug",
    "technology", "tech", "software", "systems", "solutions",
    "holdings", "acquisition", "venture", "capital", "partners",
    "fund", "trust", "series", "etf", "reit", "royalty",
    "express", "petmed", "maning", "napier", "amtech", "ckx",
    "gulf island", "wilmington", "hartford", "scully", "nextnav",
    "raytech", "synalloy", "hertz", "nls", "sunstone", "avanti",
    "advisers investment", "music licensing", "bridger", "powerup",
    "general cannabis", "sma relationship",
}

# Load web-discovered candidates
web_candidates = []
with IN_WEB.open(encoding="utf-8") as f:
    for line in f:
        c = json.loads(line)
        web_candidates.append({
            "name": c["firm_name"],
            "source_arm": "web",
            "source_class": c["source_class"],
            "source_url": c["source_url"],
            "source_domain": c["source_domain"],
            "discovered_at": c["discovered_at"],
        })

# Load SEC candidates
sec_candidates = []
if IN_SEC.exists():
    with IN_SEC.open(encoding="utf-8") as f:
        for line in f:
            s = json.loads(line)
            for name in s.get("display_names", [])[:1]:
                clean = re.sub(r"\s*/.*$", "", name).strip()
                if not clean:
                    continue
                # Filter out obvious non-family-office SEC filings
                low = clean.lower()
                if any(tok in low for tok in SEC_NON_FO_TOKENS):
                    continue
                if not any(kw in low for kw in ["family office", "single family", "multi family", "family wealth", "family investment"]):
                    # Only keep if the filing explicitly mentions family office
                    continue
                sec_candidates.append({
                    "name": clean,
                    "source_arm": "sec",
                    "cik": s["cik"],
                    "filing_url": s["filing_url"],
                    "form": s.get("form", ""),
                    "file_date": s.get("file_date", ""),
                })

print(f"[info] {len(web_candidates)} web candidates, {len(sec_candidates)} SEC candidates")

# Merge: prefer web candidates (have source URLs), augment with SEC CIK if name matches
merged = {}
for c in web_candidates:
    key = c["name"].lower()
    merged[key] = c

for c in sec_candidates:
    key = c["name"].lower()
    if key in merged:
        merged[key]["sec_cik"] = c["cik"]
        merged[key]["sec_filing_url"] = c["filing_url"]
        merged[key]["sec_form"] = c.get("form", "")
        merged[key]["sec_file_date"] = c.get("file_date", "")
    else:
        # SEC-only candidate
        merged[key] = c

candidates = list(merged.values())

# Skip generic/junk names
GENERIC = {
    "family office", "single family office", "multi family office", "family offices",
    "family wealth", "wealth management", "private wealth", "investment management",
    "capital partners", "global family office", "united states family offices",
    "core family office", "future family office", "us family office",
    "the family office", "family office team", "family office leadership",
}
# SEC filings that are clearly not family offices (public companies, etc.)
SEC_NON_FO_TOKENS = {
    "inc", "inc.", "incorporated", "corp", "corp.", "corporation",
    "ltd", "ltd.", "limited", "llc", "l.l.c.", "lp", "l.p.",
    "pharma", "pharmaceuticals", "biopharma", "therapeutics",
    "health", "healthcare", "medical", "pharma", "drug",
    "technology", "tech", "software", "systems", "solutions",
    "holdings", "acquisition", "venture", "capital", "partners",
    "fund", "trust", "series", "etf", "reit", "royalty",
    "express", "petmed", "maning", "napier", "amtech", "ckx",
    "gulf island", "wilmington", "hartford", "scully", "nextnav",
    "raytech", "synalloy", "hertz", "nls", "sunstone", "avanti",
    "advisers investment", "music licensing", "bridger", "powerup",
    "general cannabis", "sma relationship",
}
candidates = [c for c in candidates if c["name"].lower() not in GENERIC and len(c["name"]) >= 5]

# Sort by priority: web_firm_team_page first, then linkedin_company, then SEC, then others
source_priority = {
    "web_firm_team_page": 5,
    "linkedin_company": 4,
    "web_news_appointments": 3,
    "sec": 2,
    "web_industry_coverage": 1,
    "web_industry_events": 1,
}
candidates.sort(key=lambda c: source_priority.get(c.get("source_class", ""), 0), reverse=True)

# Cap for time budget
BUDGET = 1000
candidates = candidates[:BUDGET]

print(f"[info] {len(candidates)} candidates to verify (merged web+SEC)")

# Known family office domains for quick matching
KNOWN_FO_DOMAINS = {
    "angelesinvestments.com": "Angeles Wealth",
    "cressetpartners.com": "Cresset Partners",
    "omniawealth.com": "Omnia Family Wealth",
    "tfofamilyoffice.com": "TFO Family Office Partners",
    "bosfam.com": "The Boston Family Office",
    "wefamilyoffices.com": "WE Family Offices",
    "matterfamilyoffice.com": "Matter Family Office",
    "fcsprivatewealth.com": "FCS Family Office",
    "tailwindadvisors.com": "Tailwind Advisors",
    "dcafamilyoffice.com": "DCA Family Office",
    "blufo.com": "Blu Family Office",
    "tiempocapital.com": "Tiempo Capital",
    "callan.com": "Callan Family Office",
    "forcefamilyoffice.com": "FORCE Family Office",
    "corvalier.com": "Corvalier Trust Company",
    "potentumpartners.com": "Potentum Partners",
    "legacyfamilyoffice.ca": "Family Office Legacy",
    "themiamifamilyoffice.com": "Miami Family Office",
    "skgfamilyoffice.com": "SKG Family Office",
    "ideologymfo.com": "Ideology Multi-Family Office",
    "turnstone-group.com": "Turnstone Multi-Family Office",
    "mosaic.co.za": "Mosaic Family Office",
    "inti.llc": "INTI Multi-Family Office",
    "slfamilyoffice.com": "WSL Family Office",
    "unitedmfo.com.br": "United Multi-Family Office",
    "udyat.com": "Udyat Ventures",
    "sten-mfo.com": "Sten Multi-Family Office",
    "fgmfo.com": "First Growth Multi-Family Office",
    "campdenfamilyconnect.com": "Campden Family Connect",
    "beaconfos.com": "Beacon Family Office",
    "borealfo.com": "Boreal Family Office",
}

def find_official_site(firm_name: str) -> tuple[str, str] | None:
    """Return (url, title) of best-guess official site, or None."""
    try:
        results = ddgs.text(f'"{firm_name}" official site', max_results=5)
    except Exception:
        return None
    firm_tokens = set(re.findall(r"[a-z]{3,}", firm_name.lower()))
    for r in results:
        url = r.get("href", "")
        domain = urlparse(url).netloc.lower().lstrip("www.")
        # Skip social/aggregator platforms
        if any(s in domain for s in ["linkedin", "facebook", "twitter", "wikipedia",
                                      "bloomberg", "forbes", "cnbc", "sec.gov",
                                      "tracxn", "axial", "crunchbase", "pitchbook"]):
            continue
        # Prefer domains whose name overlaps with firm tokens
        dom_tokens = set(re.findall(r"[a-z]{3,}", domain))
        if firm_tokens & dom_tokens:
            return url, r.get("title", "")
    # Fallback: first non-social result
    for r in results:
        url = r.get("href", "")
        domain = urlparse(url).netloc.lower().lstrip("www.")
        if not any(s in domain for s in ["linkedin", "facebook", "twitter", "wikipedia"]):
            return url, r.get("title", "")
    return None

def site_confirms_fo(url: str) -> tuple[bool, str, str]:
    """Fetch URL; return (True, snippet, page_title) if site self-describes as family office."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        if r.status_code != 200:
            return False, f"http {r.status_code}", ""
        soup = BeautifulSoup(r.text, "html.parser")
        page_title = soup.title.string.strip() if soup.title else ""
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = re.sub(r"\s+", " ", soup.get_text(" "))
        low = text.lower()
        for phrase in ["family office", "single-family office", "multi-family office",
                       "family-owned investment", "family wealth", "multi family office"]:
            if phrase in low:
                i = low.find(phrase)
                snippet = text[max(0, i-60):i+120].strip()
                return True, snippet, page_title
        return False, "no FO self-description", page_title
    except Exception as e:
        return False, f"fetch error: {type(e).__name__}", ""

def check_sec_corroboration(firm_name: str, sec_cik: str = "") -> tuple[bool, str]:
    """Check if SEC filing corroborates family office status."""
    if not sec_cik:
        return False, ""
    try:
        # Check if the SEC filing mentions family office
        url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={sec_cik}&type=ADV&dateb=&owner=include&count=10"
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            low = r.text.lower()
            if "family office" in low or "single family" in low or "multi-family" in low:
                return True, f"SEC ADV filing for CIK {sec_cik} references family office"
    except Exception:
        pass
    return False, ""

verified = []
audit_trail = []

for i, cand in enumerate(candidates, 1):
    name = cand["name"]
    print(f"[{i:>3}/{len(candidates)}] {name[:50]:<50}", end=" ", flush=True)
    
    # Check if we already know this firm's domain
    known_domain = None
    for domain, known_name in KNOWN_FO_DOMAINS.items():
        if known_name.lower() == name.lower():
            known_domain = domain
            break
    
    if known_domain:
        url = f"https://{known_domain}"
        ok, evidence, page_title = site_confirms_fo(url)
        if ok:
            print(f"VERIFIED (known)  {urlparse(url).netloc}")
            verification_tier = "official_domain"
            notes = "Known family office domain verified via self-description"
            sec_corroborated = False
            sec_note = ""
            if cand.get("sec_cik"):
                sec_corroborated, sec_note = check_sec_corroboration(name, cand["sec_cik"])
                if sec_corroborated:
                    verification_tier = "official_domain"
                    notes += "; SEC corroborated"
            verified.append({
                "firm_name": name,
                "official_url": url,
                "official_title": page_title,
                "self_description_snippet": evidence,
                "source_arm": cand["source_arm"],
                "source_class": cand.get("source_class", ""),
                "source_url": cand.get("source_url", ""),
                "verification_tier": verification_tier,
                "verification_notes": notes,
                "sec_cik": cand.get("sec_cik"),
                "sec_filing_url": cand.get("sec_filing_url"),
                "sec_corroborated": sec_corroborated,
                "web_domains": [],
                "web_evidence": [],
            })
            audit_trail.append({
                "firm_name": name,
                "decision": "verified",
                "tier": verification_tier,
                "url": url,
                "reason": notes,
            })
            time.sleep(0.5)
            continue
    
    site = find_official_site(name)
    if not site:
        print("no site found")
        audit_trail.append({
            "firm_name": name,
            "decision": "failed",
            "reason": "no official site found",
        })
        continue
    
    url, title = site
    ok, evidence, page_title = site_confirms_fo(url)
    
    # Check SEC corroboration
    sec_corroborated = False
    sec_note = ""
    if cand.get("sec_cik"):
        sec_corroborated, sec_note = check_sec_corroboration(name, cand["sec_cik"])
    
    if ok:
        # Determine verification tier
        domain = urlparse(url).netloc.lower().lstrip("www.")
        firm_tokens = set(re.findall(r"[a-z]{3,}", name.lower()))
        dom_tokens = set(re.findall(r"[a-z]{3,}", domain))
        
        if firm_tokens & dom_tokens:
            if sec_corroborated:
                verification_tier = "official_domain"
                notes = "Official domain matches firm name; self-describes as FO; SEC corroborated"
            else:
                verification_tier = "official_domain"
                notes = "Official domain matches firm name; self-describes as FO"
        else:
            if sec_corroborated:
                verification_tier = "official_or_related_domain"
                notes = "Domain doesn't perfectly match but self-describes as FO; SEC corroborated"
            else:
                verification_tier = "official_or_related_domain"
                notes = "Domain doesn't perfectly match firm name; self-describes as FO"
        
        print(f"VERIFIED ({verification_tier})  {domain}")
        verified.append({
            "firm_name": name,
            "official_url": url,
            "official_title": page_title or title,
            "self_description_snippet": evidence,
            "source_arm": cand["source_arm"],
            "source_class": cand.get("source_class", ""),
            "source_url": cand.get("source_url", ""),
            "verification_tier": verification_tier,
            "verification_notes": notes,
            "sec_cik": cand.get("sec_cik"),
            "sec_filing_url": cand.get("sec_filing_url"),
            "sec_corroborated": sec_corroborated,
            "web_domains": [],
            "web_evidence": [],
        })
        audit_trail.append({
            "firm_name": name,
            "decision": "verified",
            "tier": verification_tier,
            "url": url,
            "reason": notes,
        })
    else:
        print(f"FAILED: {evidence[:40]}")
        audit_trail.append({
            "firm_name": name,
            "decision": "failed",
            "reason": evidence,
            "url": url,
        })
    
    time.sleep(0.5)

with OUT.open("w", encoding="utf-8") as f:
    for v in verified:
        f.write(json.dumps(v, ensure_ascii=False) + "\n")

with AUDIT.open("w", encoding="utf-8") as f:
    for a in audit_trail:
        f.write(json.dumps(a, ensure_ascii=False) + "\n")

print(f"\n[ok] {len(verified)} firms VERIFIED via their own website -> {OUT}")
print(f"[ok] Audit trail -> {AUDIT}")
print(f"\n[verified firms]")
for v in verified:
    domain = urlparse(v['official_url']).netloc
    print(f"  OK {v['firm_name']:<45}  {v['verification_tier']}  {domain}")

# Summary by tier
from collections import Counter
tier_counts = Counter(v["verification_tier"] for v in verified)
print(f"\n[verification tiers]")
for tier, count in tier_counts.most_common():
    print(f"  {count:>2}  {tier}")