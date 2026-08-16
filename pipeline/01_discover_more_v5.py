# pipeline/01_discover_more_v5.py
# Targeted discovery queries - specifically designed to find family office FIRMS
# Not generic corporate leadership pages

import json
import time
import pathlib
from datetime import datetime, timezone
from urllib.parse import urlparse
from ddgs import DDGS

OUT = pathlib.Path("data/raw/discovery_more_v5.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

# HIGHLY TARGETED queries for family office firms
# Each query combines "family office" with firm-identifying patterns
QUERIES = [
    # Direct firm name patterns
    ('"family office" "our team" "Chief Investment Officer"', "web_firm_cio_page"),
    ('"family office" "our team" "Managing Partner"', "web_firm_mp_page"),
    ('"family office" "our team" "Managing Director"', "web_firm_md_page"),
    ('"family office" "our team" "Partner" "Principal"', "web_firm_partner_page"),
    ('"family office" "meet the team" "Chief"', "web_firm_meet_team"),
    ('"family office" "leadership team" "Chief Investment Officer"', "web_firm_leadership"),
    
    # Geographic + family office specific
    ('"family office" "New York" "Chief Investment Officer"', "web_geo_ny_cio"),
    ('"family office" "San Francisco" "Chief Investment Officer"', "web_geo_sf_cio"),
    ('"family office" "Chicago" "Chief Investment Officer"', "web_geo_chi_cio"),
    ('"family office" "Los Angeles" "Chief Investment Officer"', "web_geo_la_cio"),
    ('"family office" "Miami" "Chief Investment Officer"', "web_geo_mia_cio"),
    ('"family office" "Dallas" "Chief Investment Officer"', "web_geo_dal_cio"),
    ('"family office" "Denver" "Chief Investment Officer"', "web_geo_den_cio"),
    ('"family office" "Seattle" "Chief Investment Officer"', "web_geo_sea_cio"),
    ('"family office" "Atlanta" "Chief Investment Officer"', "web_geo_atl_cio"),
    ('"family office" "Boston" "Chief Investment Officer"', "web_geo_bos_cio"),
    
    # Firm name patterns
    ('"Family Office" "LLC" "team" OR "leadership"', "web_firm_llc"),
    ('"Family Office" "L.P." "team" OR "leadership"', "web_firm_lp"),
    ('"Family Office" "Ltd" "team" OR "leadership"', "web_firm_ltd"),
    ('"Family Office" "Partners" "team" OR "leadership"', "web_firm_partners"),
    ('"Family Office" "Capital" "team" OR "leadership"', "web_firm_capital"),
    ('"Family Office" "Wealth" "team" OR "leadership"', "web_firm_wealth"),
    ('"Family Office" "Advisors" "team" OR "leadership"', "web_firm_advisors"),
    ('"Family Office" "Group" "team" OR "leadership"', "web_firm_group"),
    ('"Family Office" "Holdings" "team" OR "leadership"', "web_firm_holdings"),
    ('"Family Office" "Investments" "team" OR "leadership"', "web_firm_investments"),
    
    # Multi-family office specific
    ('"multi-family office" "our team"', "web_mfo_team"),
    ('"multi family office" "our team"', "web_mfo_team2"),
    ('"multi-family office" "Chief Investment Officer"', "web_mfo_cio"),
    ('"multi family office" "Managing Partner"', "web_mfo_mp"),
    ('"multi-family office" "Managing Director"', "web_mfo_md"),
    
    # Single family office specific
    ('"single family office" "our team"', "web_sfo_team"),
    ('"single family office" "Chief Investment Officer"', "web_sfo_cio"),
    ('"single family office" "Managing Director"', "web_sfo_md"),
    
    # Family wealth office variations
    ('"family wealth office" "team" OR "leadership"', "web_fwo_team"),
    ('"family investment office" "team" OR "leadership"', "web_fio_team"),
    ('"private family office" "team" OR "leadership"', "web_pfo_team"),
    
    # Industry events with firm names
    ('"Family Office Summit" "Chief Investment Officer" 2024 OR 2025', "web_event_cio"),
    ('"Family Office Conference" "Managing Partner" 2024 OR 2025', "web_event_mp"),
    ('"SuperReturn" "family office" "Chief Investment Officer" 2024', "web_superreturn_cio"),
    
    # Professional directories
    ('"family office" directory "Chief Investment Officer"', "web_dir_cio"),
    ('"family office" database "Managing Partner"', "web_db_mp"),
    
    # Service provider client lists
    ('"family office" client "Chief Investment Officer" "law firm"', "web_legal_cio"),
    ('"family office" client "Managing Partner" "placement agent"', "web_placement_mp"),
    ('"family office" "advised by" "Chief Investment Officer"', "web_advised_cio"),
    
    # Philanthropy connections
    ('"family office" "philanthropy" "Chief Investment Officer"', "web_phil_cio"),
    ('"family office" "foundation" "Chief Investment Officer"', "web_foundation_cio"),
    
    # Next gen / succession signals
    ('"next generation" "family office" "Chief Investment Officer"', "web_nextgen_cio"),
    ('"succession" "family office" "Chief Investment Officer"', "web_succession_cio"),
    
    # International - specific
    ('"family office" "London" "Chief Investment Officer"', "web_lon_cio"),
    ('"family office" "Singapore" "Chief Investment Officer"', "web_sgp_cio"),
    ('"family office" "Dubai" "Chief Investment Officer"', "web_dub_cio"),
    ('"family office" "Toronto" "Chief Investment Officer"', "web_tor_cio"),
    ('"family office" "Zurich" "Chief Investment Officer"', "web_zur_cio"),
    ('"family office" "Hong Kong" "Chief Investment Officer"', "web_hkg_cio"),
    
    # AUM-specific language
    ('"family office" "$1 billion" "Chief Investment Officer"', "web_aum1b_cio"),
    ('"family office" "$500 million" "Chief Investment Officer"', "web_aum500m_cio"),
    ('"family office" "$100 million" "Chief Investment Officer"', "web_aum100m_cio"),
]

ddgs = DDGS()
total = 0
per_domain = {}
per_source_class = {}

with OUT.open("w", encoding="utf-8") as f:
    for query, source_class in QUERIES:
        print(f"[query] {source_class}: {query[:80]}...")
        try:
            results = ddgs.text(query, max_results=10)
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

SUMMARY = pathlib.Path("data/raw/discovery_more_v5_summary.json")
with SUMMARY.open("w") as f:
    json.dump({
        "total_hits": total,
        "unique_domains": len(per_domain),
        "by_source_class": per_source_class,
        "top_domains": dict(sorted(per_domain.items(), key=lambda x: -x[1])[:50]),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }, f, indent=2)
print(f"\n[ok] Source summary -> {SUMMARY}")