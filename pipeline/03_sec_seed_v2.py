# pipeline/03_sec_seed_v2.py
# Expanded SEC EDGAR search for registered investment advisors identifying as family offices.

import json
import time
import pathlib
import requests

OUT = pathlib.Path("data/raw/sec_seed_v2.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

BASE = "https://efts.sec.gov/LATEST/search-index"
HEADERS = {
    "User-Agent": "Falcon Assessment Research contact@example.com",
    "Accept": "application/json",
}

# More comprehensive queries
QUERIES = [
    ('"family office"', "ADV"),
    ('"single family office"', ""),
    ('"multi-family office"', ""),
    ('"family investment office"', ""),
    ('"family wealth office"', ""),
    ('"family office" "registered investment adviser"', "ADV"),
    ('"single family office" "registered investment adviser"', "ADV"),
    ('"multi-family office" "registered investment adviser"', "ADV"),
]

seen_ciks = set()
rows = []

for q, forms in QUERIES:
    params = {"q": q, "page": 0, "size": 100}
    if forms:
        params["forms"] = forms
    try:
        r = requests.get(BASE, params=params, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[warn] {q!r} -> {e!r}")
        continue

    hits = data.get("hits", {}).get("hits", [])
    print(f"[info] query {q!r} forms={forms or 'any'}: {len(hits)} filings")

    for h in hits:
        src = h.get("_source", {})
        ciks = src.get("ciks", [])
        names = src.get("display_names", [])
        for cik in ciks:
            if cik in seen_ciks:
                continue
            seen_ciks.add(cik)
            rows.append({
                "cik": cik,
                "display_names": names,
                "form": src.get("form", ""),
                "file_date": src.get("file_date", ""),
                "adsh": src.get("adsh", ""),
                "query": q,
                "filing_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}",
            })
    time.sleep(1)

with OUT.open("w", encoding="utf-8") as f:
    for row in rows:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

print(f"\n[ok] {len(rows)} unique CIKs -> {OUT}")
print("\n[first 30 firms found in SEC]")
for row in rows[:30]:
    names = " | ".join(row["display_names"][:2])[:100]
    print(f"  CIK {row['cik']:>10}  {names}")