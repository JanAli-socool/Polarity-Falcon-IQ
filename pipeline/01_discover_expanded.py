# pipeline/01_discover_expanded.py
# Expanded multi-angle discovery for Stage 2 — targeting 500 qualifying records.
# Source classes: web search (DDG), SEC EDGAR, firm website pages, LinkedIn company pages,
# news/press releases, regulatory filings, industry directories.

import json
import time
import pathlib
from datetime import datetime, timezone
from urllib.parse import urlparse
from ddgs import DDGS
import requests
from bs4 import BeautifulSoup

OUT = pathlib.Path("data/raw/discovery_expanded.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

# 20+ deliberately non-overlapping query angles across 5 source classes
# Each angle targets a different segment of the family office market

QUERIES = [
    # --- Class 1: Direct firm self-identification (firm's own site/pages) ---
    ('site:*.com "family office" "our team" OR "our people" OR "leadership"', "web_firm_team_page"),
    ('site:*.com "single family office" "team" OR "principals"', "web_firm_team_page"),
    ('site:*.com "multi-family office" "team" OR "professionals"', "web_firm_team_page"),
    ('site:*.com "family wealth" "our team" OR "leadership"', "web_firm_team_page"),
    ('site:*.com "family investment office" "team" OR "people"', "web_firm_team_page"),

    # --- Class 2: News/Press appointments (fresh signals) ---
    ('"family office" appoints OR names OR joins OR promotes 2024 OR 2025', "web_news_appointments"),
    ('"single family office" "chief investment officer" OR "managing partner" 2024', "web_news_appointments"),
    ('"family office" "new" "partner" OR "director" OR "principal" 2024', "web_news_appointments"),
    ('"multi-family office" launches OR expands OR opens 2024 OR 2025', "web_news_appointments"),

    # --- Class 3: LinkedIn company pages (structured, verifiable) ---
    ('site:linkedin.com/company "family office" United States', "linkedin_company"),
    ('site:linkedin.com/company "single family office" United States', "linkedin_company"),
    ('site:linkedin.com/company "multi-family office" United States', "linkedin_company"),
    ('site:linkedin.com/company "family wealth" "family office" United States', "linkedin_company"),

    # --- Class 4: SEC EDGAR (regulatory filings) ---
    ('"family office" site:sec.gov Form ADV', "sec_edgar"),
    ('"single family office" site:sec.gov', "sec_edgar"),
    ('"multi-family office" site:sec.gov', "sec_edgar"),
    ('"family investment office" site:sec.gov', "sec_edgar"),

    # --- Class 5: Industry coverage / directories (corroboration) ---
    ('"family office" "assets under management" OR "AUM" 2024', "web_industry_coverage"),
    ('"family office" "wealth management" "team" site:*.com -site:linkedin.com', "web_industry_coverage"),
    ('"family office conference" OR "family office summit" 2024 OR 2025', "web_industry_events"),
]

ddgs = DDGS()
total = 0
per_domain = {}
per_source_class = {}

with OUT.open("w", encoding="utf-8") as f:
    for query, source_class in QUERIES:
        print(f"[query] {source_class}: {query[:80]}...")
        try:
            results = ddgs.text(query, max_results=15)
        except Exception as e:
            print(f"  [warn] query failed: {e}")
            results = []

        for r in results:
            url = r.get("href", "")
            domain = urlparse(url).netloc.lower().lstrip("www.")
            per_domain[domain] = per_domain.get(domain, 0) + 1
            per_source_class[source_class] = per_source_class.get(source_class, 0) + 1
            f.write(json.dumps({
                "query": query,
                "source_class": source_class,
                "title": r.get("title", ""),
                "url": url,
                "domain": domain,
                "snippet": r.get("body", ""),
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False) + "\n")
            total += 1
        time.sleep(1.2)  # polite pacing

print(f"\n[ok] {total} hits across {len(per_domain)} distinct domains -> {OUT}")
print("\n[by source class]")
for cls, cnt in sorted(per_source_class.items(), key=lambda x: -x[1]):
    print(f"  {cnt:>3}  {cls}")

print("\n[top 20 domains]")
for d, c in sorted(per_domain.items(), key=lambda x: -x[1])[:20]:
    print(f"  {c:>3}  {d}")

# Also save source class summary for methodology
SUMMARY = pathlib.Path("data/raw/discovery_source_summary.json")
with SUMMARY.open("w") as f:
    json.dump({
        "total_hits": total,
        "unique_domains": len(per_domain),
        "by_source_class": per_source_class,
        "top_domains": dict(sorted(per_domain.items(), key=lambda x: -x[1])[:30]),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }, f, indent=2)
print(f"\n[ok] Source summary -> {SUMMARY}")