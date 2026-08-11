"""Deterministic evidence retrieval, compound decomposition, and fit comparison."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from stage2.io import read_jsonl
from stage2.paths import CANONICAL_RECORDS
from stage2.policy import email_qualifies, evaluate_record, normalize_space, route_qualifies

ALLOWED_FILTERS = {
    "firm_name", "country", "firm_type", "role_class", "route_type", "has_email",
    "intelligence_kind", "intelligence_term", "source_class", "trust_state",
}
FIT_TERMS = {
    "healthcare_services": ("healthcare", "health care", "healthcare services"),
    "lower_middle_market": ("lower-middle-market", "lower middle market", "lmm"),
    "private_markets": ("private equity", "direct investments", "buyout", "private markets"),
    "limited_partner_signal": ("limited partner", "private funds", "fund investments", "external funds"),
}


@dataclass(frozen=True)
class RetrievalQuery:
    filters: dict[str, Any] = field(default_factory=dict)
    terms: tuple[str, ...] = ()
    limit: int = 50
    offset: int = 0
    aggregate: str = "records"

    def validate(self) -> None:
        unknown = set(self.filters) - ALLOWED_FILTERS
        if unknown:
            raise ValueError(f"unsupported retrieval filters: {sorted(unknown)}")
        if self.limit < 1 or self.limit > 500:
            raise ValueError("limit must be between 1 and 500")
        if self.offset < 0:
            raise ValueError("offset cannot be negative")
        if self.aggregate not in {"records", "firms", "source_mix", "route_mix", "countries"}:
            raise ValueError(f"unsupported aggregate: {self.aggregate}")


def _authorize_corpus(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply publication policy and identity uniqueness to every read path."""
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in candidates:
        evaluation = evaluate_record(record)
        identity = record.get("identity_key", "")
        if (
            record.get("lifecycle_status") != "publish"
            or not evaluation["qualifies"]
            or not identity
            or identity in seen
        ):
            continue
        seen.add(identity)
        records.append(record)
    return sorted(records, key=lambda item: item["record_id"])


def authorized_records(path=CANONICAL_RECORDS) -> list[dict[str, Any]]:
    return _authorize_corpus(read_jsonl(path))


def _record_text(record: dict[str, Any]) -> str:
    values = [
        record["firm"].get("name", ""), record["firm"].get("country", ""),
        record["firm"].get("type", ""), record["person"].get("name", ""),
        record["person"].get("title", ""), record["person"].get("role_class", ""),
        record["discovery"].get("source_class", ""),
    ]
    values.extend(str(item.get("value", "")) for item in record.get("enrichments", []))
    return normalize_space(" ".join(values)).casefold()


def _matches(record: dict[str, Any], filters: dict[str, Any]) -> bool:
    routes = [route for route in record.get("contact_routes", []) if route_qualifies(route)]
    enrichments = record.get("enrichments", [])
    for key, value in filters.items():
        expected = str(value).casefold()
        if key == "firm_name" and expected not in record["firm"].get("name", "").casefold():
            return False
        if key == "country" and expected not in record["firm"].get("country", "").casefold():
            return False
        if key == "firm_type" and record["firm"].get("type", "").casefold() != expected:
            return False
        if key == "role_class" and record["person"].get("role_class", "").casefold() != expected:
            return False
        if key == "route_type" and not any(route.get("type", "").casefold() == expected for route in routes):
            return False
        if key == "has_email" and bool(value) != any(email_qualifies(route) for route in routes):
            return False
        if key == "intelligence_kind" and not any(item.get("kind", "").casefold() == expected for item in enrichments):
            return False
        if key == "intelligence_term" and not any(expected in str(item.get("value", "")).casefold() for item in enrichments):
            return False
        if key == "source_class" and record["discovery"].get("source_class", "").casefold() != expected:
            return False
        if key == "trust_state" and record["freshness"].get("trust_state", "").casefold() != expected:
            return False
    return True


def _rank(record: dict[str, Any], terms: tuple[str, ...]) -> tuple[int, str]:
    text = _record_text(record)
    score = sum(3 if term.casefold() in text else 0 for term in terms)
    name_text = f"{record['firm']['name']} {record['person']['name']}".casefold()
    score += sum(2 for term in terms if term.casefold() in name_text)
    return score, record["record_id"]


def evidence_summary(record: dict[str, Any]) -> dict[str, Any]:
    routes = [route for route in record.get("contact_routes", []) if route_qualifies(route)]
    return {
        "record_id": record["record_id"],
        "firm": record["firm"]["name"],
        "firm_type": record["firm"]["type"],
        "country": record["firm"].get("country", "") or "unknown",
        "person": record["person"]["name"],
        "title": record["person"]["title"],
        "role_class": record["person"]["role_class"],
        "routes": [
            {
                "type": route["type"], "value": route["value"],
                "ownership_basis": route.get("ownership_status"),
                "current_use_basis": route.get("current_status"),
                "evidence_id": route["evidence"]["evidence_id"],
                "evidence_url": route["evidence"]["url"],
                "observed_at": route["evidence"]["observed_at"],
            }
            for route in routes
        ],
        "intelligence": [
            {
                "kind": item["kind"], "value": item["value"],
                "evidence_id": item["evidence"]["evidence_id"],
                "evidence_url": item["evidence"]["url"],
                "evidence_quote": item["evidence"]["quote"],
            }
            for item in record.get("enrichments", [])
        ],
        "classification_evidence": {
            "evidence_id": record["firm"]["classification_evidence"]["evidence_id"],
            "url": record["firm"]["classification_evidence"]["url"],
            "quote": record["firm"]["classification_evidence"]["quote"],
        },
        "role_evidence": {
            "evidence_id": record["person"]["role_evidence"]["evidence_id"],
            "url": record["person"]["role_evidence"]["url"],
            "quote": record["person"]["role_evidence"]["quote"],
        },
        "trust_state": record["freshness"]["trust_state"],
        "last_evidence_check_at": record["freshness"]["last_evidence_check_at"],
        "known_limitations": record.get("known_limitations", []),
    }


def retrieve(query: RetrievalQuery, records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    query.validate()
    corpus = _authorize_corpus(records) if records is not None else authorized_records()
    matched = [record for record in corpus if _matches(record, query.filters)]
    if query.terms:
        matched = [record for record in matched if any(term.casefold() in _record_text(record) for term in query.terms)]
        matched.sort(key=lambda record: (-_rank(record, query.terms)[0], record["record_id"]))
    else:
        matched.sort(key=lambda record: record["record_id"])

    if query.aggregate == "firms":
        aggregate: Any = len({record["firm"]["name"].casefold() for record in matched})
    elif query.aggregate == "source_mix":
        aggregate = dict(sorted(Counter(record["discovery"]["source_class"] for record in matched).items()))
    elif query.aggregate == "route_mix":
        aggregate = dict(sorted(Counter(
            route["type"] for record in matched for route in record.get("contact_routes", []) if route_qualifies(route)
        ).items()))
    elif query.aggregate == "countries":
        aggregate = dict(sorted(Counter(record["firm"].get("country") or "unknown" for record in matched).items()))
    else:
        aggregate = len(matched)

    page = matched[query.offset : query.offset + query.limit]
    return {
        "status": "ok" if matched else "no_supported_match",
        "query": {
            "filters": query.filters, "terms": list(query.terms), "limit": query.limit,
            "offset": query.offset, "aggregate": query.aggregate,
        },
        "authorized_corpus_count": len(corpus),
        "matched_record_count": len(matched),
        "matched_firm_count": len({record["firm"]["name"].casefold() for record in matched}),
        "aggregate": aggregate,
        "returned_record_count": len(page),
        "records": [evidence_summary(record) for record in page],
        "limitations": (
            ["No production record satisfies every requested hard filter."] if not matched else []
        ),
    }


def decompose_natural_language(goal: str) -> list[RetrievalQuery]:
    """Deterministic fallback/parser; every compound clause becomes an inspectable query."""
    lowered = normalize_space(goal).casefold()
    filters: dict[str, Any] = {}
    terms: list[str] = []
    if "email" in lowered:
        filters["has_email"] = True
    if "linkedin" in lowered:
        filters["route_type"] = "linkedin"
    if "health" in lowered:
        terms.append("healthcare")
    if "lower-middle-market" in lowered or "lower middle market" in lowered:
        terms.extend(["lower-middle-market", "lower middle market"])
    if "private equity" in lowered:
        terms.append("private equity")
    if "current" in lowered:
        filters["trust_state"] = "supported_current"
    if "united states" in lowered or " u.s." in lowered or " us " in f" {lowered} ":
        filters["country"] = "united states"
    aggregate = "firms" if ("how many" in lowered or "count" in lowered) and "firm" in lowered else "records"
    queries = [RetrievalQuery(filters=filters, terms=tuple(dict.fromkeys(terms)), limit=100, aggregate=aggregate)]
    if "source mix" in lowered:
        queries.append(RetrievalQuery(filters=filters, terms=tuple(dict.fromkeys(terms)), limit=1, aggregate="source_mix"))
    if "route mix" in lowered or "contact mix" in lowered:
        queries.append(RetrievalQuery(filters=filters, terms=tuple(dict.fromkeys(terms)), limit=1, aggregate="route_mix"))
    return queries


def compare_lmm_healthcare_lp_fit(records: list[dict[str, Any]] | None = None, limit: int = 20) -> dict[str, Any]:
    """Evidence-only Goal-2 comparison; absent LP appetite is never inferred."""
    corpus = _authorize_corpus(records) if records is not None else authorized_records()
    by_firm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in corpus:
        by_firm[record["firm"]["name"]].append(record)
    comparisons: list[dict[str, Any]] = []
    for firm, firm_records in by_firm.items():
        combined = " ".join(
            str(item.get("value", ""))
            for record in firm_records for item in record.get("enrichments", [])
        ).casefold()
        signals: dict[str, bool] = {
            key: any(term in combined for term in terms) for key, terms in FIT_TERMS.items()
        }
        if not signals["healthcare_services"]:
            continue
        score = (
            35 * signals["healthcare_services"]
            + 25 * signals["lower_middle_market"]
            + 20 * signals["private_markets"]
            + 20 * signals["limited_partner_signal"]
        )
        if signals["limited_partner_signal"] and signals["lower_middle_market"] and signals["private_markets"]:
            confidence = "high"
        elif score >= 55:
            confidence = "medium"
        else:
            confidence = "low"
        best_contact = sorted(
            firm_records,
            key=lambda record: (
                -int(any(email_qualifies(route) for route in record.get("contact_routes", []))),
                record["record_id"],
            ),
        )[0]
        limitations = []
        if not signals["limited_partner_signal"]:
            limitations.append("No published evidence in this dataset establishes current appetite for external fund commitments.")
        if not signals["lower_middle_market"]:
            limitations.append("No published evidence in this dataset establishes a lower-middle-market mandate.")
        comparisons.append({
            "firm": firm,
            "fit_score": score,
            "confidence": confidence,
            "signals": signals,
            "recommended_contact": evidence_summary(best_contact),
            "supporting_records": [record["record_id"] for record in firm_records],
            "limitations": limitations,
            "supported_action": (
                "Use the person-owned route to test LP mandate and allocation timing; do not present the firm as a confirmed LP."
            ),
        })
    comparisons.sort(key=lambda item: (-item["fit_score"], item["firm"].casefold()))
    return {
        "goal": "Identify the family offices in the dataset that are the best fit for a lower-middle-market healthcare services fund seeking limited partners, and tell me how confident you are in each.",
        "method": "Deterministic four-signal evidence comparison; no missing mandate is inferred.",
        "authorized_corpus_count": len(corpus),
        "candidate_firm_count": len(comparisons),
        "results": comparisons[:limit],
        "limitations": (["The production release contains no supported healthcare fit candidate."] if not comparisons else []),
    }
