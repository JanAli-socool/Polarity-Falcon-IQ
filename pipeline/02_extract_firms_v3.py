# pipeline/02_extract_firms_v3.py
# Extract candidate firms from ALL discovery hits (expanded + more_v3)
# Merges and deduplicates across all discovery sources

import json
import re
import pathlib
from collections import Counter

IN_FILES = [
    pathlib.Path("data/raw/discovery_expanded.jsonl"),
    pathlib.Path("data/raw/discovery_more_v3.jsonl"),
    pathlib.Path("data/raw/discovery_more_v4.jsonl"),
    pathlib.Path("data/raw/discovery_more_v5.jsonl"),
    pathlib.Path("data/raw/discovery_more_v6.jsonl"),
    pathlib.Path("data/raw/discovery_more_v7.jsonl"),
    pathlib.Path("data/raw/discovery_more_v8.jsonl"),
    pathlib.Path("data/raw/discovery_more_v9.jsonl"),
    pathlib.Path("data/raw/discovery_more_v10.jsonl"),
    pathlib.Path("data/raw/discovery_more_v11.jsonl"),
]
OUT = pathlib.Path("data/raw/firm_candidates_v3.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

# More precise patterns for firm names - capture FULL firm name including "Family Office"
PATTERNS = [
    # "X Family Office" or "X Family Offices" - 2-4 words before Family Office
    r"\b([A-Z][A-Za-z'’\-]{2,}(?:\s+[A-Z][A-Za-z'’\-]{2,}){1,3}\s+Family\s+Office(?:s)?)\b",
    # "The X Family Office" - 2-4 words after The
    r"\b(The\s+[A-Z][A-Za-z'’\-]{2,}(?:\s+[A-Z][A-Za-z'’\-]{2,}){1,3}\s+Family\s+Office)\b",
    # "family office called/named/is X Capital/Partners/Holdings/etc."
    r"(?:family\s+office\s+(?:called|named|:)\s+)([A-Z][A-Za-z'’\-]{2,}(?:\s+[A-Z][A-Za-z'’\-]{2,}){0,2}\s+(?:Capital|Partners|Holdings|Ventures|Wealth|Group|Advisors?|Investments?|Office))",
    r"(?:family\s+office\s+(?:called|named|:)\s+)([A-Z][A-Za.z'’\-]{2,}(?:\s+[A-Z][A-Za.z'’\-]{2,}){0,2}\s+(?:Wealth|Family\s+Wealth))",
    # "family office called/named/is X Investment Office/Wealth Office/etc."
    r"(?:family\s+office\s+(?:called|named|:|is|of)\s+)([A-Z][A-Za.z'’\-]{2,}(?:\s+[A-Z][A-Za.z'’\-]{2,}){0,3}\s+(?:Investment\s+Office|Wealth\s+Office|Family\s+Wealth|Capital|Partners|Holdings|Ventures|Group|Advisors?|Investments?))",
    # "Meet Our Team - X Family Office" or "Our Team - X Family Office"
    r"(?:Meet Our Team|Our Team|Leadership Team|The Team)\s*[\-\|]\s*([A-Z][A-Za.z'’\-]{2,}(?:\s+[A-Z][A-Za.z'’\-]{2,}){1,3}\s+Family\s+Office)",
    # "family office called/named/is X Family Office"
    r"(?:family office|Family Office)\s+(?:called|named|is|:)\s+([A-Z][A-Za.z'’\-]{2,}(?:\s+[A-Z][A-Za.z'’\-]{2,}){1,3}\s+Family\s+Office)",
]

LINKEDIN_PATTERN = r"^([A-Z][A-Za-z'’\-]{2,}(?:\s+[A-Z][A-Za-z'’\-]{2,}){0,3})\s*[\|\-]\s*LinkedIn"

LINKEDIN_SOURCE_CLASSES = {
    "linkedin_company", "linkedin_people", "linkedin_people_cio", "linkedin_people_pm",
    "web_firm_cio_page", "web_firm_mp_page", "web_firm_md_page", "web_firm_partner_page",
    "web_firm_meet_team", "web_firm_leadership",
    "web_geo_ny_cio", "web_geo_sf_cio", "web_geo_chi_cio", "web_geo_la_cio",
    "web_geo_mia_cio", "web_geo_dal_cio", "web_geo_den_cio", "web_geo_sea_cio",
    "web_geo_atl_cio", "web_geo_bos_cio",
    "web_firm_llc", "web_firm_lp", "web_firm_ltd", "web_firm_partners",
    "web_firm_capital", "web_firm_wealth", "web_firm_advisors", "web_firm_group",
    "web_firm_holdings", "web_firm_investments",
    "web_mfo_team", "web_mfo_team2", "web_mfo_cio", "web_mfo_mp", "web_mfo_md",
    "web_sfo_team", "web_sfo_cio", "web_sfo_md",
    "web_fwo_team", "web_fio_team", "web_pfo_team",
    "web_event_cio", "web_event_mp", "web_superreturn_cio",
    "web_dir_cio", "web_db_mp", "web_legal_cio", "web_placement_mp", "web_advised_cio",
    "web_phil_cio", "web_foundation_cio", "web_nextgen_cio", "web_succession_cio",
    "web_lon_cio", "web_sgp_cio", "web_dub_cio", "web_tor_cio", "web_zur_cio", "web_hkg_cio",
    "web_aum1b_cio", "web_aum500m_cio", "web_aum100m_cio",
}

SKIP_DOMAINS = {
    "facebook.com", "twitter.com", "x.com", "wikipedia.org",
    "bloomberg.com", "forbes.com", "cnbc.com", "sec.gov", "tracxn.com",
    "axial.com", "crunchbase.com", "pitchbook.com", "youtube.com",
    "instagram.com", "glassdoor.com", "indeed.com", "ziprecruiter.com",
    "pinterest.com", "medium.com", "nytimes.com", "ft.com", "sportingnews.com",
}

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
    "phone", "number", "email", "address", "location",
}

def clean_text_for_extraction(text: str) -> str:
    if not text:
        return ""
    ui_phrases = [
        "skip to main content", "skip to navigation", "main menu", "search",
        "sign in", "log in", "register", "subscribe", "download", "read more",
        "learn more", "view all", "show more", "load more", "see all",
        "privacy policy", "terms of use", "cookie policy", "accessibility",
    ]
    # Don't lowercase - preserve case for proper name extraction
    for phrase in ui_phrases:
        # Case-insensitive replacement
        text = re.sub(re.escape(phrase), " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()

def extract_from_linkedin_title(title: str) -> str | None:
    m = re.match(LINKEDIN_PATTERN, title.strip(), re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        if name.lower() not in GENERIC_REJECT and len(name) > 3:
            return name
    return None

def extract_firm_names(text: str, source_class: str) -> list[str]:
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
    if not name or len(name) < 5 or len(name) > 80:
        return False
    low = name.lower()
    if low in GENERIC_REJECT:
        return False
    tokens = name.split()
    meaningful = [t for t in tokens if t.lower() not in STOP_TOKENS]
    if len(meaningful) < 1:
        return False
    # First meaningful token must be capitalized proper noun
    if not re.match(r"^[A-Z][A-Za-z'’\-]{2,}$", meaningful[0]):
        return False
    if all(t.lower() in STOP_TOKENS for t in tokens):
        return False
    # Reject if contains digits
    if re.search(r"\d", name):
        return False
    # Reject generic "X family office" patterns
    if re.match(r"^(the\s+)?(family|single|multi|global|united|core|future|us)\s+family\s+office", low):
        return False
    # Reject names that start with common non-proper-noun adjectives/verbs
    first_low = meaningful[0].lower()
    non_name_starters = {
        "effective", "impact", "guide", "strategies", "strategy", "how", "why", "what",
        "when", "where", "who", "which", "many", "most", "some", "few", "all",
        "best", "top", "leading", "global", "local", "regional", "national",
        "international", "new", "latest", "recent", "current", "future", "next",
        "old", "first", "last", "upcoming", "past", "previous",
        "simple", "easy", "complex", "difficult", "challenging", "opportunity",
        "approach", "method", "solution", "platform", "software", "technology",
        "service", "services", "product", "products", "tool", "tools", "guide",
        "report", "reports", "study", "studies", "analysis", "survey", "surveys",
        "insight", "insights", "trend", "trends", "outlook", "forecast",
        "predictions", "predictive", "predict", "invest", "investing", "investment",
        "fund", "funds", "capital", "wealth", "asset", "assets",
        "manage", "management", "managing", "advisor", "advisory",
        "consult", "consulting", "advise", "advised", "advises",
        "work", "working", "works", "built", "building", "build",
        "create", "created", "creation", "launch", "launched", "launch",
        "open", "opened", "opening", "close", "closed", "closing",
        "run", "running", "ran", "operate", "operating", "operated",
        "join", "joining", "joined", "connect", "connecting", "connected",
        "network", "networking", "networked", "partner", "partnership", "partnered",
        "collaborate", "collaborating", "collaborated", "support", "supporting",
        "help", "helping", "helped", "enable", "enabled", "enabling",
        "drive", "driving", "drove", "lead", "leading", "led", "guide", "guiding",
        "direct", "directing", "directed", "manage", "managing", "managed",
        "oversee", "overseeing", "oversaw", "supervise", "supervising", "supervised",
        "even", "though", "though", "although", "while", "including", "include",
        "includes", "included", "such", "as", "like", "unlike", "versus", "versus",
        "versus", "and", "or", "but", "if", "then", "else", "when", "where",
        "about", "above", "below", "between", "among", "during", "before", "after",
        "since", "until", "from", "into", "onto", "upon", "within", "without",
        "across", "beyond", "despite", "except", "per", "via", "re", "vs",
        "aum", "esg", "foa", "pei", "vc", "pe", "llc", "ltd", "lp", "inc", "corp",
        "kbpmg", "deloitte", "pwc", "ey", "kpmg", "mckinsey", "bcg", "bain",
        "goldman", "morgan", "stanley", "jpmorgan", "blackrock", "vanguard",
        "fidelity", "schwab", "td", "ameritrade", "etrade", "robinhood",
        "crypto", "bitcoin", "ethereum", "blockchain", "defi", "nft", "web3",
        "ai", "ml", "llm", "gpt", "chatgpt", "openai", "anthropic", "claude",
    }
    if meaningful[0].lower() in non_name_starters:
        return False
    # Reject if name contains common verb-like patterns
    if any(t.lower() in {"are", "is", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "must", "can", "cannot", "can't", "won't", "don't", "doesn't", "didn't", "isn't", "aren't", "wasn't", "weren't"} for t in tokens):
        return False
    # Additional check: if "Family Office" appears, validate the prefix
    fo_idx = low.find("family office")
    if fo_idx > 0:
        prefix = low[:fo_idx].strip()
        prefix_tokens = prefix.split()
        # Remove trailing stop words
        while prefix_tokens and prefix_tokens[-1].lower() in STOP_TOKENS:
            prefix_tokens.pop()
        if prefix_tokens:
            # The word immediately before "Family Office" should be a proper noun
            # Not a common adjective/verb
            last_word = prefix_tokens[-1].lower()
            common_adjectives_before_fo = {
                "effective", "impact", "guide", "strategies", "strategy", "leading",
                "global", "local", "regional", "national", "international",
                "new", "latest", "recent", "current", "future", "next", "old",
                "first", "last", "best", "top", "simple", "easy", "complex",
                "difficult", "challenging", "opportunity", "approach", "method",
                "solution", "platform", "software", "technology", "service",
                "services", "product", "products", "tool", "tools", "guide",
                "report", "reports", "study", "studies", "analysis", "survey",
                "surveys", "insight", "insights", "trend", "trends", "outlook",
                "forecast", "predictions", "predictive", "predict", "invest",
                "investing", "investment", "fund", "funds", "capital", "wealth",
                "asset", "assets", "manage", "management", "managing", "advisor",
                "advisory", "consult", "consulting", "advise", "advised", "advises",
                "work", "working", "works", "built", "building", "build", "create",
                "created", "creation", "launch", "launched", "open", "opened",
                "opening", "close", "closed", "closing", "run", "running", "ran",
                "operate", "operating", "operated", "join", "joining", "joined",
                "connect", "connecting", "connected", "network", "networking",
                "networked", "partner", "partnership", "partnered", "collaborate",
                "collaborating", "collaborated", "support", "supporting", "help",
                "helping", "helped", "enable", "enabled", "enabling", "drive",
                "driving", "drove", "lead", "leading", "led", "guide", "guiding",
                "direct", "directing", "directed", "manage", "managing", "managed",
                "oversee", "overseeing", "oversaw", "supervise", "supervising",
                "supervised", "even", "though", "although", "while", "including",
                "include", "includes", "included", "such", "as", "like", "unlike",
                "and", "or", "but", "if", "then", "else", "when", "where", "about",
                "above", "below", "between", "among", "during", "before", "after",
                "since", "until", "from", "into", "onto", "upon", "within", "without",
                "across", "beyond", "despite", "except", "per", "via", "re", "vs",
                "the", "a", "an", "this", "that", "these", "those", "my", "your",
                "his", "her", "its", "our", "their", "me", "you", "him", "us", "them",
                "i", "we", "he", "she", "it", "they", "me", "mine", "yours", "hers",
                "ours", "theirs", "am", "is", "are", "was", "were", "be", "been",
                "being", "have", "has", "had", "do", "does", "did", "will", "would",
                "could", "should", "may", "might", "must", "can", "cannot", "can't",
                "won't", "don't", "doesn't", "didn't", "isn't", "aren't", "wasn't",
                "weren't", "haven't", "hasn't", "hadn't",
            }
            if last_word in common_adjectives_before_fo:
                return False
            # Also reject if prefix is just 1 word and it's a common adjective
            if len(prefix_tokens) == 1 and last_word in common_adjectives_before_fo:
                return False
    if re.search(r"\d", name):
        return False
    if re.match(r"^(the\s+)?(family|single|multi|global|united|core|future|us)\s+family\s+office", low):
        return False
    return True

def normalize_for_dedup(name: str) -> str:
    norm = name.lower()
    norm = re.sub(r"\s+family\s+office[s]?$", "", norm)
    norm = re.sub(r"\s+(?:capital|partners|holdings|ventures|wealth|group|advisors?|investments?|office)$", "", norm)
    norm = re.sub(r"^the\s+", "", norm)
    return norm.strip()

def main():
    print("[info] Extracting firm candidates from ALL discovery sources...")
    candidates = []
    
    for IN in IN_FILES:
        if not IN.exists():
            print(f"[warn] {IN} does not exist, skipping")
            continue
        print(f"  Processing {IN}...")
        with IN.open(encoding="utf-8") as f:
            for line in f:
                hit = json.loads(line)
                domain = hit.get("domain", "").lower().lstrip("www.")
                source_class = hit.get("source_class", "")
                title = hit.get("title", "")
                snippet = hit.get("snippet", "")
                if domain in SKIP_DOMAINS and source_class not in LINKEDIN_SOURCE_CLASSES:
                    continue
                names = []
                if source_class in LINKEDIN_SOURCE_CLASSES:
                    linkedin_name = extract_from_linkedin_title(title)
                    if linkedin_name:
                        names.append(linkedin_name)
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
    
    source_priority = {
        "web_firm_team_page": 6,
        "web_firm_cio_page": 6, "web_firm_mp_page": 6, "web_firm_md_page": 6, "web_firm_partner_page": 6,
        "web_firm_meet_team": 6, "web_firm_leadership": 6,
        "web_geo_ny": 5, "web_geo_sf": 5, "web_geo_chi": 5, "web_geo_la": 5, "web_geo_fl": 5,
        "web_geo_tx": 5, "web_geo_uk": 5, "web_geo_apac": 5, "web_geo_ca": 5,
        "web_geo_ny_cio": 5, "web_geo_sf_cio": 5, "web_geo_chi_cio": 5, "web_geo_la_cio": 5,
        "web_geo_mia_cio": 5, "web_geo_dal_cio": 5, "web_geo_den_cio": 5,
        "web_geo_sea_cio": 5, "web_geo_atl_cio": 5, "web_geo_bos_cio": 5,
        "web_aum_large": 5, "web_aum_mid": 5, "web_aum_billion": 5,
        "web_direct_invest": 5, "web_pe_vc": 5, "web_real_estate": 5,
        "web_hedge_fund": 5, "web_impact": 5, "web_events_speakers": 5,
        "web_events_attendees": 5, "web_legal": 5, "web_accounting": 5,
        "web_placement": 5, "web_associations": 5, "web_peer_groups": 5,
        "web_philanthropy": 5, "web_mission_invest": 5, "web_next_gen": 5,
        "web_fo_tech": 5,
        "linkedin_company": 4,
        "linkedin_people": 4, "linkedin_people_cio": 4, "linkedin_people_pm": 4,
        "web_news_appointments": 3,
        "sec_edgar": 2,
        "web_industry_coverage": 1, "web_industry_events": 1,
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
    
    with OUT.open("w", encoding="utf-8") as f:
        for c in final:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    
    print(f"[ok] Firm candidates -> {OUT}")
    
    print("\n[candidates by source class]")
    by_class = {}
    for c in final:
        cls = c["source_class"]
        by_class.setdefault(cls, []).append(c["firm_name"])
    
    for cls in sorted(by_class.keys(), key=lambda x: -len(by_class[x])):
        print(f"\n  {cls} ({len(by_class[cls])}):")
        for name in sorted(by_class[cls])[:20]:
            print(f"    {name}")

if __name__ == "__main__":
    main()