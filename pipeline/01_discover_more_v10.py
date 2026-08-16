# pipeline/01_discover_more_v10.py
# Discovery pass 10: More angles for additional firms

import json
import time
import pathlib
from datetime import datetime, timezone
from urllib.parse import urlparse
from ddgs import DDGS

OUT = pathlib.Path("data/raw/discovery_more_v10.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

QUERIES = [
    # More appointment/news - specific recent
    ('"family office" "appointed" "Chief Investment Officer" 2025', "web_news_cio_2025"),
    ('"family office" "appointed" "Managing Partner" 2025', "web_news_mp_2025"),
    ('"family office" "hired" "Managing Director" 2025', "web_news_md_2025"),
    ('"family office" "promoted" "Partner" 2025', "web_news_partner_2025"),
    ('"family office" "joined" "Chief Investment Officer" 2024 OR 2025', "web_news_cio_joined"),
    
    # More specific firm types
    ('"single family office" "Chief Operating Officer"', "web_sfo_coo2"),
    ('"single family office" "Chief Financial Officer"', "web_sfo_cfo2"),
    ('"single family office" "General Counsel"', "web_sfo_gc2"),
    ('"multi-family office" "Chief Operating Officer"', "web_mfo_coo2"),
    ('"multi-family office" "Chief Financial Officer"', "web_mfo_cfo2"),
    ('"multi-family office" "Head of Investments"', "web_mfo_hoi2"),
    ('"family office" "Head of Private Investments"', "web_fo_hpi"),
    ('"family office" "Head of Alternative Investments"', "web_fo_hai"),
    ('"family office" "Head of Real Estate"', "web_fo_hre"),
    ('"family office" "Head of Venture Capital"', "web_fo_hvc"),
    
    # More US cities
    ('"family office" "Phoenix" "Chief Investment Officer"', "web_geo_phx_cio2"),
    ('"family office" "Austin" "Chief Investment Officer"', "web_geo_atx_cio2"),
    ('"family office" "Nashville" "Chief Investment Officer"', "web_geo_bna_cio2"),
    ('"family office" "Raleigh" "Chief Investment Officer"', "web_geo_rdu_cio2"),
    ('"family office" "Charlotte" "Chief Investment Officer"', "web_geo_clt_cio2"),
    ('"family office" "Salt Lake City" "Chief Investment Officer"', "web_geo_slc_cio2"),
    ('"family office" "Portland" "Chief Investment Officer"', "web_geo_pdx_cio2"),
    ('"family office" "San Diego" "Chief Investment Officer"', "web_geo_san_cio2"),
    ('"family office" "Tampa" "Chief Investment Officer"', "web_geo_tpa_cio2"),
    ('"family office" "Orlando" "Chief Investment Officer"', "web_geo_mco_cio2"),
    ('"family office" "Minneapolis" "Chief Investment Officer"', "web_geo_msp_cio2"),
    ('"family office" "Seattle" "Chief Investment Officer"', "web_geo_sea_cio2"),
    ('"family office" "Denver" "Chief Investment Officer"', "web_geo_den_cio2"),
    ('"family office" "Atlanta" "Chief Investment Officer"', "web_geo_atl_cio2"),
    
    # International - more specific
    ('"family office" "Cayman Islands" "Chief Investment Officer"', "web_geo_cay_cio2"),
    ('"family office" "Bermuda" "Chief Investment Officer"', "web_geo_bda_cio2"),
    ('"family office" "Luxembourg" "Chief Investment Officer"', "web_geo_lux_cio2"),
    ('"family office" "Jersey" "Chief Investment Officer"', "web_geo_jay_cio2"),
    ('"family office" "Guernsey" "Chief Investment Officer"', "web_geo_ggy_cio2"),
    ('"family office" "Isle of Man" "Chief Investment Officer"', "web_geo_iom_cio2"),
    ('"family office" "Gibraltar" "Chief Investment Officer"', "web_geo_gib_cio"),
    ('"family office" "Monaco" "Chief Investment Officer"', "web_geo_mco_cio2"),
    ('"family office" "Liechtenstein" "Chief Investment Officer"', "web_geo_lie_cio2"),
    ('"family office" "Switzerland" "Chief Investment Officer"', "web_geo_che_cio2"),
    ('"family office" "Singapore" "Chief Investment Officer"', "web_geo_sgp_cio2"),
    ('"family office" "Hong Kong" "Chief Investment Officer"', "web_geo_hkg_cio2"),
    ('"family office" "Dubai" "Chief Investment Officer"', "web_geo_dxb_cio2"),
    ('"family office" "Abu Dhabi" "Chief Investment Officer"', "web_geo_auh_cio2"),
    ('"family office" "Riyadh" "Chief Investment Officer"', "web_geo_ruh_cio2"),
    ('"family office" "Tel Aviv" "Chief Investment Officer"', "web_geo_tlv_cio2"),
    ('"family office" "Tokyo" "Chief Investment Officer"', "web_geo_tyo_cio2"),
    ('"family office" "Shanghai" "Chief Investment Officer"', "web_geo_sha_cio2"),
    ('"family office" "Sydney" "Chief Investment Officer"', "web_geo_syd_cio2"),
    ('"family office" "Melbourne" "Chief Investment Officer"', "web_geo_mel_cio2"),
    ('"family office" "Toronto" "Chief Investment Officer"', "web_geo_yyz_cio2"),
    ('"family office" "Vancouver" "Chief Investment Officer"', "web_geo_yvr_cio2"),
    ('"family office" "Montreal" "Chief Investment Officer"', "web_geo_yul_cio2"),
    ('"family office" "Sao Paulo" "Chief Investment Officer"', "web_geo_gru_cio2"),
    ('"family office" "Mexico City" "Chief Investment Officer"', "web_geo_mex_cio2"),
    
    # Specific strategies
    ('"family office" "private credit" "Chief Investment Officer"', "web_pc_cio2"),
    ('"family office" "distressed debt" "Chief Investment Officer"', "web_dd_cio2"),
    ('"family office" "secondaries" "Chief Investment Officer"', "web_sec_cio2"),
    ('"family office" "co-investment" "Chief Investment Officer"', "web_coinv_cio2"),
    ('"family office" "direct investing" "Chief Investment Officer"', "web_direct_cio2"),
    ('"family office" "venture capital" "Chief Investment Officer"', "web_vc_cio2"),
    ('"family office" "growth equity" "Chief Investment Officer"', "web_ge_cio2"),
    ('"family office" "buyout" "Chief Investment Officer"', "web_buyout_cio2"),
    ('"family office" "real assets" "Chief Investment Officer"', "web_ra_cio2"),
    ('"family office" "infrastructure" "Chief Investment Officer"', "web_infra_cio2"),
    ('"family office" "natural resources" "Chief Investment Officer"', "web_nr_cio2"),
    ('"family office" "digital assets" "Chief Investment Officer"', "web_da_cio2"),
    ('"family office" "crypto" "Chief Investment Officer"', "web_crypto_cio2"),
    ('"family office" "art" "Chief Investment Officer"', "web_art_cio2"),
    ('"family office" "collectibles" "Chief Investment Officer"', "web_collect_cio2"),
    
    # Family office networks
    ('"Family Office Exchange" "Chief Investment Officer"', "web_fox_cio2"),
    ('"TIGER 21" "Chief Investment Officer"', "web_tiger21_cio2"),
    ('"Family Office Association" "Chief Investment Officer"', "web_foa_cio2"),
    ('"Family Office Club" "Chief Investment Officer"', "web_foc_cio2"),
    ('"Family Office Summit" "Chief Investment Officer"', "web_fos_cio2"),
    ('"SuperReturn" "family office" "Chief Investment Officer"', "web_superreturn_cio2"),
    
    # Next gen / succession
    ('"next generation" "family office" "Chief Investment Officer"', "web_nextgen_cio2"),
    ('"rising gen" "family office" "Chief Investment Officer"', "web_risinggen_cio2"),
    ('"succession" "family office" "Chief Investment Officer"', "web_succession_cio2"),
    ('"family office" "next gen" "Managing Partner"', "web_nextgen_mp2"),
    ('"family office" "rising gen" "Managing Partner"', "web_risinggen_mp"),
    
    # Service providers
    ('"family office" "outsourced" "Chief Investment Officer"', "web_outsourced_cio2"),
    ('"virtual family office" "Chief Investment Officer"', "web_vfo_cio2"),
    ('"family office services" "Chief Investment Officer"', "web_fos_cio2"),
    ('"family office platform" "Chief Investment Officer"', "web_fop_cio2"),
    ('"family office technology" "Chief Investment Officer"', "web_fotech_cio2"),
    
    # More AUM ranges
    ('"$1B" "family office" "Chief Investment Officer"', "web_aum1b_cio3"),
    ('"$2B" "family office" "Chief Investment Officer"', "web_aum2b_cio2"),
    ('"$5B" "family office" "Chief Investment Officer"', "web_aum5b_cio2"),
    ('"$10B" "family office" "Chief Investment Officer"', "web_aum10b_cio2"),
    ('"$100M" "family office" "Chief Investment Officer"', "web_aum100m_cio3"),
    ('"$250M" "family office" "Chief Investment Officer"', "web_aum250m_cio2"),
    ('"$500M" "family office" "Chief Investment Officer"', "web_aum500m_cio3"),
    
    # Professional services
    ('"law firm" "family office" "Chief Investment Officer"', "web_law_cio3"),
    ('"accounting firm" "family office" "Chief Investment Officer"', "web_acct_cio2"),
    ('"tax advisor" "family office" "Chief Investment Officer"', "web_tax_cio3"),
    
    # Philanthropy/foundations
    ('"family foundation" "Chief Investment Officer"', "web_ff_cio3"),
    ('"philanthropic" "family office" "Chief Investment Officer"', "web_phil_cio3"),
    
    # Next gen/rising gen
    ('"next generation" "family office" "Chief Investment Officer"', "web_nextgen_cio3"),
    ('"rising gen" "family office" "Chief Investment Officer"', "web_risinggen_cio3"),
    ('"succession" "family office" "Chief Investment Officer"', "web_succession_cio3"),
    ('"family office" "next gen" "Managing Partner"', "web_nextgen_mp2"),
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

SUMMARY = pathlib.Path("data/raw/discovery_more_v10_summary.json")
with SUMMARY.open("w") as f:
    json.dump({
        "total_hits": total,
        "unique_domains": len(per_domain),
        "by_source_class": per_source_class,
        "top_domains": dict(sorted(per_domain.items(), key=lambda x: -x[1])[:50]),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }, f, indent=2)
print(f"\n[ok] Source summary -> {SUMMARY}")