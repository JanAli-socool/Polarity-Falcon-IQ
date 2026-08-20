"""Evidence-bound enrichment of candidates into policy-evaluated records."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any
from urllib.parse import urljoin, urlparse

import dns.resolver
from bs4 import BeautifulSoup, Tag
from ddgs import DDGS

from stage2.http import ObservableHttpClient, Observation
from stage2.operating import OperatingLog, now_utc
from stage2.policy import (
    build_evidence,
    build_record,
    evaluate_record,
    is_http_url,
    is_person_name,
    normalize_space,
)

ROLE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:chief investment officer|co-chief investment officer|cio)\b", re.I), "investment_decision_maker"),
    (re.compile(r"\b(?:head|director|managing director|vice president|vp) of (?:private )?investments?\b", re.I), "investment_decision_maker"),
    (re.compile(r"\b(?:investment director|portfolio manager|investment manager)\b", re.I), "investment_decision_maker"),
    (re.compile(r"\b(?:founder|co-founder|chief executive officer|ceo|president|chair(?:man|woman|person)?)\b", re.I), "executive_decision_maker"),
    (re.compile(r"\b(?:managing partner|general partner|senior partner|partner|principal)\b", re.I), "partner_or_principal"),
    (re.compile(r"\b(?:head|director|managing director|partner) of (?:capital|relationships?|investor relations)\b", re.I), "capital_or_relationship_lead"),
)
NAME_RE = re.compile(
    r"\b([A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+(?:\s+[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+){1,3})\b"
)
TEAM_LINK_WORDS = ("team", "people", "leadership", "professionals", "who-we-are", "about-us", "our-firm", "our-people", "meet-the-team", "management", "partners", "principals", "investment-team", "investment-professionals", "advisors", "advisers", "executives", "senior-team", "management-team")
SOCIAL_HOSTS = {"linkedin.com", "facebook.com", "instagram.com", "x.com", "twitter.com", "youtube.com"}
CONTACT_PAGE_WORDS = ("contact", "contact-us", "get-in-touch", "reach-us", "email-us", "mail-us")
EMAIL_SEARCH_QUERIES = (
    '"{firm}" email "@" "@"',
    '"{firm}" "email" "@" "com"',
    '"{firm}" "mailto:"',
    '"{firm}" "chief investment officer" email',
    '"{firm}" "managing partner" email',
    '"{firm}" "managing director" email',
    '"{firm}" partner email',
    '"{firm}" principal email',
    '"{firm}" "chief investment officer" "@"',
    '"{firm}" "managing partner" "@"',
)
ASSET_TERMS = {
    "Private equity": ("private equity", "buyout"),
    "Venture capital": ("venture capital", "venture investments", "startups"),
    "Private credit": ("private credit", "direct lending"),
    "Real estate": ("real estate", "property investments"),
    "Public markets": ("public equities", "public markets", "listed equities"),
    "Direct investments": ("direct investments", "direct investing"),
}
SECTOR_TERMS = {
    "Healthcare": ("healthcare", "health care", "life sciences"),
    "Technology": ("technology", "software", "digital"),
    "Consumer": ("consumer",),
    "Financial services": ("financial services", "fintech"),
    "Industrials": ("industrials", "manufacturing"),
    "Energy": ("energy",),
}


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").casefold().removeprefix("www.")


def _same_site(left: str, right: str) -> bool:
    a, b = _host(left), _host(right)
    return bool(a and b and (a == b or a.endswith(f".{b}") or b.endswith(f".{a}")))


def _excerpt(text: str, term: str, radius: int = 280) -> str:
    compact = normalize_space(text)
    index = compact.casefold().find(term.casefold())
    if index < 0:
        return compact[: radius * 2]
    start = max(0, index - radius)
    end = min(len(compact), index + len(term) + radius)
    return compact[start:end].strip()


def _title_and_role(text: str) -> tuple[str, str]:
    for pattern, role_class in ROLE_PATTERNS:
        match = pattern.search(text)
        if match:
            return normalize_space(match.group(0)), role_class
    return "", ""


def _name_from_card(card: Tag, text: str) -> str:
    for tag in card.find_all(["h1", "h2", "h3", "h4", "h5", "strong", "b"], limit=8):
        candidate = normalize_space(tag.get_text(" ", strip=True))
        if is_person_name(candidate):
            return candidate
    for match in NAME_RE.finditer(text):
        candidate = normalize_space(match.group(1))
        if is_person_name(candidate):
            return candidate
    return ""


def _route_card(anchor: Tag) -> tuple[Tag, str]:
    selected = anchor
    selected_text = normalize_space(anchor.get_text(" ", strip=True))
    for parent in anchor.parents:
        if not isinstance(parent, Tag) or parent.name in {"body", "html"}:
            break
        text = normalize_space(parent.get_text(" ", strip=True))
        if 8 <= len(text) <= 900:
            selected, selected_text = parent, text
            if _title_and_role(text)[0] and any(is_person_name(normalize_space(t.get_text(" ", strip=True))) for t in parent.find_all(["h1", "h2", "h3", "h4", "h5", "strong"], limit=8)):
                break
    return selected, selected_text


def _mx_present(domain: str, log: OperatingLog) -> bool:
    log.emit("dns.mx.started", domain=domain)
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=8)
        present = bool(list(answers))
        log.emit("dns.mx.completed", domain=domain, mx_present=present)
        return present
    except Exception as exc:
        log.emit("dns.mx.failed", domain=domain, error_type=type(exc).__name__, error=str(exc)[:300])
        return False


def _classification_evidence(candidate: dict[str, Any]) -> dict[str, Any]:
    discovery = candidate["discovery"]
    return build_evidence(
        url=discovery["url"],
        observed_at=discovery["observed_at"],
        quote=discovery["quote"],
        source_class=discovery["source_class"],
        extraction_method=discovery["extraction_method"],
        supports=["firm.name", "firm.type"],
    )


def extract_enrichments(candidate: dict[str, Any], observation: Observation) -> list[dict[str, Any]]:
    text = BeautifulSoup(observation.text, "lxml").get_text(" ", strip=True)
    lowered = text.casefold()
    output: list[dict[str, Any]] = []
    if "family office" in lowered or "family-office" in lowered:
        term = "family office" if "family office" in lowered else "family-office"
        quote = _excerpt(text, term)
        output.append({
            "kind": "family_office_classification",
            "value": candidate["firm_type"],
            "evidence": build_evidence(
                url=observation.final_url,
                observed_at=observation.observed_at,
                quote=quote,
                source_class="official_firm_site",
                extraction_method="official_page_text_phrase",
                supports=["enrichment.kind", "enrichment.value"],
            ),
        })
    for value, terms in ASSET_TERMS.items():
        term = next((term for term in terms if term in lowered), "")
        if term:
            output.append({
                "kind": "asset_class",
                "value": value,
                "evidence": build_evidence(
                    url=observation.final_url, observed_at=observation.observed_at,
                    quote=_excerpt(text, term), source_class="official_firm_site",
                    extraction_method="official_page_controlled_vocabulary_match",
                    supports=["enrichment.kind", "enrichment.value"],
                ),
            })
    for value, terms in SECTOR_TERMS.items():
        term = next((term for term in terms if term in lowered), "")
        if term:
            output.append({
                "kind": "sector",
                "value": value,
                "evidence": build_evidence(
                    url=observation.final_url, observed_at=observation.observed_at,
                    quote=_excerpt(text, term), source_class="official_firm_site",
                    extraction_method="official_page_controlled_vocabulary_match",
                    supports=["enrichment.kind", "enrichment.value"],
                ),
            })
    return output


def extract_official_people(
    *,
    candidate: dict[str, Any],
    observation: Observation,
    classification_evidence: dict[str, Any],
    enrichments: list[dict[str, Any]],
    log: OperatingLog,
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(observation.text, "lxml")
    people: dict[str, dict[str, Any]] = defaultdict(lambda: {"routes": []})
    for anchor in soup.find_all("a", href=True):
        href = normalize_space(anchor.get("href"))
        absolute = urljoin(observation.final_url, href)
        route_type = ""
        route_value = ""
        if href.casefold().startswith("mailto:"):
            route_type = "email"
            route_value = href[7:].split("?", 1)[0].strip().lower()
        elif is_http_url(absolute) and _host(absolute) == "linkedin.com" and urlparse(absolute).path.casefold().startswith("/in/"):
            route_type = "linkedin"
            route_value = absolute.split("?", 1)[0]
        if not route_type:
            continue
        card, card_text = _route_card(anchor)
        title, role_class = _title_and_role(card_text)
        name = _name_from_card(card, card_text)
        if not name or not title:
            log.emit("extraction.route.rejected", url=observation.final_url, route_type=route_type, reason="explicit_name_or_decision_title_missing")
            continue
        evidence_quote = normalize_space(f"{card_text} {route_value}")[:1000]
        route_evidence = build_evidence(
            url=observation.final_url,
            observed_at=observation.observed_at,
            quote=evidence_quote,
            source_class="official_firm_site",
            extraction_method="official_dom_card_text_and_href",
            supports=["person.name", "route.value", "route.ownership"],
        )
        if route_type == "email":
            if "@" not in route_value or not _same_site(f"https://{route_value.rsplit('@', 1)[1]}", candidate["homepage"]):
                log.emit("extraction.route.rejected", url=observation.final_url, route_type=route_type, reason="email_domain_not_official_site")
                continue
            mx = _mx_present(route_value.rsplit("@", 1)[1], log)
            route = {
                "type": "email", "value": route_value,
                "ownership_status": "source_names_person", "ownership_method": "official_dom_card",
                "current_status": "published_on_current_official_source",
                "domain_mail_status": "mx_present" if mx else "not_confirmed",
                "shared": False, "inferred": False, "evidence": route_evidence,
            }
        else:
            route = {
                "type": "linkedin", "value": route_value,
                "ownership_status": "source_names_person", "ownership_method": "official_dom_card",
                "current_status": "profile_link_currently_published", "evidence": route_evidence,
            }
        key = name.casefold()
        people[key].update({"name": name, "title": title, "role_class": role_class, "card_text": card_text})
        if all(existing["value"] != route_value for existing in people[key]["routes"]):
            people[key]["routes"].append(route)

    records: list[dict[str, Any]] = []
    for details in people.values():
        role_evidence = build_evidence(
            url=observation.final_url,
            observed_at=observation.observed_at,
            quote=details["card_text"][:1000],
            source_class="official_firm_site",
            extraction_method="official_dom_card_text",
            supports=["firm.name", "person.firm_relationship", "person.name", "person.title"],
        )
        record = build_record(
            firm={
                "name": candidate["firm_name"], "type": candidate["firm_type"],
                "country": "", "classification_evidence": classification_evidence,
            },
            person={
                "name": details["name"], "title": details["title"],
                "role_class": details["role_class"], "role_evidence": role_evidence,
            },
            discovery={key: candidate["discovery"][key] for key in ("source_class", "url", "observed_at", "extraction_method")},
            enrichments=enrichments,
            contact_routes=details["routes"],
            freshness={
                "trust_state": "supported_current",
                "last_evidence_check_at": observation.observed_at,
                "basis_evidence_ids": [
                    classification_evidence["evidence_id"], role_evidence["evidence_id"],
                    *[item["evidence"]["evidence_id"] for item in enrichments],
                    *[route["evidence"]["evidence_id"] for route in details["routes"]],
                ],
                "reason": "Required evidence and a person-owned route were present on checked public sources.",
            },
            lifecycle_status="candidate",
        )
        records.append(record)
    return records


def _team_urls(home: Observation, limit: int = 15) -> list[str]:
    soup = BeautifulSoup(home.text, "lxml")
    urls: list[str] = [home.final_url]
    for anchor in soup.find_all("a", href=True):
        href = urljoin(home.final_url, anchor.get("href", "")).split("#", 1)[0]
        label = normalize_space(anchor.get_text(" ", strip=True)).casefold()
        target = href.casefold()
        if is_http_url(href) and _same_site(home.final_url, href) and any(word in f"{label} {target}" for word in TEAM_LINK_WORDS):
            if href not in urls:
                urls.append(href)
        if len(urls) >= limit:
            break
    return urls


def _linkedin_search_records(
    candidate: dict[str, Any],
    classification_evidence: dict[str, Any],
    enrichments: list[dict[str, Any]],
    log: OperatingLog,
    *,
    max_results: int = 15,
) -> list[dict[str, Any]]:
    if not enrichments:
        return []
    query = f'site:linkedin.com/in "{candidate["firm_name"]}" (partner OR principal OR founder OR "chief investment officer" OR "investment director")'
    log.emit("search.started", provider="duckduckgo", query=query, max_results=max_results, purpose="person_route")
    try:
        results = list(DDGS(timeout=20).text(query, max_results=max_results))
    except Exception as exc:
        log.emit("search.failed", provider="duckduckgo", query=query, error_type=type(exc).__name__, error=str(exc)[:500])
        return []
    records: list[dict[str, Any]] = []
    firm_tokens = [token.casefold() for token in re.findall(r"[A-Za-z0-9]+", candidate["firm_name"]) if len(token) > 3]
    for result in results:
        url = normalize_space(result.get("href")).split("?", 1)[0]
        if _host(url) != "linkedin.com" or not urlparse(url).path.casefold().startswith("/in/"):
            continue
        title_text = normalize_space(result.get("title"))
        body = normalize_space(result.get("body"))
        quote = normalize_space(f"{title_text}. {body}")[:1000]
        if firm_tokens and not any(token in quote.casefold() for token in firm_tokens):
            continue
        name_part = re.split(r"\s+[-|–—]\s+", title_text, maxsplit=1)[0]
        name = normalize_space(re.sub(r"\s+LinkedIn$", "", name_part, flags=re.I))
        title, role_class = _title_and_role(quote)
        if not is_person_name(name) or not title:
            continue
        observed = now_utc()
        role_evidence = build_evidence(
            url=url, observed_at=observed, quote=quote,
            source_class="professional_profile", extraction_method="duckduckgo_profile_result",
            supports=["firm.name", "person.firm_relationship", "person.name", "person.title"],
        )
        route_evidence = build_evidence(
            url=url, observed_at=observed, quote=quote,
            source_class="professional_profile", extraction_method="duckduckgo_profile_result",
            supports=["person.name", "route.value", "route.ownership"],
        )
        record = build_record(
            firm={
                "name": candidate["firm_name"], "type": candidate["firm_type"], "country": "",
                "classification_evidence": classification_evidence,
            },
            person={"name": name, "title": title, "role_class": role_class, "role_evidence": role_evidence},
            discovery={key: candidate["discovery"][key] for key in ("source_class", "url", "observed_at", "extraction_method")},
            enrichments=enrichments,
            contact_routes=[{
                "type": "linkedin", "value": url,
                "ownership_status": "source_names_person", "ownership_method": "current_professional_profile_result",
                "current_status": "profile_link_currently_published", "evidence": route_evidence,
            }],
            freshness={
                "trust_state": "supported_with_limitations",
                "last_evidence_check_at": observed,
                "basis_evidence_ids": [classification_evidence["evidence_id"], role_evidence["evidence_id"], route_evidence["evidence_id"], *[item["evidence"]["evidence_id"] for item in enrichments]],
                "reason": "Current profile publication and firm evidence were found; no direct outreach address was established.",
            },
            lifecycle_status="candidate",
        )
        records.append(record)
    log.emit("search.completed", provider="duckduckgo", query=query, returned=len(results), candidates=len(records), purpose="person_route")
    return records


def _extract_emails_from_page(
    observation: Observation,
    log: OperatingLog,
    candidate: dict[str, Any],
) -> list[dict[str, Any]]:
    """Extract email routes from a page observation."""
    routes = []
    soup = BeautifulSoup(observation.text, "lxml")
    
    # Find mailto: links
    for anchor in soup.find_all("a", href=True):
        href = normalize_space(anchor.get("href"))
        if not href.casefold().startswith("mailto:"):
            continue
        email = href[7:].split("?", 1)[0].strip().lower()
        if "@" not in email:
            continue
        domain = email.rsplit("@", 1)[1]
        if not _same_site(f"https://{domain}", candidate["homepage"]):
            log.emit("email.domain_not_official", email=email, candidate=candidate["candidate_id"])
            continue
        
        card, card_text = _route_card(anchor)
        title, role_class = _title_and_role(card_text)
        name = _name_from_card(card, card_text)
        if not name or not title:
            log.emit("email.no_name_title", email=email, url=observation.final_url)
            continue
        
        evidence_quote = normalize_space(f"{card_text} {email}")[:1000]
        route_evidence = build_evidence(
            url=observation.final_url,
            observed_at=observation.observed_at,
            quote=evidence_quote,
            source_class="official_firm_site",
            extraction_method="official_dom_card_text_and_href",
            supports=["person.name", "route.value", "route.ownership"],
        )
        
        mx = _mx_present(email.rsplit("@", 1)[1], log)
        route = {
            "type": "email", "value": email,
            "ownership_status": "source_names_person", "ownership_method": "official_dom_card",
            "current_status": "published_on_current_official_source",
            "domain_mail_status": "mx_present" if mx else "not_confirmed",
            "shared": False, "inferred": False, "evidence": route_evidence,
        }
        routes.append({"route": route, "name": name, "title": title, "role_class": role_class, "card_text": card_text, "evidence": route_evidence})
    
    return routes


def _discover_emails_from_search(
    candidate: dict[str, Any],
    log: OperatingLog,
    *,
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """Discover emails via targeted search queries."""
    routes = []
    if not candidate.get("homepage"):
        return routes
    
    firm_domain = urlparse(candidate["homepage"]).netloc.replace("www.", "")
    if not firm_domain:
        return routes
    
    engine = DDGS(timeout=20)
    for query_template in EMAIL_SEARCH_QUERIES:
        query = query_template.format(firm=candidate["firm_name"])
        log.emit("email_search.started", provider="duckduckgo", query=query, max_results=max_results)
        try:
            results = list(engine.text(query, max_results=max_results))
        except Exception as exc:
            log.emit("email_search.failed", provider="duckduckgo", query=query, error_type=type(exc).__name__, error=str(exc)[:500])
            continue
        
        for result in results:
            href = normalize_space(result.get("href", ""))
            title = normalize_space(result.get("title", ""))
            body = normalize_space(result.get("body", ""))
            text = normalize_space(f"{title}. {body}")
            
            # Extract emails from text
            email_matches = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
            for email in email_matches:
                email = email.lower().strip()
                domain = email.rsplit("@", 1)[1] if "@" in email else ""
                if not domain or not _same_site(f"https://{domain}", candidate["homepage"]):
                    continue
                
                # Check if email contains firm tokens
                firm_tokens = [t for t in re.findall(r"[A-Za-z0-9]+", candidate["firm_name"]) if len(t) > 3]
                if firm_tokens and not any(t in email.casefold() for t in firm_tokens):
                    continue
                
                # Find name in context
                name = ""
                for token in re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', text):
                    if is_person_name(token):
                        name = normalize_space(token)
                        break
                
                if not name:
                    continue
                
                # Extract title
                title, role_class = _title_and_role(text)
                if not title:
                    continue
                
                evidence_quote = normalize_space(text)[:1000]
                route_evidence = build_evidence(
                    url=href if href else candidate["homepage"],
                    observed_at=now_utc(),
                    quote=evidence_quote,
                    source_class="search_discovery",
                    extraction_method="search_result_email_extraction",
                    supports=["person.name", "route.value", "route.ownership"],
                )
                
                mx = _mx_present(email.rsplit("@", 1)[1], log)
                route = {
                    "type": "email", "value": email,
                    "ownership_status": "source_names_person", "ownership_method": "search_result_context",
                    "current_status": "found_in_search_context",
                    "domain_mail_status": "mx_present" if mx else "not_confirmed",
                    "shared": False, "inferred": False, "evidence": route_evidence,
                }
                routes.append({"route": route, "name": name, "title": title, "role_class": role_class, "card_text": text[:1000], "evidence": route_evidence})
        
        log.emit("email_search.completed", provider="duckduckgo", query=query, returned=len(results), emails_found=len(routes))
    
    return routes


def _discover_contact_page_emails(
    candidate: dict[str, Any],
    client: ObservableHttpClient,
    log: OperatingLog,
) -> list[dict[str, Any]]:
    """Crawl contact pages for emails."""
    routes = []
    if not candidate.get("homepage"):
        return routes
    
    try:
        home = client.get(candidate["homepage"], purpose=f"homepage:{candidate['candidate_id']}")
    except RuntimeError as exc:
        log.emit("homepage.fetch_failed", candidate_id=candidate["candidate_id"], error=str(exc)[:300])
        return routes
    
    soup = BeautifulSoup(home.text, "lxml")
    contact_urls = set()
    
    # Find contact page links
    for anchor in soup.find_all("a", href=True):
        href = normalize_space(anchor.get("href"))
        absolute = urljoin(home.final_url, href)
        label = normalize_space(anchor.get_text(" ", strip=True)).casefold()
        target = href.casefold()
        
        if not is_http_url(absolute) or not _same_site(home.final_url, absolute):
            continue
        if any(word in f"{label} {target}" for word in CONTACT_PAGE_WORDS):
            contact_urls.add(absolute)
    
    # Also check common contact page paths
    base_url = home.final_url.rstrip("/")
    common_paths = ["/contact", "/contact-us", "/get-in-touch", "/contact.html", "/contact.php", "/about/contact", "/team/contact"]
    for path in common_paths:
        contact_urls.add(base_url + path)
    
    for url in list(contact_urls)[:5]:  # Limit to 5 contact pages
        try:
            page = client.get(url, purpose=f"contact_page:{candidate['candidate_id']}")
        except RuntimeError:
            continue
        
        if page.final_url in contact_urls:
            contact_urls.remove(page.final_url)  # Avoid re-processing
        
        extracted = _extract_emails_from_page(page, log, candidate)
        routes.extend(extracted)
        log.emit("contact_page.emails_extracted", url=url, count=len(extracted))
    
    return routes


def enrich_candidate(
    candidate: dict[str, Any],
    client: ObservableHttpClient,
    log: OperatingLog,
    *,
    linkedin_fallback: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    classification = _classification_evidence(candidate)
    records: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    try:
        home = client.get(candidate["homepage"], purpose=f"candidate_home:{candidate['candidate_id']}")
    except RuntimeError as exc:
        log.emit("candidate.enrichment.failed", candidate_id=candidate["candidate_id"], reason="homepage_unavailable", error=str(exc)[:500])
        return [], [{"candidate_id": candidate["candidate_id"], "reasons": ["homepage_unavailable"]}]
    if not _same_site(candidate["homepage"], home.final_url):
        log.emit("candidate.enrichment.failed", candidate_id=candidate["candidate_id"], reason="cross_site_redirect")
        return [], [{"candidate_id": candidate["candidate_id"], "reasons": ["cross_site_redirect"]}]
    enrichments = extract_enrichments(candidate, home)
    seen_pages: set[str] = set()
    for url in _team_urls(home):
        try:
            page = home if url == home.final_url else client.get(url, purpose=f"candidate_people:{candidate['candidate_id']}")
        except RuntimeError as exc:
            log.emit("candidate.page.failed", candidate_id=candidate["candidate_id"], url=url, error=str(exc)[:500])
            continue
        if page.final_url in seen_pages or not _same_site(home.final_url, page.final_url):
            continue
        seen_pages.add(page.final_url)
        page_enrichments = enrichments or extract_enrichments(candidate, page)
        records.extend(extract_official_people(
            candidate=candidate, observation=page, classification_evidence=classification,
            enrichments=page_enrichments, log=log,
        ))
    if linkedin_fallback and len(records) < 5:
        records.extend(_linkedin_search_records(candidate, classification, enrichments, log, max_results=15))
    
    # Email-specific discovery (only if we still need more emails)
    email_routes_found = sum(1 for r in records for c in r.get("contact_routes", []) if c.get("type") == "email")
    if email_routes_found < 3:
        # Discover emails from search
        search_email_routes = _discover_emails_from_search(candidate, log, max_results=15)
        for er in search_email_routes:
            if not isinstance(er, dict) or "evidence" not in er or "route" not in er:
                log.emit("email.route_structure_invalid", candidate_id=candidate["candidate_id"], keys=list(er.keys()) if isinstance(er, dict) else "not_dict")
                continue
            evidence = er["evidence"]
            evidence_id = evidence.get("evidence_id") if isinstance(evidence, dict) else None
            if not evidence_id:
                log.emit("email.evidence_missing_id", candidate_id=candidate["candidate_id"])
                continue
            records.append(build_record(
                firm={
                    "name": candidate["firm_name"], "type": candidate["firm_type"], "country": "",
                    "classification_evidence": classification,
                },
                person={"name": er.get("name", ""), "title": er.get("title", ""), "role_class": er.get("role_class", ""), "role_evidence": er.get("evidence", {})},
                discovery={key: candidate["discovery"][key] for key in ("source_class", "url", "observed_at", "extraction_method")},
                enrichments=enrichments,
                contact_routes=[er["route"]],
                freshness={
                    "trust_state": "supported_with_limitations",
                    "last_evidence_check_at": now_utc(),
                    "basis_evidence_ids": [classification["evidence"]["evidence_id"], evidence_id],
                    "reason": "Email found in search context with supporting context.",
                },
                lifecycle_status="candidate",
            ))
        
        # Discover emails from contact pages
        contact_email_routes = _discover_contact_page_emails(candidate, client, log)
        for er in contact_email_routes:
            if not isinstance(er, dict) or "evidence" not in er or "route" not in er:
                log.emit("email.route_structure_invalid", candidate_id=candidate["candidate_id"], keys=list(er.keys()) if isinstance(er, dict) else "not_dict")
                continue
            evidence = er["evidence"]
            evidence_id = evidence.get("evidence_id") if isinstance(evidence, dict) else None
            if not evidence_id:
                log.emit("email.evidence_missing_id", candidate_id=candidate["candidate_id"])
                continue
            records.append(build_record(
                firm={
                    "name": candidate["firm_name"], "type": candidate["firm_type"], "country": "",
                    "classification_evidence": classification,
                },
                person={"name": er.get("name", ""), "title": er.get("title", ""), "role_class": er.get("role_class", ""), "role_evidence": er.get("evidence", {})},
                discovery={key: candidate["discovery"][key] for key in ("source_class", "url", "observed_at", "extraction_method")},
                enrichments=enrichments,
                contact_routes=[er["route"]],
                freshness={
                    "trust_state": "supported_current",
                    "last_evidence_check_at": now_utc(),
                    "basis_evidence_ids": [classification["evidence"]["evidence_id"], evidence_id],
                    "reason": "Email found on firm contact page with supporting context.",
                },
                lifecycle_status="candidate",
            ))

    deduped: dict[str, dict[str, Any]] = {}
    for record in records:
        existing = deduped.get(record["identity_key"])
        if existing:
            existing_values = {route["value"] for route in existing["contact_routes"]}
            existing["contact_routes"].extend(
                route for route in record["contact_routes"] if route["value"] not in existing_values
            )
            existing["freshness"]["basis_evidence_ids"] = sorted(set(
                existing["freshness"]["basis_evidence_ids"] + record["freshness"]["basis_evidence_ids"]
            ))
        else:
            deduped[record["identity_key"]] = record
    publishable: list[dict[str, Any]] = []
    for record in deduped.values():
        evaluation = evaluate_record(record)
        record["evaluation"] = evaluation
        if evaluation["qualifies"]:
            record["lifecycle_status"] = "publish"
            publishable.append(record)
        else:
            record["lifecycle_status"] = "quarantine"
            rejected.append({
                "candidate_id": candidate["candidate_id"], "record_id": record["record_id"],
                "reasons": evaluation["reasons"], "record": record,
            })
    log.emit(
        "candidate.enrichment.completed", candidate_id=candidate["candidate_id"],
        pages_checked=len(seen_pages), records_found=len(deduped),
        records_publishable=len(publishable), records_quarantined=len(rejected),
    )
    return publishable, rejected
