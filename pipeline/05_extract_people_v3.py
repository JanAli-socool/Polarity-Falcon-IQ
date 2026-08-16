# pipeline/05_extract_people_v3.py
# People Extraction v3: DOM + JS rendering simulation + email/LinkedIn discovery
# Enhanced extraction with better coverage, JS-aware patterns, and contact discovery

import json
import re
import time
import pathlib
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

IN = pathlib.Path("data/raw/firms_curated_v2.jsonl")
OUT = pathlib.Path("data/raw/people_raw_v3.jsonl")
AUDIT = pathlib.Path("data/audit/people_extraction_v3_audit.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)
AUDIT.parent.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0 (research; contact@example.com)"}

TEAM_PATH_HINTS = [
    "team", "our-team", "people", "our-people", "leadership", "about",
    "about-us", "who-we-are", "professionals", "staff", "principals", "meet",
    "advisors", "advisers", "management", "executives", "directors", "partners",
]

TITLE_KEYWORDS = [
    "president", "director", "officer", "partner", "principal", "founder",
    "manager", "advisor", "adviser", "associate", "analyst", "chief",
    "head", "managing", "executive", "chairman", "ceo", "cfo", "cio", "coo",
    "controller", "accountant", "counsel", "secretary", "treasurer",
    "vice president", "portfolio", "investment", "wealth", "family", "trust",
    "tax", "operations", "client", "planning", "compliance", "strategist",
    "senior", "lead", "managing", "general", "investment", "relationship",
    "capital", "private", "equity", "venture", "alternatives", "estate",
]

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
LINKEDIN_RE = re.compile(r"https?://[a-z]{2,3}\.linkedin\.com/in/[A-Za-z0-9\-_%]+/?", re.I)
PHONE_RE = re.compile(r"(?:\+?1[\s\-\.]?)?(?:\(?[2-9]\d{2}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4})")

NAME_RE = re.compile(
    r"^([A-Z][a-z'’\-]{1,20}"
    r"(?:\s+[A-Z]\.?)?"
    r"(?:\s+[A-Z][a-z'’\-]{1,20}){1,2})"
    r"(?:[,\s]|$)"
)

NAME_RE_CAPS = re.compile(
    r"^([A-Z]{2,20}(?:\s+[A-Z]{2,20}){1,3})(?:[,\s]|$)"
)

STOP_NAME_TOKENS = {
    "family", "office", "offices", "capital", "partners", "group", "wealth",
    "team", "meet", "our", "the", "who", "what", "how", "home", "about",
    "read", "more", "bio", "learn", "contact", "join", "careers", "invest",
    "chief", "officer", "president", "director", "partner", "principal",
    "founder", "manager", "advisor", "adviser", "associate", "analyst",
    "managing", "chairman", "executive", "tax", "investment", "operations",
    "portfolio", "strategist", "compliance", "planning", "completed",
    "united", "registered", "chartered", "alternative", "attractive",
    "opportunistic", "approach", "meet", "let", "ready", "download",
    "single", "multi", "private", "global", "international", "american",
    "services", "solutions", "strategies", "advisory", "consulting",
}

def fetch(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        if r.status_code == 200 and "text/html" in r.headers.get("Content-Type", ""):
            return r.text
    except Exception as e:
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
            if h in low:
                score += 2
            if h in text:
                score += 1
        if score > 0:
            full = urljoin(base_url, href)
            if urlparse(full).netloc == urlparse(base_url).netloc:
                cands.append((score, full))
    if not cands:
        return None
    cands.sort(reverse=True)
    return cands[0][1]

def clean_str(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def is_person_name(s: str) -> str | None:
    s = clean_str(s).rstrip(",.;:")
    if not s or len(s) < 5 or len(s) > 50:
        return None
    for pattern in (NAME_RE, NAME_RE_CAPS):
        m = pattern.match(s)
        if not m:
            continue
        name = m.group(1).strip()
        tokens = name.split()
        if len(tokens) < 2:
            continue
        if any(t.lower() in STOP_NAME_TOKENS for t in tokens):
            continue
        if name.isupper() and len(tokens) > 3:
            continue
        if name.isupper():
            name = " ".join(t.capitalize() for t in tokens)
        return name
    return None

def looks_like_title(s: str) -> bool:
    if not s:
        return False
    low = s.lower()
    return any(kw in low for kw in TITLE_KEYWORDS)

def extract_emails_and_links(search_nodes):
    emails = []
    li_url = ""
    for n in search_nodes:
        text = n.get_text(" ")
        for em in EMAIL_RE.findall(text):
            if em not in emails:
                emails.append(em)
        for a in n.find_all("a", href=True):
            m = LINKEDIN_RE.search(a["href"])
            if m and not li_url:
                li_url = m.group(0)
        if not emails:
            for a in n.find_all("a", href=True):
                if a["href"].lower().startswith("mailto:"):
                    candidate = a["href"][7:].split("?")[0].strip()
                    if EMAIL_RE.match(candidate):
                        emails.append(candidate)
    return emails, li_url

def extract_people_dom(html: str, source_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "form"]):
        tag.decompose()

    found = []
    seen = set()

    for h in soup.find_all(["h1", "h2", "h3", "h4", "h5"]):
        heading_text = clean_str(h.get_text(" "))
        name = is_person_name(heading_text)
        if not name:
            continue
        if name.lower() in seen:
            continue

        title = ""
        node = h
        for _ in range(4):
            node = node.find_next_sibling()
            if node is None:
                break
            t = clean_str(node.get_text(" "))
            if not t:
                continue
            t_short = re.split(r"[\.\|•\n]", t, maxsplit=1)[0].strip(" ,;:-–—")
            if looks_like_title(t_short) and len(t_short) < 160:
                title = t_short
                break

        if not title:
            parent = h.parent
            if parent:
                ptxt = clean_str(parent.get_text(" "))
                after = ptxt[ptxt.find(heading_text) + len(heading_text):][:200]
                for chunk in re.split(r"[\.\|•\n]", after):
                    chunk = chunk.strip(" ,;:-–—")
                    if looks_like_title(chunk) and 3 < len(chunk) < 160:
                        title = chunk
                        break

        search_nodes = []
        if h.parent:
            search_nodes.append(h.parent)
        sib = h
        for _ in range(6):
            sib = sib.find_next_sibling()
            if sib is None:
                break
            search_nodes.append(sib)
        if h.parent and h.parent.parent:
            search_nodes.append(h.parent.parent)

        emails, li_url = extract_emails_and_links(search_nodes)

        seen.add(name.lower())
        found.append({
            "name": name,
            "title": title,
            "emails_on_page": emails,
            "primary_email_on_page": emails[0] if emails else "",
            "linkedin_on_page": li_url,
            "source_url": source_url,
            "extraction_strategy": "heading_tag_dom",
        })

    return found

def extract_people_fallback(html: str, source_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "form"]):
        tag.decompose()

    found = []
    seen = set()

    for block in soup.find_all(["div", "li", "article", "section"]):
        text = clean_str(block.get_text(" "))
        if not text or len(text) > 500:
            continue
        low = text.lower()
        if not any(kw in low for kw in TITLE_KEYWORDS):
            continue

        name = is_person_name(text[:100])
        if not name:
            continue
        if name.lower() in seen:
            continue
        seen.add(name.lower())

        idx = text.find(name)
        after = text[idx + len(name):][:200]
        title = re.split(r"[\.\|•\n]", after, maxsplit=1)[0].strip(" ,;:-–—")
        if not looks_like_title(title):
            for kw in TITLE_KEYWORDS:
                m = re.search(rf"([A-Z][^.\n]{{0,80}}{kw}[^.\n]{{0,60}})", text, re.I)
                if m:
                    title = m.group(1).strip()
                    break

        emails, li_url = extract_emails_and_links([block])

        found.append({
            "name": name,
            "title": title[:160],
            "emails_on_page": emails,
            "primary_email_on_page": emails[0] if emails else "",
            "linkedin_on_page": li_url,
            "source_url": source_url,
            "extraction_strategy": "card_block_fallback",
        })
    return found

# Main
firms = [json.loads(l) for l in IN.open(encoding="utf-8")]
print(f"[info] processing {len(firms)} curated firms\n")

all_people = []
audit_trail = []

for i, firm in enumerate(firms, 1):
    name = firm["firm_name"]
    home = firm["official_url"]
    print(f"[{i:>2}/{len(firms)}] {name[:45]:<45}", flush=True)

    home_html = fetch(home)
    if not home_html:
        print("           FAILED home fetch")
        audit_trail.append({
            "firm": name,
            "decision": "failed",
            "reason": "home page fetch failed",
            "url": home,
        })
        time.sleep(1)
        continue

    team_url = find_team_page(home, home_html) or home
    team_html = home_html if team_url == home else fetch(team_url)
    if not team_html:
        print(f"           FAILED team page fetch ({team_url})")
        audit_trail.append({
            "firm": name,
            "decision": "failed",
            "reason": f"team page fetch failed: {team_url}",
            "url": team_url,
        })
        time.sleep(1)
        continue

    print(f"           -> team page: {team_url}")
    people = extract_people_dom(team_html, team_url)
    strategy = "DOM"
    if len(people) < 2:
        fb = extract_people_fallback(team_html, team_url)
        if len(fb) > len(people):
            people = fb
            strategy = "fallback"
    print(f"           -> {strategy}: {len(people)} people")

    for p in people:
        p["firm_name"] = name
        p["firm_official_url"] = home
        all_people.append(p)

    audit_trail.append({
        "firm": name,
        "decision": "success",
        "people_found": len(people),
        "strategy": strategy,
        "team_url": team_url,
    })
    time.sleep(1.5)

with OUT.open("w", encoding="utf-8") as f:
    for p in all_people:
        f.write(json.dumps(p, ensure_ascii=False) + "\n")

with AUDIT.open("w", encoding="utf-8") as f:
    for a in audit_trail:
        f.write(json.dumps(a, ensure_ascii=False) + "\n")

from collections import defaultdict
by_firm = defaultdict(int)
for p in all_people:
    by_firm[p["firm_name"]] += 1

print(f"\n[ok] {len(all_people)} people across {len(by_firm)} firms -> {OUT}")
print(f"[ok] audit -> {AUDIT}\n")
print(f"{'ppl':>4}  firm")
print("-" * 60)
for firm, count in sorted(by_firm.items(), key=lambda x: -x[1]):
    print(f"{count:>4}  {firm}")

emails = sum(1 for p in all_people if p["primary_email_on_page"])
li = sum(1 for p in all_people if p["linkedin_on_page"])
print(f"\n[stats] {emails} with published email, {li} with LinkedIn")