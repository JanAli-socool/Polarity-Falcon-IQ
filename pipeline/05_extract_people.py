# pipeline/05_extract_people.py  (v2 — DOM-structure aware)
# Uses heading tags + adjacent paragraph as the name/title anchor.
# Falls back to card-block scan only when no headings found.

import json, re, time, pathlib
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

IN  = pathlib.Path("data/raw/firms_curated.jsonl")   # ← now reads curated list
OUT = pathlib.Path("data/raw/people_raw.jsonl")

HEADERS = {"User-Agent": "Mozilla/5.0 (research; contact@example.com)"}

TEAM_PATH_HINTS = [
    "team","our-team","people","our-people","leadership","about",
    "about-us","who-we-are","professionals","staff","principals","meet",
]

TITLE_KEYWORDS = [
    "president","director","officer","partner","principal","founder",
    "manager","advisor","adviser","associate","analyst","chief",
    "head","managing","executive","chairman","ceo","cfo","cio","coo",
    "controller","accountant","counsel","secretary","treasurer","vp",
    "vice president","portfolio","investment","wealth","trust",
    "tax","operations","client","planning","compliance","strategist",
]

EMAIL_RE    = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
LINKEDIN_RE = re.compile(r"https?://[a-z]{2,3}\.linkedin\.com/in/[A-Za-z0-9\-_%]+/?")

# STRICT name pattern: 2–4 tokens, each Capitalized proper-noun,
# optional middle initial. No digits, no lowercase-only tokens.
NAME_RE = re.compile(
    r"^([A-Z][a-z'’\-]{1,20}"                     # First
    r"(?:\s+[A-Z]\.?)?"                           # optional middle initial
    r"(?:\s+[A-Z][a-z'’\-]{1,20}){1,2})"          # Last (and optional 2nd last)
    r"(?:[,\s]|$)"
)

# All-caps name variant (some sites use ALL CAPS in headings)
NAME_RE_CAPS = re.compile(
    r"^([A-Z]{2,20}(?:\s+[A-Z]{2,20}){1,3})(?:[,\s]|$)"
)

STOP_NAME_TOKENS = {
    "family","office","offices","capital","partners","group","wealth",
    "team","meet","our","the","who","what","how","home","about",
    "read","more","bio","learn","contact","join","careers","invest",
    "chief","officer","president","director","partner","principal",
    "founder","manager","advisor","adviser","associate","analyst",
    "managing","chairman","executive","tax","investment","operations",
    "portfolio","strategist","compliance","planning","completed",
    "united","registered","chartered","alternative","attractive",
    "opportunistic","approach","meet","let","ready","download",
}

def fetch(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=12, allow_redirects=True)
        if r.status_code == 200 and "text/html" in r.headers.get("Content-Type",""):
            return r.text
    except Exception:
        return None
    return None

def find_team_page(base_url: str, home_html: str) -> str | None:
    soup = BeautifulSoup(home_html, "html.parser")
    cands = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ").strip().lower()
        low = href.lower()
        score = 0
        for h in TEAM_PATH_HINTS:
            if h in low: score += 2
            if h in text: score += 1
        if score > 0:
            full = urljoin(base_url, href)
            if urlparse(full).netloc == urlparse(base_url).netloc:
                cands.append((score, full))
    if not cands: return None
    cands.sort(reverse=True)
    return cands[0][1]

def clean_str(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def is_person_name(s: str) -> str | None:
    """Return the cleaned name if s looks like a person's name, else None."""
    s = clean_str(s).rstrip(",.;:")
    if not s or len(s) < 5 or len(s) > 45:
        return None

    # Try mixed-case first, then ALL CAPS
    for pattern in (NAME_RE, NAME_RE_CAPS):
        m = pattern.match(s)
        if not m: continue
        name = m.group(1).strip()
        tokens = name.split()
        if len(tokens) < 2: continue
        # Reject if any token is a stop-word (case-insensitive)
        if any(t.lower() in STOP_NAME_TOKENS for t in tokens):
            continue
        # Reject if it's ALL uppercase and > 3 tokens (probably a heading like
        # "COMPLETED INVESTMENTS OVERVIEW"). 2-token ALL CAPS is fine.
        if name.isupper() and len(tokens) > 3:
            continue
        # Normalize ALL CAPS to Title Case for readability
        if name.isupper():
            name = " ".join(t.capitalize() for t in tokens)
        return name
    return None

def looks_like_title(s: str) -> bool:
    if not s: return False
    low = s.lower()
    return any(kw in low for kw in TITLE_KEYWORDS)

def extract_people_dom(html: str, source_url: str) -> list[dict]:
    """
    Primary strategy: heading tag (h1-h5) contains the name; the immediately
    following sibling(s) contain the title. Works for the vast majority of
    modern firm team pages.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script","style","nav","footer","header","form"]):
        tag.decompose()

    found = []
    seen = set()

    for h in soup.find_all(["h1","h2","h3","h4","h5"]):
        heading_text = clean_str(h.get_text(" "))
        name = is_person_name(heading_text)
        if not name: continue
        if name.lower() in seen: continue

        # Look at up to 3 following siblings for a title
        title = ""
        node = h
        for _ in range(4):
            node = node.find_next_sibling()
            if node is None: break
            t = clean_str(node.get_text(" "))
            if not t: continue
            # cap length; take first sentence-ish chunk
            t_short = re.split(r"[\.\|•\n]", t, maxsplit=1)[0].strip(" ,;:-–—")
            if looks_like_title(t_short) and len(t_short) < 140:
                title = t_short
                break

        # If sibling scan fails, try parent's text after the heading
        if not title:
            parent = h.parent
            if parent:
                ptxt = clean_str(parent.get_text(" "))
                after = ptxt[ptxt.find(heading_text) + len(heading_text):][:200]
                for chunk in re.split(r"[\.\|•\n]", after):
                    chunk = chunk.strip(" ,;:-–—")
                    if looks_like_title(chunk) and 3 < len(chunk) < 140:
                        title = chunk; break

        # Look for email + linkedin inside the parent block
                # Look for email + linkedin in a WIDER region: parent block + up to
        # 4 following siblings of the heading (firm sites often put contact
        # info in a paragraph a few nodes down from the name heading).
        search_nodes = []
        if h.parent:
            search_nodes.append(h.parent)
        sib = h
        for _ in range(4):
            sib = sib.find_next_sibling()
            if sib is None: break
            search_nodes.append(sib)
        # Also include the grandparent — many card layouts wrap name+details
        # in a shared parent that's 2 levels up
        if h.parent and h.parent.parent:
            search_nodes.append(h.parent.parent)

        combined_text = " ".join(n.get_text(" ") for n in search_nodes)
        email_m = EMAIL_RE.search(combined_text)

        li_url = ""
        for n in search_nodes:
            for a in n.find_all("a", href=True):
                m = LINKEDIN_RE.search(a["href"])
                if m: li_url = m.group(0); break
            if li_url: break
        # Also check anchor tags with mailto: for emails we missed
        if not email_m:
            for n in search_nodes:
                for a in n.find_all("a", href=True):
                    if a["href"].lower().startswith("mailto:"):
                        candidate = a["href"][7:].split("?")[0].strip()
                        if EMAIL_RE.match(candidate):
                            email_m = EMAIL_RE.match(candidate)
                            break
                if email_m: break

        seen.add(name.lower())
        found.append({
            "name": name,
            "title": title,
            "email_on_page": email_m.group(0) if email_m else "",
            "linkedin_on_page": li_url,
            "source_url": source_url,
            "extraction_strategy": "heading_tag_dom",
        })

    return found

def extract_people_fallback(html: str, source_url: str) -> list[dict]:
    """
    Fallback only if DOM heading strategy finds < 2 people.
    Scans compact card-like text blocks and requires strict name pattern.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script","style","nav","footer","header","form"]):
        tag.decompose()

    found = []
    seen = set()

    for block in soup.find_all(["div","li","article","section"]):
        text = clean_str(block.get_text(" "))
        if not text or len(text) > 400: continue
        low = text.lower()
        if not any(kw in low for kw in TITLE_KEYWORDS): continue

        # Try to find a person name at the start of the block
        name = is_person_name(text[:80])
        if not name: continue
        if name.lower() in seen: continue
        seen.add(name.lower())

        # Title = text after the name
        idx = text.find(name)
        after = text[idx + len(name):][:160]
        title = re.split(r"[\.\|•\n]", after, maxsplit=1)[0].strip(" ,;:-–—")
        if not looks_like_title(title):
            for kw in TITLE_KEYWORDS:
                m = re.search(rf"([A-Z][^.\n]{{0,60}}{kw}[^.\n]{{0,40}})", text, re.I)
                if m: title = m.group(1).strip(); break

        email_m = EMAIL_RE.search(text)
        li_url = ""
        for a in block.find_all("a", href=True):
            m = LINKEDIN_RE.search(a["href"])
            if m: li_url = m.group(0); break

        found.append({
            "name": name,
            "title": title[:140],
            "email_on_page": email_m.group(0) if email_m else "",
            "linkedin_on_page": li_url,
            "source_url": source_url,
            "extraction_strategy": "card_block_fallback",
        })
    return found

# ────────────────────────────────────────────────────────────────────
firms = [json.loads(l) for l in IN.open(encoding="utf-8")]
print(f"[info] processing {len(firms)} curated firms\n")

all_people = []

for i, firm in enumerate(firms, 1):
    name = firm["firm_name"]
    home = firm["official_url"]
    print(f"[{i:>2}/{len(firms)}] {name[:45]:<45}", flush=True)

    home_html = fetch(home)
    if not home_html:
        print("           ❌ home fetch failed"); time.sleep(1); continue

    team_url = find_team_page(home, home_html) or home
    team_html = home_html if team_url == home else fetch(team_url)
    if not team_html:
        print(f"           ❌ team page fetch failed ({team_url})"); time.sleep(1); continue

    print(f"           → team page: {team_url}")
    people = extract_people_dom(team_html, team_url)
    strategy = "DOM"
    if len(people) < 2:
        fb = extract_people_fallback(team_html, team_url)
        if len(fb) > len(people):
            people = fb; strategy = "fallback"
    print(f"           → {strategy}: {len(people)} people")

    for p in people:
        p["firm_name"] = name
        p["firm_official_url"] = home
        all_people.append(p)
    time.sleep(1.5)

with OUT.open("w", encoding="utf-8") as f:
    for p in all_people:
        f.write(json.dumps(p, ensure_ascii=False) + "\n")

from collections import defaultdict
by_firm = defaultdict(int)
for p in all_people: by_firm[p["firm_name"]] += 1

print(f"\n[ok] {len(all_people)} people across {len(by_firm)} firms -> {OUT}\n")
print(f"{'ppl':>4}  firm")
print("-" * 55)
for firm, count in sorted(by_firm.items(), key=lambda x: -x[1]):
    print(f"{count:>4}  {firm}")

emails = sum(1 for p in all_people if p["email_on_page"])
li     = sum(1 for p in all_people if p["linkedin_on_page"])
print(f"\n[stats] {emails} with published email, {li} with LinkedIn")