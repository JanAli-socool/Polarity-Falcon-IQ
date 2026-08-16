# pipeline/01b_discover_more_v2.py
# Additional discovery passes targeting known family office directories and lists.

import json
import time
import pathlib
from datetime import datetime, timezone
from urllib.parse import urlparse
from ddgs import DDGS

OUT = pathlib.Path("data/raw/discovery_more_v2.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

# Targeted queries for known directories, lists, and specific firm names
QUERIES = [
    # Known family office directories
    ('site:familyofficedirectory.com "family office"', "directory_familyofficedirectory"),
    ('site:simplefamilyoffice.com "family office"', "directory_simplefamilyoffice"),
    ('site:familyoffice.com "family office"', "directory_familyoffice"),
    ('site:thefopro.com "family office"', "directory_thefopro"),
    ('site:efamilyoffices.com "family office"', "directory_efamilyoffices"),
    ('site:paminsight.com "family office"', "directory_paminsight"),
    ('site:cowenpartners.com "family office"', "directory_cowenpartners"),
    ('site:russellreynolds.com "family office"', "directory_russellreynolds"),
    ('site:heidrick.com "family office"', "directory_heidrick"),
    ('site:spencerstuart.com "family office"', "directory_spencerstuart"),
    ('site:kornferry.com "family office"', "directory_kornferry"),

    # Industry publications with family office lists
    ('"top family offices" 2024 OR 2025', "industry_list"),
    ('"largest family offices" "AUM" 2024', "industry_list"),
    ('"family office" "billion" "AUM" list', "industry_list"),
    ('"single family office" "net worth" "billion"', "industry_list"),

    # Specific known family offices (from public knowledge)
    ('"Rockefeller" family office', "known_firm"),
    ('"Pritzker" family office', "known_firm"),
    ('"Walton" family office', "known_firm"),
    ('"Cox" family office', "known_firm"),
    ('"Mars" family office', "known_firm"),
    ('"Koch" family office', "known_firm"),
    ('"Johnson" family office', "known_firm"),
    ('"Hearst" family office', "known_firm"),
    ('"Newhouse" family office', "known_firm"),
    ('"Ochs" family office', "known_firm"),
    ('"Scripps" family office', "known_firm"),
    ('"Cargill" family office', "known_firm"),
    ('"Simmons" family office', "known_firm"),
    ('"Hunt" family office', "known_firm"),
    ('"Perot" family office', "known_firm"),
    ('"Bass" family office', "known_firm"),
    ('"Bassett" family office', "known_firm"),
    ('"Bourne" family office', "known_firm"),

    # Multi-family office platforms
    ('"multi-family office" platform "team"', "mfo_platform"),
    ('"multi family office" "chief investment officer"', "mfo_platform"),
    ('"independent family office" "team"', "mfo_platform"),

    # Geographic searches
    ('"family office" "New York" "team"', "geo_ny"),
    ('"family office" "San Francisco" "team"', "geo_sf"),
    ('"family office" "Chicago" "team"', "geo_chi"),
    ('"family office" "Los Angeles" "team"', "geo_la"),
    ('"family office" "Boston" "team"', "geo_bos"),
    ('"family office" "Miami" "team"', "geo_mia"),
    ('"family office" "Dallas" "team"', "geo_dal"),
    ('"family office" "Houston" "team"', "geo_hou"),
    ('"family office" "Seattle" "team"', "geo_sea"),
    ('"family office" "Denver" "team"', "geo_den"),
    ('"family office" "Atlanta" "team"', "geo_atl"),
    ('"family office" "Washington DC" "team"', "geo_dc"),
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
        time.sleep(1.2)

print(f"\n[ok] {total} hits across {len(per_domain)} distinct domains -> {OUT}")
print("\n[by source class]")
for cls, cnt in sorted(per_source_class.items(), key=lambda x: -x[1]):
    print(f"  {cnt:>3}  {cls}")

print("\n[top 30 domains]")
for d, c in sorted(per_domain.items(), key=lambda x: -x[1])[:30]:
    print(f"  {c:>3}  {d}")