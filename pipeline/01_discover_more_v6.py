# pipeline/01_discover_more_v6.py
# Discovery pass 6: New angles - wealth management firms, RIA directories, 
# family office service providers, international, next-gen signals

import json
import time
import pathlib
from datetime import datetime, timezone
from urllib.parse import urlparse
from ddgs import DDGS

OUT = pathlib.Path("data/raw/discovery_more_v6.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

# NEW angles not yet exploited
QUERIES = [
    # RIA/SEC-registered firms that serve families
    ('"RIA" "family office" "team" OR "leadership"', "web_ria_fo"),
    ('"registered investment adviser" "family office" "Chief Investment Officer"', "web_ria_cio"),
    ('"multi-family office" "SEC registered"', "web_mfo_sec"),
    ('"single family office" "SEC registered"', "web_sfo_sec"),
    
    # Wealth management firms with family office divisions
    ('"wealth management" "family office" "division" OR "group" team', "web_wm_fo_div"),
    ('"private wealth" "family office" team', "web_pw_fo"),
    ('"family office services" "team" OR "leadership"', "web_fo_services"),
    
    # Outsourced family office providers
    ('"outsourced family office" OR "virtual family office" team', "web_outsourced_fo"),
    ('"family office platform" "team" OR "leadership"', "web_fo_platform_team"),
    
    # International - specific countries
    ('"family office" "Australia" team OR leadership', "web_geo_au"),
    ('"family office" "Switzerland" team OR leadership', "web_geo_ch"),
    ('"family office" "Germany" team OR leadership', "web_geo_de"),
    ('"family office" "France" team OR leadership', "web_geo_fr"),
    ('"family office" "Netherlands" team OR leadership', "web_geo_nl"),
    ('"family office" "Luxembourg" team OR leadership', "web_geo_lu"),
    ('"family office" "Cayman" team OR leadership', "web_geo_ky"),
    ('"family office" "Bahamas" team OR leadership', "web_geo_bs"),
    ('"family office" "Jersey" team OR leadership', "web_geo_je"),
    ('"family office" "Guernsey" team OR leadership', "web_geo_gg"),
    
    # Middle East
    ('"family office" "Abu Dhabi" team OR leadership', "web_geo_ae"),
    ('"family office" "Qatar" team OR leadership', "web_geo_qa"),
    ('"family office" "Saudi Arabia" team OR leadership', "web_geo_sa"),
    
    # Asia
    ('"family office" "Japan" team OR leadership', "web_geo_jp"),
    ('"family office" "South Korea" team OR leadership', "web_geo_kr"),
    ('"family office" "India" team OR leadership', "web_geo_in"),
    ('"family office" "Taiwan" team OR leadership', "web_geo_tw"),
    
    # Latin America
    ('"family office" "Brazil" team OR leadership', "web_geo_br"),
    ('"family office" "Mexico" team OR leadership', "web_geo_mx"),
    
    # Specific AUM tiers
    ('"$500 million" "family office" team', "web_aum_500m"),
    ('"$200 million" "family office" team', "web_aum_200m"),
    ('"$100 million" "family office" team', "web_aum_100m"),
    
    # Investment focus specific
    ('"family office" "venture capital" "Chief Investment Officer"', "web_vc_cio"),
    ('"family office" "private equity" "Managing Partner"', "web_pe_mp"),
    ('"family office" "real estate" "Chief Investment Officer"', "web_re_cio"),
    ('"family office" "hedge fund" "Managing Director"', "web_hf_md"),
    ('"family office" "public markets" "Chief Investment Officer"', "web_pm_cio"),
    ('"family office" "alternatives" "Chief Investment Officer"', "web_alt_cio"),
    ('"family office" "secondaries" "Chief Investment Officer"', "web_sec_cio"),
    ('"family office" "co-investment" "Managing Partner"', "web_coinv_mp"),
    
    # Family office networks/memberships
    ('"TIGER 21" "family office" member', "web_tiger21_mem"),
    ('"Family Office Exchange" "member" OR "membership"', "web_fox_mem"),
    ('"Family Office Association" "member"', "web_foa_mem"),
    ('"Premier Family Office" network', "web_premier_fo"),
    
    # Philanthropy/foundation connections
    ('"family foundation" "family office" "Chief Investment Officer"', "web_ff_cio"),
    ('"philanthropic advisor" "family office" team', "web_pa_fo"),
    
    # Next generation / succession / rising gen
    ('"rising generation" "family office" "Chief Investment Officer"', "web_rising_cio"),
    ('"next gen" "family office" "Managing Partner"', "web_nextgen_mp"),
    ('"succession" "family office" "Chief Investment Officer"', "web_succession_cio2"),
    ('"family office" "next generation" "Managing Director"', "web_ng_md"),
    
    # Technology/fintech for family offices
    ('"family office technology" "Chief Technology Officer"', "web_fo_cto"),
    ('"family office software" "team" OR "leadership"', "web_fo_soft_team"),
    
    # Professional services - law firms, accounting, placement
    ('"law firm" "family office" "Chief Investment Officer"', "web_law_cio"),
    ('"placement agent" "family office" "Managing Partner"', "web_placement_mp2"),
    ('"family office" "tax advisor" OR "tax partner"', "web_tax_fo"),
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
        time.sleep(1.2)

print(f"\n[ok] {total} hits across {len(per_domain)} distinct domains -> {OUT}")
print("\n[by source class]")
for cls, cnt in sorted(per_source_class.items(), key=lambda x: -x[1]):
    print(f"  {cnt:>3}  {cls}")

print("\n[top 30 domains]")
for d, c in sorted(per_domain.items(), key=lambda x: -x[1])[:30]:
    print(f"  {c:>3}  {d}")

SUMMARY = pathlib.Path("data/raw/discovery_more_v6_summary.json")
with SUMMARY.open("w") as f:
    json.dump({
        "total_hits": total,
        "unique_domains": len(per_domain),
        "by_source_class": per_source_class,
        "top_domains": dict(sorted(per_domain.items(), key=lambda x: -x[1])[:50]),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }, f, indent=2)
print(f"\n[ok] Source summary -> {SUMMARY}")