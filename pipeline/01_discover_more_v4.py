# pipeline/01_discover_more_v4.py
# Additional discovery queries - focused on finding MORE firms for 500 target
# More specific angles: regional, AUM tiers, investment focus, professional networks

import json
import time
import pathlib
from datetime import datetime, timezone
from urllib.parse import urlparse
from ddgs import DDGS

OUT = pathlib.Path("data/raw/discovery_more_v4.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

# 40+ targeted queries for additional firm discovery
QUERIES = [
    # US Regional - major wealth centers
    ('site:*.com "family office" "Boston" team OR leadership', "web_geo_boston"),
    ('site:*.com "family office" "Chicago" team OR leadership', "web_geo_chicago"),
    ('site:*.com "family office" "Denver" team OR leadership', "web_geo_denver"),
    ('site:*.com "family office" "Seattle" team OR leadership', "web_geo_seattle"),
    ('site:*.com "family office" "Atlanta" team OR leadership', "web_geo_atlanta"),
    ('site:*.com "family office" "Dallas" team OR leadership', "web_geo_dallas"),
    ('site:*.com "family office" "Houston" team OR leadership', "web_geo_houston"),
    ('site:*.com "family office" "Phoenix" team OR leadership', "web_geo_phoenix"),
    ('site:*.com "family office" "San Diego" team OR leadership', "web_geo_sandiego"),
    ('site:*.com "family office" "Minneapolis" team OR leadership', "web_geo_minneapolis"),
    
    # AUM tiers - different language
    ('"family office" "$100M" OR "$200M" OR "$500M" "assets"', "web_aum_100_500"),
    ('"family office" "$1B" OR "$2B" OR "$5B" "assets under management"', "web_aum_1b_plus"),
    ('"single family office" "net worth" "$" "million"', "web_aum_sfo"),
    
    # Investment focus variations
    ('"family office" "direct investments" team', "web_direct_inv"),
    ('"family office" "co-investments" team', "web_coinv"),
    ('"family office" "venture capital" team', "web_vc"),
    ('"family office" "private equity" team', "web_pe"),
    ('"family office" "real assets" team', "web_real_assets"),
    ('"family office" "alternative investments" team', "web_alt"),
    ('"family office" "impact investing" team', "web_impact"),
    ('"family office" "ESG" team', "web_esg"),
    
    # Professional networks & associations
    ('"Family Office Exchange" member OR members', "web_fox_members"),
    ('"TIGER 21" member OR members', "web_tiger21"),
    ('"Family Office Association" directory', "web_foa"),
    ('"Ultra High Net Worth" "family office" network', "web_uhnw_network"),
    
    # Service provider referrals (lawyers, accountants, placement agents)
    ('"family office" "outside counsel" OR "legal advisor"', "web_legal"),
    ('"family office" "fund administrator" OR "back office"', "web_fund_admin"),
    ('"family office" "placement agent" "capital introduction"', "web_placement"),
    ('"family office" "investment consultant" OR "OCIO"', "web_consultant"),
    
    # Family office events - speakers/attendees
    ('"Family Office Summit" 2024 speaker OR panelist', "web_summit_2024"),
    ('"Family Office Conference" 2024 attendee', "web_conf_2024"),
    ('"SuperReturn" "family office" 2024', "web_superreturn"),
    ('"PEI" "family office" 2024', "web_pei"),
    
    # Philanthropy & impact (often have family office connections)
    ('"family office" "philanthropic advisor"', "web_philanthropy"),
    ('"family office" "charitable giving" team', "web_charitable"),
    
    # Next gen / succession
    ('"next gen" "family office" team OR leadership', "web_nextgen"),
    ('"rising gen" "family office"', "web_rising_gen"),
    ('"succession planning" "family office" team', "web_succession"),
    
    # Technology / family office platforms
    ('"family office platform" OR "family office software" team', "web_platform"),
    ('"family office" "technology" "chief" OR "head"', "web_tech"),
    
    # International - English language
    ('site:*.com "family office" "London" team OR leadership', "web_geo_london"),
    ('site:*.com "family office" "Singapore" team OR leadership', "web_geo_singapore"),
    ('site:*.com "family office" "Dubai" team OR leadership', "web_geo_dubai"),
    ('site:*.com "family office" "Hong Kong" team OR leadership', "web_geo_hk"),
    ('site:*.com "family office" "Sydney" team OR leadership', "web_geo_sydney"),
    ('site:*.com "family office" "Toronto" team OR leadership', "web_geo_toronto"),
    ('site:*.com "family office" "Zurich" team OR leadership', "web_geo_zurich"),
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

print("\n[top 30 domains]")
for d, c in sorted(per_domain.items(), key=lambda x: -x[1])[:30]:
    print(f"  {c:>3}  {d}")

SUMMARY = pathlib.Path("data/raw/discovery_more_v4_summary.json")
with SUMMARY.open("w") as f:
    json.dump({
        "total_hits": total,
        "unique_domains": len(per_domain),
        "by_source_class": per_source_class,
        "top_domains": dict(sorted(per_domain.items(), key=lambda x: -x[1])[:50]),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }, f, indent=2)
print(f"\n[ok] Source summary -> {SUMMARY}")