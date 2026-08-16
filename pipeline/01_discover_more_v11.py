# pipeline/01_discover_more_v11.py
# Discovery pass 11: More targeted angles for family offices

import json
import time
import pathlib
from datetime import datetime, timezone
from urllib.parse import urlparse
from ddgs import DDGS

OUT = pathlib.Path("data/raw/discovery_more_v11.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

QUERIES = [
    # More specific family office names from directories
    ('"family office" "directory" "Chief Investment Officer"', "web_dir_cio2"),
    ('"family office" "database" "Managing Partner"', "web_db_mp2"),
    ('"family office" "list" "Chief Investment Officer"', "web_list_cio"),
    ('"family office" "registry" "Managing Partner"', "web_registry_mp"),
    
    # More specific geographic - US states
    ('"family office" "Colorado" "Chief Investment Officer"', "web_geo_co_cio"),
    ('"family office" "Arizona" "Chief Investment Officer"', "web_geo_az_cio"),
    ('"family office" "Nevada" "Chief Investment Officer"', "web_geo_nv_cio"),
    ('"family office" "Oregon" "Chief Investment Officer"', "web_geo_or_cio"),
    ('"family office" "Washington" "Chief Investment Officer"', "web_geo_wa_cio"),
    ('"family office" "Utah" "Chief Investment Officer"', "web_geo_ut_cio"),
    ('"family office" "New Mexico" "Chief Investment Officer"', "web_geo_nm_cio"),
    ('"family office" "Idaho" "Chief Investment Officer"', "web_geo_id_cio"),
    ('"family office" "Wyoming" "Chief Investment Officer"', "web_geo_wy_cio"),
    ('"family office" "Montana" "Chief Investment Officer"', "web_geo_mt_cio"),
    ('"family office" "North Dakota" "Chief Investment Officer"', "web_geo_nd_cio"),
    ('"family office" "South Dakota" "Chief Investment Officer"', "web_geo_sd_cio"),
    ('"family office" "Nebraska" "Chief Investment Officer"', "web_geo_ne_cio"),
    ('"family office" "Kansas" "Chief Investment Officer"', "web_geo_ks_cio"),
    ('"family office" "Oklahoma" "Chief Investment Officer"', "web_geo_ok_cio"),
    ('"family office" "Arkansas" "Chief Investment Officer"', "web_geo_ar_cio"),
    ('"family office" "Louisiana" "Chief Investment Officer"', "web_geo_la_cio3"),
    ('"family office" "Mississippi" "Chief Investment Officer"', "web_geo_ms_cio"),
    ('"family office" "Alabama" "Chief Investment Officer"', "web_geo_al_cio"),
    ('"family office" "Georgia" "Chief Investment Officer"', "web_geo_ga_cio2"),
    ('"family office" "South Carolina" "Chief Investment Officer"', "web_geo_sc_cio"),
    ('"family office" "Tennessee" "Chief Investment Officer"', "web_geo_tn_cio"),
    ('"family office" "Kentucky" "Chief Investment Officer"', "web_geo_ky_cio3"),
    ('"family office" "West Virginia" "Chief Investment Officer"', "web_geo_wv_cio"),
    ('"family office" "Virginia" "Chief Investment Officer"', "web_geo_va_cio"),
    ('"family office" "Maryland" "Chief Investment Officer"', "web_geo_md_cio"),
    ('"family office" "Delaware" "Chief Investment Officer"', "web_geo_de_cio2"),
    ('"family office" "Pennsylvania" "Chief Investment Officer"', "web_geo_pa_cio2"),
    ('"family office" "New Jersey" "Chief Investment Officer"', "web_geo_nj_cio"),
    ('"family office" "Connecticut" "Chief Investment Officer"', "web_geo_ct_cio"),
    ('"family office" "Rhode Island" "Chief Investment Officer"', "web_geo_ri_cio"),
    ('"family office" "Massachusetts" "Chief Investment Officer"', "web_geo_ma_cio"),
    ('"family office" "New Hampshire" "Chief Investment Officer"', "web_geo_nh_cio"),
    ('"family office" "Vermont" "Chief Investment Officer"', "web_geo_vt_cio"),
    ('"family office" "Maine" "Chief Investment Officer"', "web_geo_me_cio"),
    
    # More international
    ('"family office" "Isle of Man" "Chief Investment Officer"', "web_geo_iom_cio3"),
    ('"family office" "Jersey" "Chief Investment Officer"', "web_geo_je_cio3"),
    ('"family office" "Guernsey" "Chief Investment Officer"', "web_geo_gg_cio3"),
    ('"family office" "Monaco" "Chief Investment Officer"', "web_geo_mco_cio3"),
    ('"family office" "Liechtenstein" "Chief Investment Officer"', "web_geo_lie_cio3"),
    ('"family office" "Andorra" "Chief Investment Officer"', "web_geo_and_cio"),
    ('"family office" "Gibraltar" "Chief Investment Officer"', "web_geo_gib_cio2"),
    ('"family office" "Malta" "Chief Investment Officer"', "web_geo_mt_cio"),
    ('"family office" "Cyprus" "Chief Investment Officer"', "web_geo_cy_cio"),
    ('"family office" "Bahamas" "Chief Investment Officer"', "web_geo_bs_cio3"),
    ('"family office" "Cayman Islands" "Chief Investment Officer"', "web_geo_ky_cio3"),
    ('"family office" "Bermuda" "Chief Investment Officer"', "web_geo_bda_cio3"),
    ('"family office" "British Virgin Islands" "Chief Investment Officer"', "web_geo_vg_cio"),
    ('"family office" "Panama" "Chief Investment Officer"', "web_geo_pa_cio"),
    ('"family office" "Switzerland" "Chief Investment Officer"', "web_geo_ch_cio3"),
    ('"family office" "Luxembourg" "Chief Investment Officer"', "web_geo_lu_cio3"),
    ('"family office" "Liechtenstein" "Chief Investment Officer"', "web_geo_li_cio"),
    ('"family office" "Singapore" "Chief Investment Officer"', "web_geo_sg_cio3"),
    ('"family office" "Hong Kong" "Chief Investment Officer"', "web_geo_hk_cio3"),
    ('"family office" "Dubai" "Chief Investment Officer"', "web_geo_dxb_cio3"),
    ('"family office" "Abu Dhabi" "Chief Investment Officer"', "web_geo_auh_cio3"),
    ('"family office" "Riyadh" "Chief Investment Officer"', "web_geo_ruh_cio3"),
    ('"family office" "Tel Aviv" "Chief Investment Officer"', "web_geo_tlv_cio3"),
    ('"family office" "Tokyo" "Chief Investment Officer"', "web_geo_tyo_cio3"),
    ('"family office" "Shanghai" "Chief Investment Officer"', "web_geo_sha_cio3"),
    ('"family office" "Sydney" "Chief Investment Officer"', "web_geo_syd_cio3"),
    ('"family office" "Melbourne" "Chief Investment Officer"', "web_geo_mel_cio3"),
    ('"family office" "Toronto" "Chief Investment Officer"', "web_geo_yyz_cio3"),
    ('"family office" "Vancouver" "Chief Investment Officer"', "web_geo_yvr_cio3"),
    ('"family office" "Montreal" "Chief Investment Officer"', "web_geo_yul_cio3"),
    ('"family office" "Sao Paulo" "Chief Investment Officer"', "web_geo_gru_cio3"),
    ('"family office" "Mexico City" "Chief Investment Officer"', "web_geo_mex_cio3"),
    
    # More AUM
    ('"$1B" "family office" "Chief Investment Officer"', "web_aum1b_cio4"),
    ('"$2B" "family office" "Chief Investment Officer"', "web_aum2b_cio3"),
    ('"$5B" "family office" "Chief Investment Officer"', "web_aum5b_cio3"),
    ('"$10B" "family office" "Chief Investment Officer"', "web_aum10b_cio3"),
    ('"$100M" "family office" "Chief Investment Officer"', "web_aum100m_cio4"),
    ('"$250M" "family office" "Chief Investment Officer"', "web_aum250m_cio3"),
    ('"$500M" "family office" "Chief Investment Officer"', "web_aum500m_cio4"),
    
    # More strategies
    ('"family office" "impact investing" "Chief Investment Officer"', "web_impact_cio3"),
    ('"family office" "ESG" "Chief Investment Officer"', "web_esg_cio3"),
    ('"family office" "venture capital" "Chief Investment Officer"', "web_vc_cio3"),
    ('"family office" "private equity" "Chief Investment Officer"', "web_pe_cio3"),
    ('"family office" "real estate" "Chief Investment Officer"', "web_re_cio3"),
    ('"family office" "hedge fund" "Chief Investment Officer"', "web_hf_cio3"),
    ('"family office" "public markets" "Chief Investment Officer"', "web_pm_cio3"),
    ('"family office" "alternatives" "Chief Investment Officer"', "web_alt_cio3"),
    ('"family office" "co-investment" "Chief Investment Officer"', "web_coinv_cio3"),
    ('"family office" "direct investing" "Chief Investment Officer"', "web_direct_cio3"),
    ('"family office" "private credit" "Chief Investment Officer"', "web_pc_cio3"),
    ('"family office" "distressed debt" "Chief Investment Officer"', "web_dd_cio3"),
    ('"family office" "secondaries" "Chief Investment Officer"', "web_sec_cio3"),
    ('"family office" "art" "Chief Investment Officer"', "web_art_cio3"),
    ('"family office" "collectibles" "Chief Investment Officer"', "web_collect_cio3"),
    ('"family office" "digital assets" "Chief Investment Officer"', "web_da_cio3"),
    ('"family office" "crypto" "Chief Investment Officer"', "web_crypto_cio3"),
    
    # Networks
    ('"Family Office Exchange" "Chief Investment Officer"', "web_fox_cio3"),
    ('"TIGER 21" "Chief Investment Officer"', "web_tiger21_cio3"),
    ('"Family Office Association" "Chief Investment Officer"', "web_foa_cio3"),
    ('"Family Office Club" "Chief Investment Officer"', "web_foc_cio3"),
    ('"Family Office Summit" "Chief Investment Officer"', "web_fos_cio3"),
    ('"SuperReturn" "family office" "Chief Investment Officer"', "web_superreturn_cio3"),
    
    # Next gen
    ('"next generation" "family office" "Chief Investment Officer"', "web_nextgen_cio4"),
    ('"rising gen" "family office" "Chief Investment Officer"', "web_risinggen_cio4"),
    ('"succession" "family office" "Chief Investment Officer"', "web_succession_cio4"),
    ('"family office" "next gen" "Managing Partner"', "web_nextgen_mp3"),
    ('"family office" "rising gen" "Managing Partner"', "web_risinggen_mp2"),
    
    # Service providers
    ('"family office" "outsourced" "Chief Investment Officer"', "web_outsourced_cio3"),
    ('"virtual family office" "Chief Investment Officer"', "web_vfo_cio3"),
    ('"family office services" "Chief Investment Officer"', "web_fos_cio3"),
    ('"family office platform" "Chief Investment Officer"', "web_fop_cio3"),
    ('"family office technology" "Chief Investment Officer"', "web_fotech_cio3"),
    
    # Legal/accounting
    ('"law firm" "family office" "Chief Investment Officer"', "web_law_cio4"),
    ('"accounting firm" "family office" "Chief Investment Officer"', "web_acct_cio3"),
    ('"tax advisor" "family office" "Chief Investment Officer"', "web_tax_cio4"),
    
    # Philanthropy
    ('"family foundation" "Chief Investment Officer"', "web_ff_cio4"),
    ('"philanthropic" "family office" "Chief Investment Officer"', "web_phil_cio4"),
    
    # Next gen
    ('"next generation" "family office" "Chief Investment Officer"', "web_nextgen_cio5"),
    ('"rising gen" "family office" "Chief Investment Officer"', "web_risinggen_cio5"),
    ('"succession" "family office" "Chief Investment Officer"', "web_succession_cio5"),
    ('"family office" "next gen" "Managing Partner"', "web_nextgen_mp4"),
    
    # Legal/accounting
    ('"law firm" "family office" "Chief Investment Officer"', "web_law_cio5"),
    ('"accounting firm" "family office" "Chief Investment Officer"', "web_acct_cio4"),
    ('"tax advisor" "family office" "Chief Investment Officer"', "web_tax_cio5"),
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

SUMMARY = pathlib.Path("data/raw/discovery_more_v11_summary.json")
with SUMMARY.open("w") as f:
    json.dump({
        "total_hits": total,
        "unique_domains": len(per_domain),
        "by_source_class": per_source_class,
        "top_domains": dict(sorted(per_domain.items(), key=lambda x: -x[1])[:50]),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }, f, indent=2)
print(f"\n[ok] Source summary -> {SUMMARY}")