# pipeline/02_extract_firms_v2.py
# Extract candidate firms from expanded discovery hits — cleaned up version.

import json
import re
import pathlib
from collections import Counter

IN = pathlib.Path("data/raw/discovery_expanded.jsonl")
OUT = pathlib.Path("data/raw/firm_candidates_v2.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

# More precise patterns for firm names
# Focus on patterns that appear in firm self-descriptions
PATTERNS = [
    # "X Family Office" or "X Family Offices" - most reliable
    r"\b([A-Z][A-Za-z'’\-]{2,}(?:\s+[A-Z][A-Za-z'’\-]{2,}){0,2})\s+Family\s+Office(?:s)?\b",
    # "The X Family Office"
    r"\bThe\s+([A-Z][A-Za-z'’\-]{2,}(?:\s+[A-Z][A-Za-z'’\-]{2,}){0,2})\s+Family\s+Office\b",
    # "X Capital" / "X Partners" / "X Holdings" etc. but ONLY when preceded by family office context
    r"(?:family\s+office\s+(?:called|named|:)\s+)([A-Z][A-Za-z'’\-]{2,}(?:\s+[A-Z][A-Za-z'’\-]{2,}){0,2}\s+(?:Capital|Partners|Holdings|Ventures|Wealth|Group|Advisors?|Investments?|Office))",
    # "X Wealth" / "X Family Wealth" in family office context
    r"(?:family\s+office\s+(?:called|named|:)\s+)([A-Z][A-Za-z'’\-]{2,}(?:\s+[A-Z][A-Za-z'’\-]{2,}){0,2}\s+(?:Wealth|Family\s+Wealth))",
]

# For LinkedIn company pages - extract company name from title
LINKEDIN_PATTERN = r"^([A-Z][A-Za-z'’\-]{2,}(?:\s+[A-Z][A-Za-z'’\-]{2,}){0,3})\s*[\|\-]\s*LinkedIn"

# Noise to skip entirely
SKIP_DOMAINS = {
    "linkedin.com", "facebook.com", "twitter.com", "x.com", "wikipedia.org",
    "bloomberg.com", "forbes.com", "cnbc.com", "sec.gov", "tracxn.com",
    "axial.com", "crunchbase.com", "pitchbook.com", "youtube.com",
    "instagram.com", "glassdoor.com", "indeed.com", "ziprecruiter.com",
}

# Generic/junk names to reject
GENERIC_REJECT = {
    "family office", "single family office", "multi family office",
    "family offices", "family wealth", "wealth management",
    "private wealth", "investment management", "capital partners",
    "global family office", "united states family offices",
    "core family office", "future family office", "us family office",
    "the family office", "family office team", "family office leadership",
    "our team", "our people", "meet the team", "leadership team",
    "join our team", "careers", "contact us", "about us", "home",
    "services", "insights", "news", "press", "blog", "resources",
}

STOP_TOKENS = {
    "the", "a", "an", "our", "your", "their", "his", "her", "its",
    "team", "people", "leadership", "staff", "professionals", "principals",
    "meet", "join", "careers", "about", "contact", "home", "services",
    "news", "press", "blog", "insights", "resources", "family", "office",
    "offices", "capital", "partners", "group", "wealth", "advisors",
    "investments", "holdings", "ventures", "single", "multi", "global",
    "united", "international", "american", "british", "private", "management",
    "planning", "solutions", "strategies", "founded", "established",
    "launched", "created", "built", "based", "located", "headquartered",
    "operating", "serving", "clients", "page", "site", "website",
    "overview", "profile", "company", "firm", "business", "organization",
}

def clean_text_for_extraction(text: str) -> str:
    """Remove navigation/UI boilerplate from snippet."""
    if not text:
        return ""
    # Remove common UI phrases
    ui_phrases = [
        "skip to main content", "skip to navigation", "main menu", "search",
        "sign in", "log in", "register", "subscribe", "download", "read more",
        "learn more", "view all", "show more", "load more", "see all",
        "privacy policy", "terms of use", "cookie policy", "accessibility",
    ]
    low = text.lower()
    for phrase in ui_phrases:
        low = low.replace(phrase, " ")
    # Collapse whitespace
    return re.sub(r"\s+", " ", low).strip()


def extract_from_linkedin_title(title: str) -> str | None:
    """Extract company name from LinkedIn page title."""
    m = re.match(LINKEDIN_PATTERN, title.strip(), re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        if name.lower() not in GENERIC_REJECT and len(name) > 3:
            return name
    return None


def extract_firm_names(text: str, source_class: str) -> list[str]:
    """Extract firm names from text using patterns."""
    text = clean_text_for_extraction(text)
    if not text or len(text) < 10:
        return []

    found = set()

    for pat in PATTERNS:
        matches = re.findall(pat, text, re.IGNORECASE)
        for m in matches:
            name = m.strip() if isinstance(m, str) else " ".join(m).strip()
            name = re.sub(r"\s+", " ", name)
            if validate_firm_name(name):
                found.add(name)

    return list(found)


def validate_firm_name(name: str) -> bool:
    """Validate a candidate firm name."""
    if not name or len(name) < 5 or len(name) > 80:
        return False

    low = name.lower()
    if low in GENERIC_REJECT:
        return False

    # Must have at least one meaningful token
    tokens = name.split()
    meaningful = [t for t in tokens if t.lower() not in STOP_TOKENS]
    if len(meaningful) < 1:
        return False

    # First meaningful token must be capitalized proper noun
    if not re.match(r"^[A-Z][A-Za-z'’\-]{2,}$", meaningful[0]):
        return False

    # Reject if it's all generic terms
    if all(t.lower() in STOP_TOKENS for t in tokens):
        return False

    # Reject names with digits
    if re.search(r"\d", name):
        return False

    # Reject names that are just "X Family Office" where X is generic
    if re.match(r"^(the\s+)?(family|single|multi|global|united|core|future|us)\s+family\s+office", low):
        return False

    return True


def normalize_for_dedup(name: str) -> str:
    """Normalize name for deduplication."""
    norm = name.lower()
    # Remove common suffixes
    norm = re.sub(r"\s+family\s+office[s]?$", "", norm)
    norm = re.sub(r"\s+(?:capital|partners|holdings|ventures|wealth|group|advisors?|investments?|office)$", "", norm)
    norm = re.sub(r"^the\s+", "", norm)
    return norm.strip()


def main():
    print("[info] Extracting firm candidates from expanded discovery...")

    candidates = []

    with IN.open(encoding="utf-8") as f:
        for line in f:
            hit = json.loads(line)
            domain = hit.get("domain", "").lower().lstrip("www.")
            source_class = hit.get("source_class", "")
            title = hit.get("title", "")
            snippet = hit.get("snippet", "")

            # Skip aggregator/social domains for primary extraction
            if domain in SKIP_DOMAINS and source_class != "linkedin_company":
                continue

            names = []

            # LinkedIn company pages: extract from title
            if source_class == "linkedin_company":
                linkedin_name = extract_from_linkedin_title(title)
                if linkedin_name:
                    names.append(linkedin_name)

            # All sources: extract from title + snippet
            combined = f"{title} {snippet}"
            extracted = extract_firm_names(combined, source_class)
            names.extend(extracted)

            for name in names:
                norm = normalize_for_dedup(name)
                candidates.append({
                    "firm_name": name,
                    "normalized_name": norm,
                    "source_class": source_class,
                    "source_query": hit.get("query", ""),
                    "source_url": hit.get("url", ""),
                    "source_domain": domain,
                    "discovered_at": hit.get("discovered_at", ""),
                })

    print(f"[info] {len(candidates)} raw extractions")

    # Deduplicate by normalized name, keep best source
    # Priority: web_firm_team_page > linkedin_company > web_news_appointments > sec_edgar > web_industry_*
    source_priority = {
        "web_firm_team_page": 5,
        "linkedin_company": 4,
        "web_news_appointments": 3,
        "sec_edgar": 2,
        "web_industry_coverage": 1,
        "web_industry_events": 1,
    }

    by_norm = {}
    for c in candidates:
        norm = c["normalized_name"]
        prio = source_priority.get(c["source_class"], 0)
        if norm not in by_norm or prio > by_norm[norm]["_prio"]:
            c["_prio"] = prio
            by_norm[norm] = c

    final = list(by_norm.values())
    for c in final:
        del c["_prio"]

    print(f"[info] {len(final)} unique firms after deduplication")

    # Save
    with OUT.open("w", encoding="utf-8") as f:
        for c in final:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"[ok] Firm candidates -> {OUT}")

    # Show all candidates by source class
    print("\n[candidates by source class]")
    by_class = {}
    for c in final:
        cls = c["source_class"]
        by_class.setdefault(cls, []).append(c["firm_name"])

    for cls in sorted(by_class.keys(), key=lambda x: -len(by_class[x])):
        print(f"\n  {cls} ({len(by_class[cls])}):")
        for name in sorted(by_class[cls])[:15]:
            print(f"    {name}")


if __name__ == "__main__":
    main()