# pipeline/01_discover_more_v7.py
# Discovery pass 7: More specific angles for additional firms

import json
import time
import pathlib
from datetime import datetime, timezone
from urllib.parse import urlparse
from ddgs import DDGS

OUT = pathlib.Path("data/raw/discovery_more_v7.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

QUERIES = [
    # Specific family office names from news/articles
    ('"Family Office" "appointed" "Chief Investment Officer" 2024 OR 2025', "web_news_cio_2024"),
    ('"Family Office" "hired" "Managing Partner" 2024 OR 2025', "web_news_mp_2024"),
    ('"Family Office" "named" "Managing Director" 2024 OR 2025', "web_news_md_2024"),
    ('"Family Office" "promoted" "Partner" 2024 OR 2025', "web_news_partner_2024"),
    
    # Specific firm types
    ('"single family office" "Chief Investment Officer" site:*.com', "web_sfo_cio_site"),
    ('"multi-family office" "Managing Partner" site:*.com', "web_mfo_mp_site"),
    ('"family office" "Chief Operating Officer" site:*.com', "web_fo_coo_site"),
    ('"family office" "Chief Financial Officer" site:*.com', "web_fo_cfo_site"),
    
    # Geographic - more specific
    ('"family office" "Denver" "Chief Investment Officer"', "web_geo_den_cio2"),
    ('"family office" "Phoenix" "Chief Investment Officer"', "web_geo_phx_cio"),
    ('"family office" "Austin" "Chief Investment Officer"', "web_geo_atx_cio"),
    ('"family office" "Nashville" "Chief Investment Officer"', "web_geo_bna_cio"),
    ('"family office" "Charlotte" "Chief Investment Officer"', "web_geo_clt_cio"),
    ('"family office" "Minneapolis" "Chief Investment Officer"', "web_geo_msp_cio"),
    ('"family office" "Seattle" "Chief Investment Officer"', "web_geo_sea_cio2"),
    ('"family office" "Portland" "Chief Investment Officer"', "web_geo_pdx_cio"),
    ('"family office" "San Diego" "Chief Investment Officer"', "web_geo_san_cio"),
    ('"family office" "Tampa" "Chief Investment Officer"', "web_geo_tpa_cio"),
    ('"family office" "Orlando" "Chief Investment Officer"', "web_geo_mco_cio"),
    ('"family office" "Raleigh" "Chief Investment Officer"', "web_geo_rdu_cio"),
    ('"family office" "Atlanta" "Chief Investment Officer"', "web_geo_atl_cio2"),
    
    # International financial centers
    ('"family office" "Cayman Islands" "Chief Investment Officer"', "web_geo_ky_cio"),
    ('"family office" "Luxembourg" "Chief Investment Officer"', "web_geo_lu_cio"),
    ('"family office" "Jersey" "Chief Investment Officer"', "web_geo_je_cio"),
    ('"family office" "Guernsey" "Chief Investment Officer"', "web_geo_gg_cio"),
    ('"family office" "Singapore" "Chief Investment Officer"', "web_geo_sg_cio"),
    ('"family office" "Hong Kong" "Chief Investment Officer"', "web_geo_hk_cio2"),
    ('"family office" "Dubai" "Chief Investment Officer"', "web_geo_dxb_cio"),
    ('"family office" "Abu Dhabi" "Chief Investment Officer"', "web_geo_auh_cio"),
    ('"family office" "Zurich" "Chief Investment Officer"', "web_geo_zrh_cio"),
    ('"family office" "Geneva" "Chief Investment Officer"', "web_geo_gva_cio"),
    ('"family office" "London" "Chief Investment Officer"', "web_geo_lon_cio2"),
    ('"family office" "Edinburgh" "Chief Investment Officer"', "web_geo_edi_cio"),
    
    # Specific investment strategies
    ('"family office" "impact investing" "Chief Investment Officer"', "web_impact_cio"),
    ('"family office" "ESG investing" "Chief Investment Officer"', "web_esg_cio"),
    ('"family office" "venture capital" "Chief Investment Officer"', "web_vc_cio2"),
    ('"family office" "private credit" "Chief Investment Officer"', "web_pc_cio"),
    ('"family office" "direct investing" "Chief Investment Officer"', "web_direct_cio"),
    ('"family office" "co-investing" "Managing Partner"', "web_coinv_mp2"),
    
    # Professional networks
    ('"Family Office Exchange" "Chief Investment Officer"', "web_fox_cio"),
    ('"TIGER 21" "Chief Investment Officer"', "web_tiger21_cio"),
    ('"FOX" "Family Office" "Chief Investment Officer"', "web_fox_cio2"),
    
    # Family office platforms/tech
    ('"family office" "technology platform" "team"', "web_fo_platform_team2"),
    ('"family office" "software" "Chief Technology Officer"', "web_fo_cto2"),
    ('"family office" "data" "Chief Data Officer"', "web_fo_cdo"),
    
    # Service providers
    ('"family office" "outsourced" "Chief Investment Officer"', "web_outsourced_cio"),
    ('"virtual family office" "Chief Investment Officer"', "web_vfo_cio"),
    ('"family office" "placement agent" "Chief Investment Officer"', "web_placement_cio"),
    ('"family office" "fund administrator" "team"', "web_fund_admin_team"),
    
    # Philanthropy/foundations
    ('"family foundation" "Chief Investment Officer"', "web_ff_cio2"),
    ('"philanthropic" "family office" "Chief Investment Officer"', "web_phil_cio2"),
    
    # Next gen/rising gen
    ('"rising gen" "family office" "Chief Investment Officer"', "web_rising_cio2"),
    ('"next generation" "family office" "Managing Partner"', "web_ng_mp"),
    ('"succession planning" "family office" "Chief Investment Officer"', "web_succ_cio3"),
    
    # Specific AUM ranges
    ('"$1 billion" "family office" "Chief Investment Officer"', "web_aum1b_cio2"),
    ('"$500 million" "family office" "Chief Investment Officer"', "web_aum500m_cio2"),
    ('"$250 million" "family office" "Chief Investment Officer"', "web_aum250m_cio"),
    ('"$100 million" "family office" "Chief Investment Officer"', "web_aum100m_cio2"),
    
    # Legal/accounting firms serving family offices
    ('"law firm" "family office" "Chief Investment Officer"', "web_law_cio2"),
    ('"accounting firm" "family office" "Chief Investment Officer"', "web_acct_cio"),
    ('"tax advisor" "family office" "Chief Investment Officer"', "web_tax_cio2"),
    
    # International - more regions
    ('"family office" "Tel Aviv" "Chief Investment Officer"', "web_geo_tlv_cio"),
    ('"family office" "Sydney" "Chief Investment Officer"', "web_geo_syd_cio"),
    ('"family office" "Melbourne" "Chief Investment Officer"', "web_geo_mel_cio"),
    ('"family office" "Toronto" "Chief Investment Officer"', "web_geo_yyz_cio"),
    ('"family office" "Vancouver" "Chief Investment Officer"', "web_geo_yvr_cio"),
    ('"family office" "Montreal" "Chief Investment Officer"', "web_geo_yul_cio"),
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

SUMMARY = pathlib.Path("data/raw/discovery_more_v7_summary.json")
with SUMMARY.open("w") as f:
    json.dump({
        "total_hits": total,
        "unique_domains": len(per_domain),
        "by_source_class": per_source_class,
        "top_domains": dict(sorted(per_domain.items(), key=lambda x: -x[1])[:50]),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }, f, indent=2)
print(f"\n[ok] Source summary -> {SUMMARY}")