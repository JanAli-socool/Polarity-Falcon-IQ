from __future__ import annotations

import json
import sys
from copy import deepcopy
from types import SimpleNamespace

import pytest

from stage2 import agent
from stage2.agent import GOAL_2, run_agent
from stage2.policy import build_evidence
from stage2.retrieval import (
    RetrievalQuery,
    compare_lmm_healthcare_lp_fit,
    decompose_natural_language,
    retrieve,
)


def _full_fit_record(valid_record):
    record = deepcopy(valid_record)
    evidence = build_evidence(
        url="https://example.com/mandate",
        observed_at="2026-08-11T08:00:00Z",
        quote="We make lower-middle-market private equity fund investments as a limited partner.",
        source_class="official_firm_site",
        extraction_method="fixture_html_text",
        supports=["enrichment.kind", "enrichment.value"],
    )
    record["enrichments"].append({
        "kind": "investment_thesis",
        "value": "Lower-middle-market private equity fund investments as a limited partner",
        "evidence": evidence,
    })
    record["freshness"]["basis_evidence_ids"].append(evidence["evidence_id"])
    return record


def test_compound_filter_and_aggregate_are_exact(valid_record):
    result = retrieve(
        RetrievalQuery(
            filters={"has_email": True, "intelligence_term": "healthcare"},
            terms=("managing partner",),
            aggregate="firms",
        ),
        [valid_record],
    )
    assert result["authorized_corpus_count"] == 1
    assert result["matched_record_count"] == 1
    assert result["matched_firm_count"] == 1
    assert result["aggregate"] == 1
    assert result["records"][0]["record_id"] == valid_record["record_id"]


def test_unknown_filter_is_rejected_before_retrieval(valid_record):
    with pytest.raises(ValueError, match="unsupported retrieval filters"):
        retrieve(RetrievalQuery(filters={"confidence": "high"}), [valid_record])


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (RetrievalQuery(filters={"route_type": "email"}), 1),
        (RetrievalQuery(filters={"route_type": "linkedin"}), 0),
        (RetrievalQuery(filters={"has_email": False}), 0),
        (RetrievalQuery(filters={"country": "united states"}), 1),
    ],
)
def test_route_and_location_filters_are_exact(valid_record, query, expected):
    assert retrieve(query, [valid_record])["matched_record_count"] == expected


def test_deterministic_aggregate_combinations(valid_record):
    assert retrieve(RetrievalQuery(aggregate="source_mix"), [valid_record])["aggregate"] == {
        "association_directory": 1,
    }
    assert retrieve(RetrievalQuery(aggregate="route_mix"), [valid_record])["aggregate"] == {"email": 1}
    assert retrieve(RetrievalQuery(aggregate="countries"), [valid_record])["aggregate"] == {"United States": 1}


def test_compound_language_decomposes_filter_terms_and_source_mix():
    queries = decompose_natural_language(
        "Find United States lower-middle-market healthcare contacts with email and show source mix"
    )
    assert len(queries) == 2
    assert queries[0].filters == {"has_email": True, "country": "united states"}
    assert set(queries[0].terms) == {"healthcare", "lower-middle-market", "lower middle market"}
    assert queries[1].aggregate == "source_mix"


def test_read_authority_rejects_quarantine_stale_and_duplicates(valid_record):
    quarantined = deepcopy(valid_record)
    quarantined["lifecycle_status"] = "quarantine"
    stale = deepcopy(valid_record)
    stale["freshness"]["trust_state"] = "stale"
    duplicate = deepcopy(valid_record)
    result = retrieve(RetrievalQuery(), [quarantined, stale, valid_record, duplicate])
    assert result["authorized_corpus_count"] == 1
    assert result["returned_record_count"] == 1


def test_goal2_does_not_infer_lp_appetite(valid_record):
    comparison = compare_lmm_healthcare_lp_fit([valid_record])
    assert comparison["goal"] == GOAL_2
    assert comparison["candidate_firm_count"] == 1
    result = comparison["results"][0]
    assert result["signals"]["healthcare_services"] is True
    assert result["signals"]["limited_partner_signal"] is False
    assert result["confidence"] == "low"
    assert "No published evidence" in result["limitations"][0]
    assert "do not present the firm as a confirmed LP" in result["supported_action"]


def test_goal2_high_confidence_requires_all_mandate_signals(valid_record):
    comparison = compare_lmm_healthcare_lp_fit([_full_fit_record(valid_record)])
    result = comparison["results"][0]
    assert result["signals"] == {
        "healthcare_services": True,
        "lower_middle_market": True,
        "private_markets": True,
        "limited_partner_signal": True,
    }
    assert result["fit_score"] == 100
    assert result["confidence"] == "high"
    assert result["limitations"] == []


def test_goal2_empty_release_abstains(monkeypatch):
    monkeypatch.setattr("stage2.agent.authorized_records", lambda: [])
    result = run_agent(GOAL_2, use_model=False, save_trace=False)
    assert result["status"] == "abstained"
    assert result["render_authority"]["decision"] == "abstain"
    assert "no supported candidate" in result["render_authority"]["reason"].casefold()


def test_agent_fallback_has_raw_tool_and_authority_trace(valid_record, monkeypatch):
    monkeypatch.setattr("stage2.agent.authorized_records", lambda: [valid_record])
    result = run_agent(
        "Find healthcare family offices with a person-owned email and report the firm count and source mix.",
        use_model=False,
        save_trace=False,
    )
    assert result["planner_mode"] == "deterministic_fallback"
    assert result["status"] == "ok"
    events = [item["event"] for item in result["trace"]]
    assert "tool.call" in events
    assert "tool.result" in events
    assert "render.authority_decision" in events
    assert result["render_authority"]["authorized_record_ids"] == [valid_record["record_id"]]


@pytest.mark.parametrize(
    "plan",
    [
        {"decision": "execute", "tool_calls": [{"tool": "shell", "arguments": {}}]},
        {"decision": "execute", "tool_calls": [{"tool": "search_records", "arguments": {"secret": "x"}}]},
        {"decision": "execute", "tool_calls": [{"tool": "search_records", "arguments": {"terms": "health"}}]},
        {"decision": "refuse", "tool_calls": [{"tool": "search_records", "arguments": {}}]},
    ],
)
def test_malformed_or_non_allowlisted_plans_are_rejected(plan):
    with pytest.raises(ValueError):
        agent._validate_plan(plan)


def test_model_retries_after_malformed_json_and_keeps_raw_events(valid_record, monkeypatch):
    class FakeCompletions:
        calls = 0

        def create(self, **kwargs):
            del kwargs
            self.calls += 1
            content = "not-json" if self.calls == 1 else json.dumps({
                "decision": "execute",
                "reason": "count supported records",
                "tool_calls": [{"tool": "search_records", "arguments": {"aggregate": "firms"}}],
            })
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
                usage=None,
            )

    completions = FakeCompletions()
    fake_groq = SimpleNamespace(
        Groq=lambda api_key: SimpleNamespace(chat=SimpleNamespace(completions=completions))
    )
    monkeypatch.setitem(sys.modules, "groq", fake_groq)
    monkeypatch.setenv("GROQ_API_KEY", "fixture-key-not-a-secret")
    monkeypatch.setattr("stage2.agent.authorized_records", lambda: [valid_record])
    result = run_agent("Count the firms in the released dataset", save_trace=False)
    assert result["planner_mode"] == "model"
    assert result["status"] == "ok"
    assert [event["event"] for event in result["trace"]].count("model.retry_or_failure") == 1
    assert [event["event"] for event in result["trace"]].count("model.request") == 2


def test_render_authority_replays_and_rejects_modified_claim(valid_record):
    call = {
        "tool": "search_records",
        "arguments": {"filters": {}, "terms": [], "limit": 50, "offset": 0, "aggregate": "records"},
    }
    output = agent._execute(call, [valid_record])
    output["records"][0]["title"] = "Unsupported invented title"
    authority = agent._authorize_output(
        "Who is this person?",
        [{"tool": call["tool"], "arguments": call["arguments"], "result": output}],
        [valid_record],
    )
    assert authority["passed"] is False
    assert authority["decision"] == "refuse"
    assert "differed from deterministic tool replay" in authority["reason"]


def test_refusal_is_traced_and_persisted(tmp_path, monkeypatch):
    monkeypatch.setattr("stage2.agent.GOAL_LOGS", tmp_path)
    result = run_agent("", save_trace=True)
    assert result["status"] == "refused"
    assert [event["event"] for event in result["trace"]] == ["goal.received", "goal.refused"]
    assert (tmp_path / f"{result['trace_id']}.jsonl").exists()
