from __future__ import annotations

from copy import deepcopy

import pytest

from stage2.policy import build_evidence, build_record


@pytest.fixture
def valid_record() -> dict:
    observed = "2026-08-11T08:00:00Z"
    firm_url = "https://example.com/about"
    person_url = "https://example.com/team/jane-smith"
    record = build_record(
        firm={
            "name": "Example Family Office",
            "type": "multi_family_office",
            "country": "United States",
            "classification_evidence": build_evidence(
                url=firm_url,
                observed_at=observed,
                quote="Example is an independent multi-family office.",
                source_class="official_firm_site",
                extraction_method="fixture_html_text",
                supports=["firm.name", "firm.type"],
            ),
        },
        person={
            "name": "Jane Smith",
            "title": "Managing Partner and Chief Investment Officer",
            "role_class": "investment_decision_maker",
            "role_evidence": build_evidence(
                url=person_url,
                observed_at=observed,
                quote="Jane Smith — Managing Partner and Chief Investment Officer at Example Family Office",
                source_class="official_firm_site",
                extraction_method="fixture_html_text",
                supports=["firm.name", "person.firm_relationship", "person.name", "person.title"],
            ),
        },
        discovery={
            "source_class": "association_directory",
            "url": "https://directory.example.org/example-family-office",
            "observed_at": observed,
            "extraction_method": "fixture_directory_entry",
        },
        enrichments=[
            {
                "kind": "sector",
                "value": "Healthcare services",
                "evidence": build_evidence(
                    url="https://example.com/investments",
                    observed_at=observed,
                    quote="We invest in lower-middle-market healthcare services businesses.",
                    source_class="official_firm_site",
                    extraction_method="fixture_html_text",
                    supports=["enrichment.kind", "enrichment.value"],
                ),
            }
        ],
        contact_routes=[
            {
                "type": "email",
                "value": "jane.smith@example.com",
                "ownership_status": "source_names_person",
                "ownership_method": "official_person_page",
                "current_status": "published_on_current_official_source",
                "domain_mail_status": "mx_present",
                "shared": False,
                "inferred": False,
                "evidence": build_evidence(
                    url=person_url,
                    observed_at=observed,
                    quote="Jane Smith jane.smith@example.com",
                    source_class="official_firm_site",
                    extraction_method="fixture_html_text",
                    supports=["person.name", "route.value", "route.ownership"],
                ),
            }
        ],
        freshness={
            "trust_state": "supported_current",
            "last_evidence_check_at": observed,
            "basis_evidence_ids": [],
            "reason": "Required evidence remained present on live sources.",
        },
        lifecycle_status="publish",
    )
    record["freshness"]["basis_evidence_ids"] = [
        record["firm"]["classification_evidence"]["evidence_id"],
        record["person"]["role_evidence"]["evidence_id"],
        record["enrichments"][0]["evidence"]["evidence_id"],
        record["contact_routes"][0]["evidence"]["evidence_id"],
    ]
    return deepcopy(record)
