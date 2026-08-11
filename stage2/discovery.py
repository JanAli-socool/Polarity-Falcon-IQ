"""Multi-source candidate discovery. Candidates are never production records."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import quote_plus, urljoin, urlparse

from bs4 import BeautifulSoup
from ddgs import DDGS

from stage2.http import ObservableHttpClient
from stage2.operating import OperatingLog, now_utc
from stage2.policy import is_http_url, normalize_space

DIRECTORY_SOURCES = (
    {
        "url": "https://canadianfamilyoffices.com/fundamentals/the-list-sixty-multi-family-offices-in-canada/",
        "source_class": "news_or_press",
        "label": "Canadian Family Offices permission-based MFO list",
    },
    {
        "url": "https://andsimple.co/family-offices",
        "source_class": "association_directory",
        "label": "Simple family-office directory",
    },
    {
        "url": "https://praxisrock.com/resources/investors/multi-family-offices",
        "source_class": "other_public_source",
        "label": "Praxis Rock researched MFO directory",
    },
    {
        "url": "https://bigblackbookdirectory.wordpress.com/2023/11/12/family-office-directory/",
        "source_class": "other_public_source",
        "label": "Big Black Book family-office directory",
    },
)

SEARCH_QUERIES = (
    '"multi-family office" "our team" investments',
    '"multi family office" "team" partner',
    '"single family office" investments team',
    '"family investment office" team',
    '"family office" "chief investment officer"',
    '"family office" "managing partner" investments',
    '"family office" principal investments United States',
    '"family office" principal investments Canada',
    '"family office" investment director Europe',
    '"family office" team United Kingdom',
    '"family office" team Singapore investments',
    '"family office" team Australia investments',
    '"family office" team Switzerland investments',
    '"family office" team Middle East investments',
    '"family office" team Latin America investments',
    'site:adviserinfo.sec.gov/firm/summary "family office"',
)

EXCLUDED_HOSTS = {
    "facebook.com", "www.facebook.com", "instagram.com", "www.instagram.com",
    "linkedin.com", "www.linkedin.com", "x.com", "twitter.com", "www.youtube.com",
    "andsimple.co", "bigblackbookdirectory.wordpress.com", "canadianfamilyoffices.com",
    "familyofficedirectories.com", "openvc.app", "praxisrock.com", "scribd.com",
}
GENERIC_TITLES = {
    "family office", "family offices", "family office directory", "our team", "team",
    "home", "about", "contact", "learn more", "visit", "website",
}
SUFFIX_RE = re.compile(
    r"\s*(?:[-|–—:]\s*)?(?:independent\s+)?(?:single[- ]family|multi[- ]family|family investment|family) office.*$",
    re.IGNORECASE,
)
PREFIX_RE = re.compile(r"^(?:welcome to|about)\s+", re.IGNORECASE)


def candidate_id(firm_name: str, homepage: str) -> str:
    raw = f"{normalize_space(firm_name).casefold()}|{normalize_space(homepage).casefold()}"
    return f"CAN_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:14].upper()}"


def _host(url: str) -> str:
    return urlparse(url).netloc.casefold().removeprefix("www.")


def _clean_firm_name(value: str) -> str:
    text = normalize_space(value)
    text = re.sub(r"\s+[|–—]\s+.*$", "", text)
    text = PREFIX_RE.sub("", text)
    stripped = SUFFIX_RE.sub("", text).strip(" -|–—:,.")
    if stripped and stripped.casefold() not in GENERIC_TITLES:
        text = stripped
    text = normalize_space(text).strip(" -|–—:,.")
    if len(text) < 2 or len(text) > 120 or text.casefold() in GENERIC_TITLES:
        return ""
    if len(text.split()) > 12:
        return ""
    return text


def _firm_type(quote: str) -> str:
    lowered = quote.casefold()
    if "multi-family office" in lowered or "multi family office" in lowered:
        return "multi_family_office"
    if "single-family office" in lowered or "single family office" in lowered:
        return "single_family_office"
    return "family_investment_office"


def _candidate(
    *,
    firm_name: str,
    homepage: str,
    discovery_url: str,
    discovery_source_class: str,
    quote: str,
    observed_at: str,
    method: str,
) -> dict[str, Any] | None:
    firm_name = _clean_firm_name(firm_name)
    homepage = normalize_space(homepage)
    quote = normalize_space(quote)[:1000]
    if not firm_name or not is_http_url(homepage) or "family office" not in quote.casefold().replace("-", " "):
        return None
    if _host(homepage) in EXCLUDED_HOSTS:
        return None
    return {
        "candidate_id": candidate_id(firm_name, homepage),
        "firm_name": firm_name,
        "firm_type": _firm_type(quote),
        "homepage": homepage,
        "discovered_at": observed_at,
        "discovery": {
            "source_class": discovery_source_class,
            "url": discovery_url,
            "observed_at": observed_at,
            "extraction_method": method,
            "quote": quote,
        },
        "status": "candidate",
    }


def discover_from_directory(
    source: dict[str, str], client: ObservableHttpClient, log: OperatingLog
) -> list[dict[str, Any]]:
    observation = client.get(source["url"], purpose=f"candidate_directory:{source['label']}")
    soup = BeautifulSoup(observation.text, "lxml")
    source_host = _host(source["url"])
    found: list[dict[str, Any]] = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(observation.final_url, anchor.get("href", ""))
        if not is_http_url(href) or _host(href) == source_host:
            continue
        label = normalize_space(anchor.get_text(" ", strip=True))
        parent_text = normalize_space(anchor.parent.get_text(" ", strip=True) if anchor.parent else label)
        context = parent_text if "family office" in parent_text.casefold().replace("-", " ") else label
        if "family office" not in context.casefold().replace("-", " "):
            continue
        name = label or context.split("family office", 1)[0]
        item = _candidate(
            firm_name=name,
            homepage=href,
            discovery_url=source["url"],
            discovery_source_class=source["source_class"],
            quote=context,
            observed_at=observation.observed_at,
            method="directory_html_anchor_context",
        )
        if item:
            found.append(item)
    log.emit("discovery.source.completed", source=source["url"], candidates=len(found))
    return found


def _search_result_firm_name(title: str, body: str) -> str:
    title = normalize_space(title)
    before = re.split(r"\s+[|–—:]\s+", title, maxsplit=1)[0]
    before = re.sub(r"\s+-\s+.*$", "", before)
    name = _clean_firm_name(before)
    if name:
        return name
    match = re.search(
        r"([A-Z][A-Za-z0-9&'’.]+(?:\s+[A-Z][A-Za-z0-9&'’.]+){0,7})\s+(?:is\s+an?\s+)?(?:independent\s+)?(?:multi[- ]family|single[- ]family|family) office",
        body,
    )
    return _clean_firm_name(match.group(1)) if match else ""


def discover_from_search(log: OperatingLog, *, per_query: int = 30) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    engine = DDGS(timeout=20)
    for query in SEARCH_QUERIES:
        log.emit("search.started", provider="duckduckgo", query=query, max_results=per_query)
        try:
            results = list(engine.text(query, max_results=per_query))
        except Exception as exc:  # provider library uses several exception classes
            log.emit(
                "search.failed", provider="duckduckgo", query=query,
                error_type=type(exc).__name__, error=str(exc)[:500],
            )
            continue
        accepted = 0
        query_url = f"https://duckduckgo.com/?q={quote_plus(query)}"
        for result in results:
            href = normalize_space(result.get("href"))
            title = normalize_space(result.get("title"))
            body = normalize_space(result.get("body"))
            quote = normalize_space(f"{title}. {body}")
            if "family office" not in quote.casefold().replace("-", " "):
                continue
            name = _search_result_firm_name(title, body)
            item = _candidate(
                firm_name=name,
                homepage=href,
                discovery_url=query_url,
                discovery_source_class=(
                    "regulatory_filing" if "adviserinfo.sec.gov" in href else "search_discovery"
                ),
                quote=quote,
                observed_at=now_utc(),
                method="duckduckgo_result_title_and_snippet",
            )
            if item:
                found.append(item)
                accepted += 1
        log.emit(
            "search.completed", provider="duckduckgo", query=query,
            returned=len(results), candidates=accepted,
        )
    return found


def discover_candidates(
    client: ObservableHttpClient,
    log: OperatingLog,
    *,
    include_search: bool = True,
    per_query: int = 30,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for source in DIRECTORY_SOURCES:
        try:
            candidates.extend(discover_from_directory(source, client, log))
        except RuntimeError as exc:
            log.emit("discovery.source.failed", source=source["url"], error=str(exc)[:500])
    if include_search:
        candidates.extend(discover_from_search(log, per_query=per_query))

    deduped: dict[str, dict[str, Any]] = {}
    for item in candidates:
        deduped.setdefault(item["candidate_id"], item)
    output = sorted(deduped.values(), key=lambda item: item["candidate_id"])
    log.emit("discovery.completed", raw_candidates=len(candidates), unique_candidates=len(output))
    return output
