# pipeline/01_discover_more_v9.py
# Discovery pass 9: Additional angles for more firms

import json
import time
import pathlib
from datetime import datetime, timezone
from urllib.parse import urlparse
from ddgs import DDGS

OUT = pathlib.Path("data/raw/discovery_more_v9.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

QUERIES = [
    # More specific appointment signals
    ('"family office" "appointed" "Chief Investment Officer" site:linkedin.com', "linkedin_cio_appt"),
    ('"family office" "appointed" "Managing Partner" site:linkedin.com', "linkedin_mp_appt"),
    ('"family office" "hired" "Managing Director" site:linkedin.com', "linkedin_md_hired"),
    ('"family office" "promoted" "Partner" site:linkedin.com', "linkedin_partner_promo"),
    
    # Specific firm structures
    ('"single family office" "Chief Operating Officer"', "web_sfo_coo"),
    ('"single family office" "Chief Financial Officer"', "web_sfo_cfo"),
    ('"single family office" "General Counsel"', "web_sfo_gc"),
    ('"multi-family office" "Chief Operating Officer"', "web_mfo_coo"),
    ('"multi-family office" "Chief Financial Officer"', "web_mfo_cfo"),
    ('"multi-family office" "Head of Investments"', "web_mfo_hoi"),
    
    # More international
    ('"family office" "Monaco" "Chief Investment Officer"', "web_geo_mco_cio"),
    ('"family office" "Cayman" "Chief Investment Officer"', "web_geo_cay_cio"),
    ('"family office" "Bermuda" "Chief Investment Officer"', "web_geo_bda_cio"),
    ('"family office" "Isle of Man" "Chief Investment Officer"', "web_geo_iom_cio"),
    ('"family office" "Guernsey" "Chief Investment Officer"', "web_geo_ggy_cio"),
    ('"family office" "Jersey" "Chief Investment Officer"', "web_geo_jay_cio"),
    ('"family office" "Luxembourg" "Chief Investment Officer"', "web_geo_lux_cio"),
    ('"family office" "Liechtenstein" "Chief Investment Officer"', "web_geo_lie_cio"),
    ('"family office" "Switzerland" "Chief Investment Officer"', "web_geo_che_cio"),
    ('"family office" "Singapore" "Chief Investment Officer"', "web_geo_sgp_cio"),
    ('"family office" "Hong Kong" "Chief Investment Officer"', "web_geo_hkg_cio"),
    ('"family office" "Dubai" "Chief Investment Officer"', "web_geo_dxb_cio"),
    ('"family office" "Abu Dhabi" "Chief Investment Officer"', "web_geo_auh_cio"),
    ('"family office" "Riyadh" "Chief Investment Officer"', "web_geo_ruh_cio"),
    ('"family office" "Tel Aviv" "Chief Investment Officer"', "web_geo_tlv_cio"),
    ('"family office" "Tokyo" "Chief Investment Officer"', "web_geo_tyo_cio"),
    ('"family office" "Shanghai" "Chief Investment Officer"', "web_geo_sha_cio"),
    ('"family office" "Sydney" "Chief Investment Officer"', "web_geo_syd_cio"),
    ('"family office" "Melbourne" "Chief Investment Officer"', "web_geo_mel_cio"),
    ('"family office" "Toronto" "Chief Investment Officer"', "web_geo_yyz_cio"),
    ('"family office" "Vancouver" "Chief Investment Officer"', "web_geo_yvr_cio"),
    ('"family office" "Montreal" "Chief Investment Officer"', "web_geo_yul_cio"),
    ('"family office" "Sao Paulo" "Chief Investment Officer"', "web_geo_gru_cio"),
    ('"family office" "Mexico City" "Chief Investment Officer"', "web_geo_mex_cio"),
    
    # Specific strategies
    ('"family office" "private credit" "Chief Investment Officer"', "web_pc_cio"),
    ('"family office" "distressed debt" "Chief Investment Officer"', "web_dd_cio"),
    ('"family office" "secondaries" "Chief Investment Officer"', "web_sec_cio"),
    ('"family office" "co-investment" "Chief Investment Officer"', "web_coinv_cio"),
    ('"family office" "direct investing" "Chief Investment Officer"', "web_direct_cio"),
    ('"family office" "venture capital" "Chief Investment Officer"', "web_vc_cio"),
    ('"family office" "growth equity" "Chief Investment Officer"', "web_ge_cio"),
    ('"family office" "buyout" "Chief Investment Officer"', "web_buyout_cio"),
    ('"family office" "real assets" "Chief Investment Officer"', "web_ra_cio"),
    ('"family office" "infrastructure" "Chief Investment Officer"', "web_infra_cio"),
    ('"family office" "natural resources" "Chief Investment Officer"', "web_nr_cio"),
    
    # Specific AUM
    ('"$1B" "family office" "Chief Investment Officer"', "web_aum1b_cio"),
    ('"$2B" "family office" "Chief Investment Officer"', "web_aum2b_cio"),
    ('"$5B" "family office" "Chief Investment Officer"', "web_aum5b_cio"),
    ('"$10B" "family office" "Chief Investment Officer"', "web_aum10b_cio"),
    ('"$100M" "family office" "Chief Investment Officer"', "web_aum100m_cio"),
    ('"$250M" "family office" "Chief Investment Officer"', "web_aum250m_cio"),
    ('"$500M" "family office" "Chief Investment Officer"', "web_aum500m_cio"),
    
    # Family office networks
    ('"FOX" "Family Office Exchange" "Chief Investment Officer"', "web_fox_cio"),
    ('"TIGER 21" "Chief Investment Officer"', "web_tiger21_cio"),
    ('"Family Office Association" "Chief Investment Officer"', "web_foa_cio"),
    ('"Family Office Club" "Chief Investment Officer"', "web_foc_cio"),
    ('"Family Office Summit" "Chief Investment Officer"', "web_fos_cio"),
    ('"SuperReturn" "family office" "Chief Investment Officer"', "web_superreturn_cio"),
    
    # Next gen / succession
    ('"next generation" "family office" "Chief Investment Officer"', "web_nextgen_cio"),
    ('"rising gen" "family office" "Chief Investment Officer"', "web_risinggen_cio"),
    ('"succession" "family office" "Chief Investment Officer"', "web_succession_cio"),
    ('"family office" "next gen" "Managing Partner"', "web_nextgen_mp"),
    
    # Service providers
    ('"family office" "outsourced" "Chief Investment Officer"', "web_outsourced_cio"),
    ('"virtual family office" "Chief Investment Officer"', "web_vfo_cio"),
    ('"family office services" "Chief Investment Officer"', "web_fos_cio"),
    ('"family office platform" "Chief Investment Officer"', "web_fop_cio"),
    ('"family office technology" "Chief Investment Officer"', "web_fotech_cio"),
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

SUMMARY = pathlib.Path("data/raw/discovery_more_v9_summary.json")
with SUMMARY.open("w") as f:
    json.dump({
        "total_hits": total,
        "unique_domains": len(per_domain),
        "by_source_class": per_source_class,
        "top_domains": dict(sorted(per_domain.items(), key=lambda x: -x[1])[:50]),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }, f, indent=2)
print(f"\n[ok] Source summary -> {SUMMARY}")