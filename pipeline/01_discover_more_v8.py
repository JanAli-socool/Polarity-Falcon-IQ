# pipeline/01_discover_more_v8.py
# Discovery pass 8: Even more targeted angles

import json
import time
import pathlib
from datetime import datetime, timezone
from urllib.parse import urlparse
from ddgs import DDGS

OUT = pathlib.Path("data/raw/discovery_more_v8.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

QUERIES = [
    # More appointment/news signals
    ('"family office" "appointed" "Managing Director" 2024 OR 2025', "web_news_md_2024_2"),
    ('"family office" "appointed" "Partner" 2024 OR 2025', "web_news_partner_2024_2"),
    ('"family office" "hired" "Chief Investment Officer" 2024 OR 2025', "web_news_cio_2024_2"),
    ('"family office" "promoted" "Managing Partner" 2024 OR 2025', "web_news_mp_2024_2"),
    
    # More geographic - US secondary cities
    ('"family office" "Nashville" "Managing Partner"', "web_geo_bna_mp"),
    ('"family office" "Raleigh" "Chief Investment Officer"', "web_geo_rdu_cio2"),
    ('"family office" "Salt Lake City" "Chief Investment Officer"', "web_geo_slc_cio"),
    ('"family office" "Kansas City" "Chief Investment Officer"', "web_geo_mci_cio"),
    ('"family office" "Indianapolis" "Chief Investment Officer"', "web_geo_ind_cio"),
    ('"family office" "Columbus" "Chief Investment Officer"', "web_geo_cmh_cio"),
    ('"family office" "Cincinnati" "Chief Investment Officer"', "web_geo_cvg_cio"),
    ('"family office" "Pittsburgh" "Chief Investment Officer"', "web_geo_pit_cio"),
    ('"family office" "Cleveland" "Chief Investment Officer"', "web_geo_cle_cio"),
    ('"family office" "Detroit" "Chief Investment Officer"', "web_geo_dtw_cio"),
    
    # More international
    ('"family office" "Copenhagen" "Chief Investment Officer"', "web_geo_cph_cio"),
    ('"family office" "Stockholm" "Chief Investment Officer"', "web_geo_arn_cio"),
    ('"family office" "Oslo" "Chief Investment Officer"', "web_geo_osl_cio"),
    ('"family office" "Helsinki" "Chief Investment Officer"', "web_geo_hel_cio"),
    ('"family office" "Vienna" "Chief Investment Officer"', "web_geo_vie_cio"),
    ('"family office" "Amsterdam" "Chief Investment Officer"', "web_geo_ams_cio"),
    ('"family office" "Brussels" "Chief Investment Officer"', "web_geo_brussels_cio"),
    ('"family office" "Madrid" "Chief Investment Officer"', "web_geo_mad_cio"),
    ('"family office" "Barcelona" "Chief Investment Officer"', "web_geo_bcn_cio"),
    ('"family office" "Milan" "Chief Investment Officer"', "web_geo_mil_cio"),
    ('"family office" "Rome" "Chief Investment Officer"', "web_geo_fco_cio"),
    ('"family office" "Paris" "Chief Investment Officer"', "web_geo_cdg_cio"),
    ('"family office" "Frankfurt" "Chief Investment Officer"', "web_geo_fra_cio"),
    ('"family office" "Munich" "Chief Investment Officer"', "web_geo_muc_cio"),
    
    # Specific family office service providers
    ('"family office" "consulting" "Chief Investment Officer"', "web_fo_consult_cio"),
    ('"family office" "advisory" "Chief Investment Officer"', "web_fo_advisory_cio"),
    ('"family office" "wealth planning" "Chief Investment Officer"', "web_fo_wp_cio"),
    
    # Specific AUM
    ('"$2 billion" "family office" "Chief Investment Officer"', "web_aum2b_cio"),
    ('"$3 billion" "family office" "Chief Investment Officer"', "web_aum3b_cio"),
    ('"$10 billion" "family office" "Chief Investment Officer"', "web_aum10b_cio"),
    
    # Specific strategies
    ('"family office" "digital assets" "Chief Investment Officer"', "web_da_cio"),
    ('"family office" "crypto" "Chief Investment Officer"', "web_crypto_cio"),
    ('"family office" "art" "Chief Investment Officer"', "web_art_cio"),
    ('"family office" "collectibles" "Chief Investment Officer"', "web_collect_cio"),
    
    # Family office networks
    ('"family office" "peer group" "Chief Investment Officer"', "web_fo_peer_cio"),
    ('"family office" "mastermind" "Chief Investment Officer"', "web_fo_mastermind_cio"),
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

SUMMARY = pathlib.Path("data/raw/discovery_more_v8_summary.json")
with SUMMARY.open("w") as f:
    json.dump({
        "total_hits": total,
        "unique_domains": len(per_domain),
        "by_source_class": per_source_class,
        "top_domains": dict(sorted(per_domain.items(), key=lambda x: -x[1])[:50]),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }, f, indent=2)
print(f"\n[ok] Source summary -> {SUMMARY}")