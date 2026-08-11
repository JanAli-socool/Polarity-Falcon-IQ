from __future__ import annotations

from stage2.enrichment import extract_enrichments, extract_official_people
from stage2.http import Observation
from stage2.policy import build_evidence, email_qualifies, evaluate_record


class RecordingLog:
    def __init__(self) -> None:
        self.events = []

    def emit(self, event, **details):
        self.events.append((event, details))


def candidate() -> dict:
    return {
        "candidate_id": "CAN_EXAMPLE",
        "firm_name": "Example Partners",
        "firm_type": "multi_family_office",
        "homepage": "https://example.com/",
        "discovery": {
            "source_class": "association_directory",
            "url": "https://directory.example/example",
            "observed_at": "2026-08-11T08:00:00Z",
            "extraction_method": "fixture_directory_entry",
            "quote": "Example Partners is an independent multi-family office.",
        },
    }


def observation(url: str, html: str) -> Observation:
    return Observation(
        url=url,
        final_url=url,
        observed_at="2026-08-11T09:00:00Z",
        status_code=200,
        content_type="text/html",
        text=html,
        content_sha256="fixture-sha",
        elapsed_ms=1,
    )


def test_official_dom_card_produces_evidence_bound_routes(monkeypatch):
    firm = candidate()
    home = observation(
        "https://example.com/",
        "<html><body>Example Partners is a multi-family office making direct investments in healthcare services.</body></html>",
    )
    enrichments = extract_enrichments(firm, home)
    classification = build_evidence(
        url=firm["discovery"]["url"],
        observed_at=firm["discovery"]["observed_at"],
        quote=firm["discovery"]["quote"],
        source_class="association_directory",
        extraction_method="fixture_directory_entry",
        supports=["firm.name", "firm.type"],
    )
    team = observation(
        "https://example.com/team",
        """
        <html><body><article class="person">
          <h3>Jane Smith</h3><p>Managing Partner</p>
          <a href="mailto:jane.smith@example.com">Email Jane Smith</a>
          <a href="https://www.linkedin.com/in/jane-smith/">LinkedIn</a>
        </article></body></html>
        """,
    )
    monkeypatch.setattr("stage2.enrichment._mx_present", lambda domain, log: True)
    records = extract_official_people(
        candidate=firm,
        observation=team,
        classification_evidence=classification,
        enrichments=enrichments,
        log=RecordingLog(),
    )

    assert len(records) == 1
    assert evaluate_record(records[0])["qualifies"] is True
    assert {route["type"] for route in records[0]["contact_routes"]} == {"email", "linkedin"}
    assert sum(email_qualifies(route) for route in records[0]["contact_routes"]) == 1


def test_card_without_explicit_person_name_is_rejected(monkeypatch):
    firm = candidate()
    classification = build_evidence(
        url=firm["discovery"]["url"],
        observed_at=firm["discovery"]["observed_at"],
        quote=firm["discovery"]["quote"],
        source_class="association_directory",
        extraction_method="fixture_directory_entry",
        supports=["firm.name", "firm.type"],
    )
    team = observation(
        "https://example.com/team",
        '<html><body><article><h3>Project Management</h3><p>Managing Partner</p><a href="mailto:office@example.com">Email</a></article></body></html>',
    )
    monkeypatch.setattr("stage2.enrichment._mx_present", lambda domain, log: True)
    records = extract_official_people(
        candidate=firm,
        observation=team,
        classification_evidence=classification,
        enrichments=[{
            "kind": "family_office_classification",
            "value": "multi_family_office",
            "evidence": classification | {
                "supports": ["enrichment.kind", "enrichment.value"],
            },
        }],
        log=RecordingLog(),
    )
    assert records == []
