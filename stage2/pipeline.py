"""Unattended discovery, enrichment, trust refresh, and canonical release cycle."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict, deque
from typing import Any

from ddgs import DDGS

from stage2.discovery import discover_candidates
from stage2.enrichment import enrich_candidate
from stage2.http import ObservableHttpClient
from stage2.io import read_jsonl, write_jsonl
from stage2.operating import OperatingLog, now_utc
from stage2.paths import (
    CANDIDATES,
    CANONICAL_RECORDS,
    QUARANTINE,
    SOURCE_OBSERVATIONS,
    ensure_data_dirs,
)
from stage2.policy import email_qualifies, evaluate_record, route_qualifies
from stage2.release import export_release

TARGET_RECORDS = 550
TARGET_EMAILS = 220


def _counts(records: list[dict[str, Any]]) -> tuple[int, int]:
    publishable = [record for record in records if record.get("lifecycle_status") == "publish" and evaluate_record(record)["qualifies"]]
    email_count = sum(
        any(email_qualifies(route) for route in record.get("contact_routes", []))
        for record in publishable
    )
    return len(publishable), email_count


def _merge_record(existing: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Idempotently merge a repeated identity without weakening newer evidence."""
    existing_check = existing.get("freshness", {}).get("last_evidence_check_at", "")
    new_check = new.get("freshness", {}).get("last_evidence_check_at", "")
    base, other = (new, existing) if new_check >= existing_check else (existing, new)
    base = json.loads(json.dumps(base))
    route_values = {(route.get("type"), route.get("value")) for route in base.get("contact_routes", [])}
    base.setdefault("contact_routes", []).extend(
        route for route in other.get("contact_routes", [])
        if (route.get("type"), route.get("value")) not in route_values and route_qualifies(route)
    )
    enrichment_values = {(item.get("kind"), item.get("value")) for item in base.get("enrichments", [])}
    base.setdefault("enrichments", []).extend(
        item for item in other.get("enrichments", [])
        if (item.get("kind"), item.get("value")) not in enrichment_values
    )
    basis = set(base.get("freshness", {}).get("basis_evidence_ids", []))
    basis.update(other.get("freshness", {}).get("basis_evidence_ids", []))
    base.setdefault("freshness", {})["basis_evidence_ids"] = sorted(basis)
    evaluation = evaluate_record(base)
    base["evaluation"] = evaluation
    base["lifecycle_status"] = "publish" if evaluation["qualifies"] else "quarantine"
    return base


def _balanced_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    for candidate in sorted(
        candidates,
        key=lambda item: (int(item.get("attempt_count", 0)), item.get("last_attempted_at", ""), item["candidate_id"]),
    ):
        buckets[candidate["discovery"]["source_class"]].append(candidate)
    order: list[dict[str, Any]] = []
    keys = sorted(buckets)
    while keys:
        next_keys: list[str] = []
        for key in keys:
            if buckets[key]:
                order.append(buckets[key].popleft())
            if buckets[key]:
                next_keys.append(key)
        keys = next_keys
    return order


def refresh_trust(
    records: list[dict[str, Any]],
    client: ObservableHttpClient,
    log: OperatingLog,
    *,
    batch_size: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    observations = {row.get("url"): row for row in read_jsonl(SOURCE_OBSERVATIONS) if row.get("url")}
    quarantine: list[dict[str, Any]] = []
    ordered = sorted(
        [record for record in records if record.get("lifecycle_status") == "publish"],
        key=lambda record: (record.get("freshness", {}).get("last_evidence_check_at", ""), record["record_id"]),
    )[:batch_size]
    for record in ordered:
        person = record["person"]["name"]
        firm = record["firm"]["name"]
        route = next((route for route in record.get("contact_routes", []) if route_qualifies(route)), None)
        if not route:
            record["lifecycle_status"] = "quarantine"
            quarantine.append({"record_id": record["record_id"], "reasons": ["route.none_qualify_on_refresh"], "record": record})
            continue
        source = route["evidence"]
        url = source["url"]
        old_state = record["freshness"].get("trust_state")
        still_present: bool | None = None
        content_hash = ""
        failure_reason = ""
        if source.get("source_class") == "professional_profile":
            query = f'site:linkedin.com/in "{person}" "{firm}"'
            log.emit("trust.refresh.started", record_id=record["record_id"], method="profile_search", url=url)
            try:
                results = list(DDGS(timeout=20).text(query, max_results=10))
                result_urls = {str(item.get("href", "")).split("?", 1)[0] for item in results}
                still_present = url.split("?", 1)[0] in result_urls
                content_hash = "search-result-present" if still_present else "search-result-absent"
            except Exception as exc:
                failure_reason = f"profile_search_dependency_failed:{type(exc).__name__}"
                log.emit("trust.refresh.deferred", record_id=record["record_id"], url=url, reason=failure_reason)
        else:
            log.emit("trust.refresh.started", record_id=record["record_id"], method="source_fetch", url=url)
            try:
                observation = client.get(url, purpose=f"trust_refresh:{record['record_id']}")
                content_hash = observation.content_sha256
                body = observation.text.casefold()
                still_present = person.casefold() in body and route["value"].casefold() in body
            except RuntimeError as exc:
                still_present = False
                failure_reason = f"required_source_unavailable:{str(exc)[:200]}"
        previous = observations.get(url)
        if previous and content_hash and previous.get("content_sha256") != content_hash:
            log.emit(
                "trust.source_content_changed", record_id=record["record_id"], url=url,
                prior_sha256=previous.get("content_sha256"), current_sha256=content_hash,
                required_evidence_still_present=still_present,
            )
        if content_hash:
            observations[url] = {
                "url": url, "content_sha256": content_hash, "checked_at": now_utc(),
                "record_id": record["record_id"], "required_evidence_present": still_present,
            }
        if still_present is True:
            record["freshness"]["last_evidence_check_at"] = now_utc()
            record["freshness"]["trust_state"] = "supported_current"
            record["freshness"]["reason"] = "Named person and qualifying route remained present on the checked source."
            log.emit("trust.refresh.passed", record_id=record["record_id"], url=url)
        elif still_present is False:
            record["freshness"]["trust_state"] = "stale_evidence_missing"
            record["freshness"]["reason"] = failure_reason or "Named person or qualifying route was no longer present on the checked source."
            record["lifecycle_status"] = "quarantine"
            quarantine.append({
                "record_id": record["record_id"], "reasons": ["freshness.required_evidence_missing"],
                "detected_at": now_utc(), "record": record,
            })
            log.emit(
                "trust.state_changed", record_id=record["record_id"], url=url,
                prior_state=old_state, current_state="stale_evidence_missing",
                action="removed_from_release_and_quarantined", reason=record["freshness"]["reason"],
            )
    write_jsonl(SOURCE_OBSERVATIONS, observations.values(), sort_key="url")
    return records, quarantine


def run_cycle(
    *,
    max_candidates: int,
    search_results_per_query: int,
    trust_refresh_batch: int,
    exercise_failure: bool,
) -> dict[str, Any]:
    ensure_data_dirs()
    log = OperatingLog()
    client = ObservableHttpClient(log)
    try:
        existing_records = read_jsonl(CANONICAL_RECORDS)
        existing_candidates = {row["candidate_id"]: row for row in read_jsonl(CANDIDATES)}
        record_count, email_count = _counts(existing_records)
        log.metrics["records_before"] = record_count
        log.emit("state.loaded", canonical_records=record_count, qualifying_emails=email_count, candidates=len(existing_candidates))

        if exercise_failure:
            client.dependency_failure_exercise()

        existing_records, trust_quarantine = refresh_trust(
            existing_records, client, log, batch_size=trust_refresh_batch
        )
        discovered = discover_candidates(client, log, per_query=search_results_per_query)
        for item in discovered:
            if item["candidate_id"] in existing_candidates:
                prior = existing_candidates[item["candidate_id"]]
                item["attempt_count"] = prior.get("attempt_count", 0)
                item["last_attempted_at"] = prior.get("last_attempted_at", "")
                item["last_outcome"] = prior.get("last_outcome", "")
            existing_candidates[item["candidate_id"]] = item
        write_jsonl(CANDIDATES, existing_candidates.values(), sort_key="candidate_id")

        records_by_identity = {
            record["identity_key"]: record for record in existing_records
            if record.get("lifecycle_status") == "publish" and evaluate_record(record)["qualifies"]
        }
        quarantine_rows = trust_quarantine
        processed = 0
        for candidate in _balanced_candidates(list(existing_candidates.values())):
            if processed >= max_candidates:
                break
            current_records, current_emails = _counts(list(records_by_identity.values()))
            if current_records >= TARGET_RECORDS and current_emails >= TARGET_EMAILS:
                log.emit("target.buffer_reached", records=current_records, qualifying_emails=current_emails)
                break
            processed += 1
            candidate["attempt_count"] = int(candidate.get("attempt_count", 0)) + 1
            candidate["last_attempted_at"] = now_utc()
            found, rejected = enrich_candidate(candidate, client, log)
            quarantine_rows.extend(rejected)
            candidate["last_outcome"] = "publishable_found" if found else "no_publishable_record"
            for record in found:
                identity = record["identity_key"]
                records_by_identity[identity] = (
                    _merge_record(records_by_identity[identity], record)
                    if identity in records_by_identity else record
                )
            record_count, email_count = _counts(list(records_by_identity.values()))
            log.emit(
                "replenishment.progress", candidates_processed=processed,
                records=record_count, qualifying_emails=email_count,
                records_target=TARGET_RECORDS, emails_target=TARGET_EMAILS,
            )

        canonical = sorted(records_by_identity.values(), key=lambda record: record["record_id"])
        write_jsonl(CANONICAL_RECORDS, canonical, sort_key="record_id")
        write_jsonl(CANDIDATES, existing_candidates.values(), sort_key="candidate_id")
        quarantine_path = QUARANTINE / f"{log.cycle}.jsonl"
        write_jsonl(quarantine_path, quarantine_rows, sort_key="record_id")
        manifest = export_release()
        final_count, final_emails = _counts(canonical)
        log.metrics["records_after"] = final_count
        log.metrics["records_added"] = final_count - int(log.metrics["records_before"])
        log.metrics["records_quarantined"] = len(quarantine_rows)
        status = "target_reached" if final_count >= TARGET_RECORDS and final_emails >= TARGET_EMAILS else "completed_below_target"
        summary = log.finish(
            status,
            records=final_count,
            qualifying_emails=final_emails,
            candidates_processed=processed,
            candidates_total=len(existing_candidates),
            release_id=manifest["release_id"],
            release_ready=manifest["release_ready"],
        )
        return summary
    except Exception as exc:
        log.emit("cycle.exception", error_type=type(exc).__name__, error=str(exc)[:1000])
        log.finish("failed", error_type=type(exc).__name__, error=str(exc)[:1000])
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-candidates", type=int, default=int(os.getenv("STAGE2_MAX_CANDIDATES", "80")))
    parser.add_argument("--search-results-per-query", type=int, default=int(os.getenv("STAGE2_SEARCH_RESULTS_PER_QUERY", "30")))
    parser.add_argument("--trust-refresh-batch", type=int, default=int(os.getenv("STAGE2_TRUST_REFRESH_BATCH", "50")))
    parser.add_argument("--skip-failure-exercise", action="store_true")
    args = parser.parse_args()
    result = run_cycle(
        max_candidates=args.max_candidates,
        search_results_per_query=args.search_results_per_query,
        trust_refresh_batch=args.trust_refresh_batch,
        exercise_failure=not args.skip_failure_exercise,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
