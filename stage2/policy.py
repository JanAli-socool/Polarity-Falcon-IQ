"""Code-enforced record inclusion, route ownership, and language policy.

The policy deliberately returns reason codes instead of a single confidence
score. A record may be useful while still failing the production floor, and a
weighted score must not allow one strong field to hide a missing hard floor.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

SUPPORTED_FIRM_TYPES = {"single_family_office", "multi_family_office", "family_investment_office"}
SUPPORTED_SOURCE_CLASSES = {
    "official_firm_site",
    "regulatory_filing",
    "association_directory",
    "search_discovery",
    "company_registry",
    "news_or_press",
    "professional_profile",
    "other_public_source",
}
DECISION_ROLE_CLASSES = {
    "investment_decision_maker",
    "executive_decision_maker",
    "partner_or_principal",
    "capital_or_relationship_lead",
}
DECISION_RELEVANT_ENRICHMENT = {
    "asset_class",
    "sector",
    "investment_stage",
    "investment_geography",
    "check_size",
    "aum",
    "dated_investment_activity",
    "investment_thesis",
    "family_office_classification",
}
GENERIC_EMAIL_LOCAL_PARTS = {
    "admin", "admissions", "careers", "clientservices", "compliance", "contact",
    "enquiries", "hello", "help", "hr", "info", "inquiries", "investorrelations",
    "ir", "mail", "marketing", "office", "operations", "press", "reception",
    "sales", "support", "team",
}
NON_PERSON_PHRASES = {
    "about us", "allow us", "client login", "connect with", "contact us", "family office",
    "investment management", "learn more", "our people", "our team", "private wealth",
    "project management", "read bio", "wealth management",
}
NON_PERSON_TOKENS = {
    "advisory", "capital", "chief", "director", "executive", "founder", "investment",
    "investments", "login", "management", "managing", "office", "partner", "planning",
    "president", "principal", "private", "project", "services", "team", "wealth",
}
PERSON_RE = re.compile(r"^[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+(?:\s+[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+){1,4}$")
EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")
PHONE_RE = re.compile(r"^\+?[0-9][0-9().\s-]{6,24}$")
LINKEDIN_HOSTS = {"linkedin.com", "www.linkedin.com", "uk.linkedin.com", "ca.linkedin.com", "au.linkedin.com"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_name(value: Any) -> str:
    return normalize_space(value)


def identity_key(firm_name: str, person_name: str) -> str:
    normalized = f"{normalize_space(firm_name).casefold()}|{normalize_name(person_name).casefold()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def record_id_for(firm_name: str, person_name: str) -> str:
    return f"FOC_{identity_key(firm_name, person_name)[:12].upper()}"


def is_person_name(value: Any) -> bool:
    name = normalize_name(value)
    lowered = name.casefold()
    tokens = {token.strip(".'’- ").casefold() for token in name.split()}
    return (
        bool(PERSON_RE.fullmatch(name))
        and not any(phrase in lowered for phrase in NON_PERSON_PHRASES)
        and not tokens.intersection(NON_PERSON_TOKENS)
    )


def is_http_url(value: Any) -> bool:
    try:
        parsed = urlparse(normalize_space(value))
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False


def evidence_id_for(url: str, observed_at: str, quote: str) -> str:
    payload = "|".join((normalize_space(url), normalize_space(observed_at), normalize_space(quote)))
    return f"EV_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16].upper()}"


def build_evidence(
    *,
    url: str,
    observed_at: str,
    quote: str,
    source_class: str,
    extraction_method: str,
    supports: list[str],
    support: str = "supported",
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id_for(url, observed_at, quote),
        "url": normalize_space(url),
        "observed_at": normalize_space(observed_at),
        "quote": normalize_space(quote),
        "source_class": source_class,
        "extraction_method": extraction_method,
        "supports": sorted(set(supports)),
        "support": support,
    }


def evidence_is_supported(
    evidence: dict[str, Any],
    *,
    require_quote: bool = True,
    required_supports: set[str] | None = None,
) -> bool:
    if not isinstance(evidence, dict):
        return False
    if evidence.get("support") != "supported":
        return False
    url = normalize_space(evidence.get("url"))
    observed_at = normalize_space(evidence.get("observed_at"))
    quote = normalize_space(evidence.get("quote"))
    if not is_http_url(url) or not observed_at:
        return False
    if require_quote and not quote:
        return False
    if evidence.get("evidence_id") != evidence_id_for(url, observed_at, quote):
        return False
    if evidence.get("source_class") not in SUPPORTED_SOURCE_CLASSES:
        return False
    if not normalize_space(evidence.get("extraction_method")):
        return False
    supports = set(evidence.get("supports", []))
    if required_supports and not required_supports.issubset(supports):
        return False
    return True


def email_route_reasons(route: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    value = normalize_space(route.get("value")).lower()
    if not EMAIL_RE.fullmatch(value):
        reasons.append("route.email.invalid_format")
        return reasons
    local = value.split("@", 1)[0].replace(".", "").replace("-", "").replace("_", "")
    if local in GENERIC_EMAIL_LOCAL_PARTS or route.get("shared") is True:
        reasons.append("route.email.generic_or_shared")
    if route.get("inferred") is True or route.get("ownership_method") in {"pattern", "inferred", "guessed"}:
        reasons.append("route.email.inferred")
    if route.get("ownership_status") != "source_names_person":
        reasons.append("route.email.ownership_not_established")
    if route.get("current_status") not in {"published_on_current_official_source", "mailbox_confirmed"}:
        reasons.append("route.email.current_use_not_established")
    if route.get("domain_mail_status") not in {"mx_present", "mailbox_confirmed"}:
        reasons.append("route.email.domain_mail_unconfirmed")
    if not evidence_is_supported(
        route.get("evidence", {}),
        required_supports={"person.name", "route.value", "route.ownership"},
    ):
        reasons.append("route.email.evidence_missing")
    return reasons


def linkedin_route_reasons(route: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    value = normalize_space(route.get("value"))
    if not is_http_url(value):
        return ["route.linkedin.invalid_url"]
    parsed = urlparse(value)
    if parsed.netloc.casefold() not in LINKEDIN_HOSTS or not parsed.path.casefold().startswith("/in/"):
        reasons.append("route.linkedin.not_individual_profile")
    if route.get("ownership_status") != "source_names_person":
        reasons.append("route.linkedin.ownership_not_established")
    if route.get("current_status") != "profile_link_currently_published":
        reasons.append("route.linkedin.current_use_not_established")
    if not evidence_is_supported(
        route.get("evidence", {}),
        required_supports={"person.name", "route.value", "route.ownership"},
    ):
        reasons.append("route.linkedin.evidence_missing")
    return reasons


def phone_route_reasons(route: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    value = normalize_space(route.get("value"))
    if not PHONE_RE.fullmatch(value):
        reasons.append("route.phone.invalid_format")
    if route.get("shared") is True or route.get("ownership_status") != "source_names_person_direct_line":
        reasons.append("route.phone.not_person_direct")
    if route.get("current_status") != "published_on_current_official_source":
        reasons.append("route.phone.current_use_not_established")
    if not evidence_is_supported(
        route.get("evidence", {}),
        required_supports={"person.name", "route.value", "route.ownership"},
    ):
        reasons.append("route.phone.evidence_missing")
    return reasons


def route_reasons(route: dict[str, Any]) -> list[str]:
    route_type = route.get("type")
    if route_type == "email":
        return email_route_reasons(route)
    if route_type == "linkedin":
        return linkedin_route_reasons(route)
    if route_type == "direct_phone":
        return phone_route_reasons(route)
    return ["route.unsupported_type"]


def route_qualifies(route: dict[str, Any]) -> bool:
    return not route_reasons(route)


def email_qualifies(route: dict[str, Any]) -> bool:
    return route.get("type") == "email" and route_qualifies(route)


def evaluate_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return independent hard-floor failures for one canonical record."""
    reasons: list[str] = []
    firm = record.get("firm", {})
    person = record.get("person", {})

    if record.get("schema_version") != "2.0":
        reasons.append("record.schema_version")
    if not normalize_space(record.get("record_id")):
        reasons.append("record.id_missing")
    if not normalize_space(record.get("identity_key")):
        reasons.append("record.identity_key_missing")
    expected_identity = identity_key(firm.get("name", ""), person.get("name", ""))
    if record.get("identity_key") and record.get("identity_key") != expected_identity:
        reasons.append("record.identity_key_mismatch")
    if record.get("record_id") and record.get("record_id") != record_id_for(firm.get("name", ""), person.get("name", "")):
        reasons.append("record.id_mismatch")

    if not normalize_space(firm.get("name")):
        reasons.append("firm.name_missing")
    if firm.get("type") not in SUPPORTED_FIRM_TYPES:
        reasons.append("firm.type_not_qualifying")
    if not evidence_is_supported(
        firm.get("classification_evidence", {}),
        required_supports={"firm.name", "firm.type"},
    ):
        reasons.append("firm.classification_unsupported")

    if not is_person_name(person.get("name")):
        reasons.append("person.name_not_plausible")
    if not normalize_space(person.get("title")):
        reasons.append("person.title_missing")
    if person.get("role_class") not in DECISION_ROLE_CLASSES:
        reasons.append("person.role_not_decision_relevant")
    if not evidence_is_supported(
        person.get("role_evidence", {}),
        required_supports={"firm.name", "person.firm_relationship", "person.name", "person.title"},
    ):
        reasons.append("person.role_unsupported")

    discovery = record.get("discovery", {})
    if discovery.get("source_class") not in SUPPORTED_SOURCE_CLASSES:
        reasons.append("discovery.source_class_missing")
    if (
        not is_http_url(discovery.get("url"))
        or not normalize_space(discovery.get("observed_at"))
        or not normalize_space(discovery.get("extraction_method"))
    ):
        reasons.append("discovery.source_missing")

    enrichments = record.get("enrichments", [])
    qualifying_enrichments = [
        item for item in enrichments
        if item.get("kind") in DECISION_RELEVANT_ENRICHMENT
        and evidence_is_supported(
            item.get("evidence", {}),
            required_supports={"enrichment.kind", "enrichment.value"},
        )
    ]
    if not qualifying_enrichments:
        reasons.append("enrichment.decision_relevant_missing")

    routes = record.get("contact_routes", [])
    if not isinstance(routes, list) or not routes:
        reasons.append("route.missing")
    elif not any(route_qualifies(route) for route in routes):
        reasons.append("route.none_qualify")

    freshness = record.get("freshness", {})
    if freshness.get("trust_state") not in {"supported_current", "supported_with_limitations"}:
        reasons.append("freshness.not_publishable")
    if not normalize_space(freshness.get("last_evidence_check_at")):
        reasons.append("freshness.never_checked")
    if not freshness.get("basis_evidence_ids"):
        reasons.append("freshness.evidence_basis_missing")

    # Every customer-visible optional claim must carry evidence or remain blank.
    for index, claim in enumerate(record.get("claims", [])):
        if normalize_space(claim.get("value")) and not evidence_is_supported(
            claim.get("evidence", {}), required_supports={"claim.value"}
        ):
            reasons.append(f"claim.{index}.unsupported")

    return {
        "qualifies": not reasons,
        "reasons": sorted(set(reasons)),
        "qualifying_route_count": sum(route_qualifies(route) for route in routes if isinstance(route, dict)),
        "qualifying_email_count": sum(email_qualifies(route) for route in routes if isinstance(route, dict)),
        "evaluated_at": utc_now(),
    }


def build_record(
    *,
    firm: dict[str, Any],
    person: dict[str, Any],
    discovery: dict[str, Any],
    enrichments: list[dict[str, Any]],
    contact_routes: list[dict[str, Any]],
    freshness: dict[str, Any],
    claims: list[dict[str, Any]] | None = None,
    lifecycle_status: str = "candidate",
) -> dict[str, Any]:
    firm_name = normalize_space(firm.get("name"))
    person_name = normalize_name(person.get("name"))
    return {
        "schema_version": "2.0",
        "record_id": record_id_for(firm_name, person_name),
        "identity_key": identity_key(firm_name, person_name),
        "lifecycle_status": lifecycle_status,
        "firm": firm,
        "person": person,
        "discovery": discovery,
        "enrichments": enrichments,
        "contact_routes": contact_routes,
        "freshness": freshness,
        "claims": claims or [],
    }
