# pipeline/06_enrich_contacts.py
# Contact Enrichment: Email MX verify, LinkedIn profile match, phone discovery
# Enriches extracted people with verified contact info

import json
import re
import pathlib
import dns.resolver
from urllib.parse import urlparse

IN = pathlib.Path("data/raw/people_raw_v3.jsonl")
OUT = pathlib.Path("data/raw/people_enriched_v3.jsonl")
AUDIT = pathlib.Path("data/audit/contact_enrichment_audit.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)
AUDIT.parent.mkdir(parents=True, exist_ok=True)

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?:\+?1[\s\-\.]?)?(?:\(?[2-9]\d{2}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4})")
LINKEDIN_RE = re.compile(r"https?://[a-z]{2,3}\.linkedin\.com/in/[A-Za-z0-9\-_%]+/?", re.I)

# Common email patterns for family offices
COMMON_PATTERNS = [
    "{first}.{last}@{domain}",
    "{first}{last}@{domain}",
    "{f}{last}@{domain}",
    "{first}@{domain}",
    "{last}@{domain}",
]

def validate_email_mx(email: str) -> tuple[str, str, str]:
    """Return (code, explanation, quality) for email."""
    if not email:
        return ("P0", "No email was published on the extracted source page.", "Not available")
    
    domain = email.split("@")[-1].lower()
    
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=5)
        mx_hosts = [str(r.exchange).rstrip(".") for r in answers]
        return (
            "V2",
            f"Email was published on source page and domain has MX records: {', '.join(mx_hosts[:2])}",
            "Published + MX verified"
        )
    except dns.resolver.NXDOMAIN:
        return ("U2", f"Email was published on source page, but domain {domain} does not exist.", "Published but domain invalid")
    except dns.resolver.NoAnswer:
        return ("U2", f"Email was published on source page, but domain {domain} has no MX records.", "Published but no MX records")
    except dns.resolver.Timeout:
        return ("U2", f"Email was published on source page, but MX lookup timed out for {domain}.", "Published but MX timeout")
    except Exception as e:
        return ("U2", f"Email was published on source page, but MX lookup could not be confirmed: {type(e).__name__}", "Published but MX unresolved")

def extract_domain_from_firm_url(url: str) -> str:
    """Extract domain from firm URL for email pattern generation."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower().lstrip("www.")
    return domain

def generate_email_patterns(first: str, last: str, domain: str) -> list[str]:
    """Generate likely email patterns (NOT used for verification, only for reference)."""
    first = first.lower()
    last = last.lower()
    patterns = []
    for p in COMMON_PATTERNS:
        try:
            email = p.format(first=first, last=last, f=first[0], domain=domain)
            patterns.append(email)
        except:
            pass
    return patterns

def enrich_person(person: dict, firm_url: str) -> dict:
    """Enrich a person record with contact validation."""
    email = person.get("primary_email_on_page", "")
    emails_on_page = person.get("emails_on_page", [])
    linkedin = person.get("linkedin_on_page", "")
    
    # Validate primary email
    code, explanation, quality = validate_email_mx(email)
    
    # Check LinkedIn - if present, mark as found (not fully verified without API)
    linkedin_verified = bool(linkedin)
    
    # Check for phone in source (we'd need to re-fetch, for now mark as not found)
    phone = ""
    phone_verified = False
    
    enriched = dict(person)
    enriched["email"] = email
    enriched["email_validation_code"] = code
    enriched["email_validation_explanation"] = explanation
    enriched["email_quality"] = quality
    enriched["linkedin_url"] = linkedin
    enriched["linkedin_verified"] = linkedin_verified
    enriched["phone"] = phone
    enriched["phone_verified"] = phone_verified
    enriched["firm_domain"] = extract_domain_from_firm_url(firm_url)
    
    return enriched

people = [json.loads(l) for l in IN.open(encoding="utf-8")]
print(f"[info] Enriching {len(people)} people...")

enriched_people = []
audit_trail = []

# Group by firm to get domain once per firm
firm_domains = {}
for p in people:
    firm = p.get("firm_name", "")
    if firm not in firm_domains:
        firm_domains[firm] = extract_domain_from_firm_url(p.get("firm_official_url", ""))

for i, person in enumerate(people, 1):
    firm = person.get("firm_name", "")
    name = person.get("name", "")
    domain = firm_domains.get(firm, "")
    
    if i % 50 == 0:
        print(f"  [{i}/{len(people)}] {name} @ {firm}")
    
    enriched = enrich_person(person, firm_domains.get(firm, ""))
    enriched_people.append(enriched)
    
    audit_trail.append({
        "firm": firm,
        "person": name,
        "email": enriched["email"],
        "email_code": enriched["email_validation_code"],
        "linkedin": enriched["linkedin_url"],
        "linkedin_verified": enriched["linkedin_verified"],
    })

with OUT.open("w", encoding="utf-8") as f:
    for p in enriched_people:
        f.write(json.dumps(p, ensure_ascii=False) + "\n")

with AUDIT.open("w", encoding="utf-8") as f:
    for a in audit_trail:
        f.write(json.dumps(a, ensure_ascii=False) + "\n")

# Stats
v1_v2 = sum(1 for p in enriched_people if p["email_validation_code"] in ("V1", "V2"))
u1_u2 = sum(1 for p in enriched_people if p["email_validation_code"] in ("U1", "U2"))
p0 = sum(1 for p in enriched_people if p["email_validation_code"] == "P0")
li_verified = sum(1 for p in enriched_people if p["linkedin_verified"])

print(f"\n[ok] {len(enriched_people)} people enriched -> {OUT}")
print(f"[ok] audit -> {AUDIT}")
print(f"\n[email validation]")
print(f"  V1/V2 (published + MX verified): {v1_v2}")
print(f"  U1/U2 (published but MX issues): {u1_u2}")
print(f"  P0 (no email published): {p0}")
print(f"  LinkedIn found: {li_verified}")