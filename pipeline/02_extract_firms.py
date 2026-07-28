# pipeline/02_extract_firms.py  (v3 — merges near-duplicates)
import json, re, pathlib
from collections import defaultdict

IN  = pathlib.Path("data/raw/discovery_probe.jsonl")
OUT = pathlib.Path("data/raw/firm_candidates.jsonl")

FIRM_PATTERNS = [
    re.compile(r"(?:^|(?<=[\s\-–—:\|]))([A-Z][A-Za-z0-9&'\.\-]+(?:\s+[A-Z][A-Za-z0-9&'\.\-]+){0,3})\s+Family\s+Office(?:s)?\b"),
    re.compile(r"(?:^|(?<=[\s\-–—:\|]))([A-Z][A-Za-z0-9&'\.\-]+(?:\s+[A-Z][A-Za-z0-9&'\.\-]+){0,2})\s+(?:Capital|Partners|Holdings|Ventures|Wealth|Group|Advisors)\b"),
]

BAD_FIRST_TOKENS = {
    "linkedin","facebook","twitter","x","instagram","as","is","and","or","but",
    "the","a","an","our","your","this","that","these","those","its",
    "single","multi","private","best","top","leading","new","most","accurate",
    "comprehensive","structuring","defining","forcing","understanding","building",
    "chief","managing","president","director","founder","co-founder","partner",
    "what","how","why","when","where","who","are","was","were","future",
    "family","office","offices","global","us","u.s.","canadian","singapore","emirates",
}

BAD_SUBSTRINGS = [
    "chief investment","chief financial","chief executive",
    "managing director","vice president","head of",
    "most accurate","financial services","forcing family","defining moments",
]

# Words to strip from the START of a captured name
LEADING_STRIP = re.compile(r"^(As|Is|And|Or|But|The|A|An|Our|Your|LinkedIn\.?|Facebook\.?)\s+", re.I)

def clean(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip().rstrip(".,;:")
    # strip stray leading noise words
    prev = None
    while prev != name:
        prev = name
        name = LEADING_STRIP.sub("", name).strip()
    # strip trailing platform names
    name = re.sub(r"\s+(LinkedIn|Facebook|Twitter)$", "", name, flags=re.I)
    return name

def is_valid_firm(name: str) -> bool:
    if not name or len(name) < 4 or len(name) > 55: return False
    lower = name.lower()
    if any(bad in lower for bad in BAD_SUBSTRINGS): return False
    first = name.split()[0].lower()
    if first in BAD_FIRST_TOKENS: return False
    if len(name.split()) < 2: return False
    return True

def extract_firms(text: str) -> set[str]:
    found = set()
    if "family office" not in text.lower(): return found
    for pat in FIRM_PATTERNS:
        for m in pat.finditer(text):
            name = clean(m.group(0))
            if is_valid_firm(name):
                found.add(name)
    return found

def norm_key(name: str) -> str:
    # merge key: lowercase, no punctuation, collapse "Offices"→"Office"
    k = re.sub(r"[^\w\s]", "", name.lower())
    k = re.sub(r"\s+", " ", k).strip()
    k = k.replace(" offices", " office")
    return k

firms = defaultdict(lambda: {"display_name": "", "domains": set(), "evidence": []})

with IN.open(encoding="utf-8") as f:
    for line in f:
        rec = json.loads(line)
        blob = f"{rec.get('title','')} . {rec.get('snippet','')}"
        for firm in extract_firms(blob):
            key = norm_key(firm)
            slot = firms[key]
            # keep the longest display name we've seen (usually most complete)
            if len(firm) > len(slot["display_name"]):
                slot["display_name"] = firm
            slot["domains"].add(rec["domain"])
            slot["evidence"].append({
                "url": rec["url"], "title": rec["title"],
                "snippet": rec["snippet"], "query": rec["query"],
                "domain": rec["domain"],
            })

ranked = sorted(firms.values(),
                key=lambda d: (len(d["domains"]), len(d["evidence"])),
                reverse=True)

with OUT.open("w", encoding="utf-8") as f:
    for data in ranked:
        f.write(json.dumps({
            "firm_name": data["display_name"],
            "distinct_domain_count": len(data["domains"]),
            "domains": sorted(data["domains"]),
            "evidence_count": len(data["evidence"]),
            "evidence": data["evidence"],
        }, ensure_ascii=False) + "\n")

print(f"[ok] extracted {len(ranked)} unique firms (after merge) -> {OUT}\n")
print(f"{'dom':>3}  {'ev':>3}  firm")
print("-" * 70)
for d in ranked[:25]:
    print(f"{len(d['domains']):>3}  {len(d['evidence']):>3}  {d['display_name']}")
multi = [d for d in ranked if len(d['domains']) >= 2]
print(f"\n[stats] {len(multi)} firms with ≥2 distinct domains (verified pool)")