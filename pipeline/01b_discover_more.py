# pipeline/01b_discover_more.py
# Second discovery pass — APPENDS to the same file with new query angles.
# Different angles surface different domains, which is exactly what we
# need to push more firms into the ≥2-domain "verified" bucket.

import json, time, pathlib
from datetime import datetime, timezone
from urllib.parse import urlparse
from ddgs import DDGS

OUT = pathlib.Path("data/raw/discovery_probe.jsonl")

# NEW angles, deliberately non-overlapping with the first probe.
# Each targets a different corner of the ecosystem.
QUERIES = [
    '"family office" appointed OR promoted OR joined 2024',      # PR/news angle
    '"family office" "team" OR "our people" site:*.com',         # firm team pages
    '"single family office" -directory -list -"top 10"',         # avoid aggregators
    '"multi-family office" founded OR established United States',
    'family office "portfolio" OR "investments" site:*.com',
    '"CIO" OR "CFO" "family office" LinkedIn',
    'Form ADV "family office" site:sec.gov',                     # regulatory
    '"family office" philanthropy OR foundation grant',
]

ddgs = DDGS()
existing = set()
if OUT.exists():
    with OUT.open(encoding="utf-8") as f:
        for line in f:
            try: existing.add(json.loads(line)["url"])
            except: pass

total, dedup = 0, 0
per_domain = {}
with OUT.open("a", encoding="utf-8") as f:
    for q in QUERIES:
        try:
            results = ddgs.text(q, max_results=10)
        except Exception as e:
            print(f"[warn] {q!r} -> {e!r}")
            results = []
        for r in results:
            url = r.get("href","")
            if url in existing:
                dedup += 1
                continue
            existing.add(url)
            domain = urlparse(url).netloc.lower().lstrip("www.")
            per_domain[domain] = per_domain.get(domain, 0) + 1
            f.write(json.dumps({
                "query": q,
                "title": r.get("title",""),
                "url": url,
                "domain": domain,
                "snippet": r.get("body",""),
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False) + "\n")
            total += 1
        time.sleep(1)

print(f"[ok] appended {total} NEW hits ({dedup} dedup'd) across {len(per_domain)} new domains")
print("[new top domains]")
for d,c in sorted(per_domain.items(), key=lambda x:-x[1])[:10]:
    print(f"  {c:>3}  {d}")