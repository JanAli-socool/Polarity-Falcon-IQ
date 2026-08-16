# pipeline/04_verify_firms.py
# For each candidate firm, find its OWN website and verify the site
# self-identifies as a family office. This is our strongest verification.

import json, re, time, pathlib
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

IN  = pathlib.Path("data/raw/firm_candidates.jsonl")
SEC = pathlib.Path("data/raw/sec_seed.jsonl")
OUT = pathlib.Path("data/raw/firms_verified.jsonl")

# Load candidates from BOTH arms
candidates = []
with IN.open(encoding="utf-8") as f:
    for line in f:
        c = json.loads(line)
        candidates.append({"name": c["firm_name"], "source_arm": "web",
                           "web_domains": c["domains"],
                           "web_evidence": c["evidence"][:2]})

if SEC.exists():
    with SEC.open(encoding="utf-8") as f:
        for line in f:
            s = json.loads(line)
            for name in s.get("display_names", [])[:1]:
                # SEC display names look like "SMITH CAPITAL LLC /CIK123/"
                clean = re.sub(r"\s*/.*$", "", name).strip()
                if clean:
                    candidates.append({"name": clean, "source_arm": "sec",
                                       "cik": s["cik"],
                                       "filing_url": s["filing_url"]})

# Skip generic/junk names for the verification pass
GENERIC = {"global family office","united states family offices",
           "core family office","future family office","u.s. family office"}
candidates = [c for c in candidates
              if c["name"].lower() not in GENERIC
              and len(c["name"]) >= 5]

print(f"[info] {len(candidates)} candidates to verify (web+SEC merged)")

# Cap for time budget — verify top 40, rest go to backlog
BUDGET = 40
candidates = candidates[:BUDGET]

HEADERS = {"User-Agent": "Mozilla/5.0 (research; contact@example.com)"}
ddgs = DDGS()
verified = []

def find_official_site(firm_name: str) -> tuple[str, str] | None:
    """Return (url, title) of best-guess official site, or None."""
    try:
        results = ddgs.text(f'"{firm_name}" official site', max_results=5)
    except Exception:
        return None
    firm_tokens = set(re.findall(r"[a-z]{3,}", firm_name.lower()))
    for r in results:
        url = r.get("href","")
        domain = urlparse(url).netloc.lower().lstrip("www.")
        # Skip social/aggregator platforms as the "official" site
        if any(s in domain for s in ["linkedin","facebook","twitter","wikipedia",
                                     "bloomberg","forbes","cnbc","sec.gov",
                                     "tracxn","axial","crunchbase","pitchbook"]):
            continue
        # Prefer domains whose name overlaps with firm tokens
        dom_tokens = set(re.findall(r"[a-z]{3,}", domain))
        if firm_tokens & dom_tokens:
            return url, r.get("title","")
    # fallback: first non-social result
    for r in results:
        url = r.get("href","")
        domain = urlparse(url).netloc.lower().lstrip("www.")
        if not any(s in domain for s in ["linkedin","facebook","twitter","wikipedia"]):
            return url, r.get("title","")
    return None

def site_confirms_fo(url: str) -> tuple[bool, str]:
    """Fetch URL; return (True, snippet) if site self-describes as family office."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        if r.status_code != 200:
            return False, f"http {r.status_code}"
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script","style","nav","footer"]):
            tag.decompose()
        text = re.sub(r"\s+", " ", soup.get_text(" "))
        low = text.lower()
        for phrase in ["family office","single-family office","multi-family office",
                       "family-owned investment","family wealth"]:
            if phrase in low:
                i = low.find(phrase)
                snippet = text[max(0,i-60):i+120].strip()
                return True, snippet
        return False, "no FO self-description"
    except Exception as e:
        return False, f"fetch error: {type(e).__name__}"

for i, cand in enumerate(candidates, 1):
    name = cand["name"]
    print(f"[{i:>2}/{len(candidates)}] {name[:50]:<50}", end=" ", flush=True)
    site = find_official_site(name)
    if not site:
        print("no site found")
        continue
    url, title = site
    ok, evidence = site_confirms_fo(url)
    status = "VERIFIED" if ok else f"FAILED: {evidence[:30]}"
    print(f"{status}  {urlparse(url).netloc}")
    if ok:
        verified.append({
            "firm_name": name,
            "official_url": url,
            "official_title": title,
            "self_description_snippet": evidence,
            "source_arm": cand["source_arm"],
            "sec_cik": cand.get("cik"),
            "sec_filing_url": cand.get("filing_url"),
            "web_domains": cand.get("web_domains", []),
            "web_evidence": cand.get("web_evidence", []),
        })
    time.sleep(0.5)  # polite pacing

with OUT.open("w", encoding="utf-8") as f:
    for v in verified:
        f.write(json.dumps(v, ensure_ascii=False) + "\n")

print(f"\n[ok] {len(verified)} firms VERIFIED via their own website -> {OUT}")
print(f"[verified firms]")
for v in verified:
    print(f"  ✅ {v['firm_name']:<45}  {urlparse(v['official_url']).netloc}")