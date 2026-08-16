# pipeline/01_discover_more_v3.py
# Additional discovery queries to reach 500 records
# More query angles targeting different family office segments

import json
import time
import pathlib
from datetime import datetime, timezone
from urllib.parse import urlparse
from ddgs import DDGS

OUT = pathlib.Path("data/raw/discovery_more_v3.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

# 30+ additional query angles for more coverage
QUERIES = [
    # Geographic/regional family offices
    ('site:*.com "family office" "New York" OR "NYC" team OR leadership', "web_geo_ny"),
    ('site:*.com "family office" "San Francisco" OR "Bay Area" team OR leadership', "web_geo_sf"),
    ('site:*.com "family office" "Chicago" OR "Illinois" team OR leadership', "web_geo_chi"),
    ('site:*.com "family office" "Los Angeles" OR "LA" team OR leadership', "web_geo_la"),
    ('site:*.com "family office" "Miami" OR "Florida" team OR leadership', "web_geo_fl"),
    ('site:*.com "family office" "Texas" OR "Houston" OR "Dallas" team OR leadership', "web_geo_tx"),
    ('site:*.com "family office" "London" OR "UK" team OR leadership', "web_geo_uk"),
    ('site:*.com "family office" "Singapore" OR "Hong Kong" team OR leadership', "web_geo_apac"),
    ('site:*.com "family office" "Toronto" OR "Canada" team OR leadership', "web_geo_ca"),
    
    # AUM-based queries
    ('"family office" "assets under management" "$1 billion" OR "$2 billion" OR "$5 billion"', "web_aum_large"),
    ('"family office" "assets under management" "$100 million" OR "$200 million" OR "$500 million"', "web_aum_mid"),
    ('"single family office" "AUM" "billion"', "web_aum_billion"),
    
    # Investment focus queries
    ('"family office" "direct investment" OR "co-investment" team', "web_direct_invest"),
    ('"family office" "private equity" OR "venture capital" team', "web_pe_vc"),
    ('"family office" "real estate" OR "property" team', "web_real_estate"),
    ('"family office" "hedge fund" OR "public markets" team', "web_hedge_fund"),
    ('"family office" "impact investing" OR "ESG" team', "web_impact"),
    
    # Industry events/speakers (fresh signals)
    ('"family office" speaker OR panel OR conference 2024 OR 2025', "web_events_speakers"),
    ('"family office summit" OR "family office conference" 2024 OR 2025 attendee OR speaker', "web_events_attendees"),
    
    # Professional services referring to family offices
    ('"family office" "law firm" OR "legal counsel" OR "outside counsel"', "web_legal"),
    ('"family office" "accounting firm" OR "tax advisor" OR "CPA"', "web_accounting"),
    ('"family office" "placement agent" OR "fundraising" OR "capital introduction"', "web_placement"),
    
    # LinkedIn people search (not companies)
    ('site:linkedin.com/in "family office" "managing director" OR "partner" OR "principal"', "linkedin_people"),
    ('site:linkedin.com/in "single family office" "chief investment officer"', "linkedin_people_cio"),
    ('site:linkedin.com/in "multi-family office" "portfolio manager"', "linkedin_people_pm"),
    
    # Family office networks/associations
    ('"family office association" OR "family office network" members', "web_associations"),
    ('"family office peer group" OR "family office forum"', "web_peer_groups"),
    
    # Philanthropy/impact
    ('"family office" "philanthropy" OR "charitable" OR "foundation" team', "web_philanthropy"),
    ('"family office" "impact investing" OR "mission-related investing"', "web_mission_invest"),
    
    # Succession/next gen
    ('"family office" "next generation" OR "next gen" OR "succession" team', "web_next_gen"),
    
    # Technology/family office tech
    ('"family office" "technology" OR "platform" OR "software" team', "web_fo_tech"),
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
        time.sleep(1.5)

print(f"\n[ok] {total} hits across {len(per_domain)} distinct domains -> {OUT}")
print("\n[by source class]")
for cls, cnt in sorted(per_source_class.items(), key=lambda x: -x[1]):
    print(f"  {cnt:>3}  {cls}")

print("\n[top 25 domains]")
for d, c in sorted(per_domain.items(), key=lambda x: -x[1])[:25]:
    print(f"  {c:>3}  {d}")

# Save summary
SUMMARY = pathlib.Path("data/raw/discovery_more_v3_summary.json")
with SUMMARY.open("w") as f:
    json.dump({
        "total_hits": total,
        "unique_domains": len(per_domain),
        "by_source_class": per_source_class,
        "top_domains": dict(sorted(per_domain.items(), key=lambda x: -x[1])[:50]),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }, f, indent=2)
print(f"\n[ok] Source summary -> {SUMMARY}")