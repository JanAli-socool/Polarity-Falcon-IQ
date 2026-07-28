# pipeline/01_discover_probe.py
# PROBE: prove free multi-angle discovery works BEFORE we commit hours to it.
# We are searching for FIRMS first; people come in the next step.

import json, time, pathlib
from datetime import datetime, timezone
from urllib.parse import urlparse
from ddgs import DDGS                     # NEW

OUT = pathlib.Path("data/raw/discovery_probe.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

# 4 DELIBERATELY DIFFERENT angles so we don't inherit one directory's
# blind spots. Each angle tends to surface a different domain mix.
QUERIES = [
    'site:linkedin.com/company "family office" United States',
    '"single family office" team OR leadership site:*.com -site:wikipedia.org',
    '"family office" "chief investment officer" OR "managing director" 2024',
    '"family office" press release appoints OR names OR joins',
]

ddgs = DDGS()
total, per_domain = 0, {}
with OUT.open("w", encoding="utf-8") as f:
    for q in QUERIES:
        try:
            results = ddgs.text(q, max_results=10)
        except Exception as e:
            print(f"[warn] query failed: {q!r} -> {e!r}")
            results = []
        for r in results:
            url = r.get("href", "")
            domain = urlparse(url).netloc.lower().lstrip("www.")
            per_domain[domain] = per_domain.get(domain, 0) + 1
            f.write(json.dumps({
                "query": q,
                "title": r.get("title", ""),
                "url": url,
                "domain": domain,
                "snippet": r.get("body", ""),
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False) + "\n")
            total += 1
        time.sleep(1)  # polite pacing

print(f"[ok] wrote {total} hits across {len(per_domain)} distinct domains -> {OUT}")
print("[top domains]")
for d, c in sorted(per_domain.items(), key=lambda x: -x[1])[:10]:
    print(f"  {c:>3}  {d}")