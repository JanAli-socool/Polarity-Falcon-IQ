from copy import deepcopy

import pytest

from stage2.policy import evaluate_record, is_person_name, route_qualifies


def test_complete_supported_record_qualifies(valid_record):
    result = evaluate_record(valid_record)
    assert result["qualifies"] is True
    assert result["reasons"] == []
    assert result["qualifying_route_count"] == 1
    assert result["qualifying_email_count"] == 1


@pytest.mark.parametrize(
    "text",
    [
        "Allow Us",
        "Connect With",
        "Our Team",
        "Private Wealth",
        "Contact Us",
        "Project Management",
        "Client Login",
    ],
)
def test_navigation_or_marketing_text_is_not_a_person(text):
    assert is_person_name(text) is False


@pytest.mark.parametrize("name", ["Jane Smith", "George P. Beal", "Jean-Luc Picard", "María García"])
def test_plausible_person_names_are_not_blocked(name):
    assert is_person_name(name) is True


def test_generic_email_cannot_be_a_person_route(valid_record):
    route = valid_record["contact_routes"][0]
    route["value"] = "info@example.com"
    assert route_qualifies(route) is False
    result = evaluate_record(valid_record)
    assert result["qualifies"] is False
    assert "route.none_qualify" in result["reasons"]


def test_inferred_email_cannot_be_a_person_route(valid_record):
    route = valid_record["contact_routes"][0]
    route["inferred"] = True
    route["ownership_method"] = "pattern"
    assert route_qualifies(route) is False


def test_mailbox_check_without_ownership_does_not_qualify(valid_record):
    route = valid_record["contact_routes"][0]
    route["current_status"] = "mailbox_confirmed"
    route["domain_mail_status"] = "mailbox_confirmed"
    route["ownership_status"] = "unresolved"
    assert route_qualifies(route) is False


def test_seed_only_record_does_not_qualify(valid_record):
    valid_record["enrichments"] = []
    result = evaluate_record(valid_record)
    assert "enrichment.decision_relevant_missing" in result["reasons"]


def test_optional_populated_claim_requires_evidence(valid_record):
    valid_record["claims"] = [{"field": "aum", "value": "$5 billion", "evidence": {}}]
    result = evaluate_record(valid_record)
    assert "claim.0.unsupported" in result["reasons"]


def test_evidence_metadata_and_claim_authority_are_enforced(valid_record):
    del valid_record["person"]["role_evidence"]["extraction_method"]
    result = evaluate_record(valid_record)
    assert "person.role_unsupported" in result["reasons"]

    valid_record["person"]["role_evidence"]["extraction_method"] = "fixture_html_text"
    valid_record["person"]["role_evidence"]["supports"].remove("person.firm_relationship")
    result = evaluate_record(valid_record)
    assert "person.role_unsupported" in result["reasons"]


def test_shared_switchboard_does_not_qualify(valid_record):
    valid_record["contact_routes"] = [
        {
            "type": "direct_phone",
            "value": "+1 212 555 1000",
            "ownership_status": "firm_switchboard",
            "current_status": "published_on_current_official_source",
            "shared": True,
            "evidence": deepcopy(valid_record["person"]["role_evidence"]),
        }
    ]
    result = evaluate_record(valid_record)
    assert "route.none_qualify" in result["reasons"]
