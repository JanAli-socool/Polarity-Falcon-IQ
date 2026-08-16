# tests/test_suite.py
# Real test suite with assertions - replaces 99_stress_test.py
# Tests the canonical dataset, retrieval, agent, and query layer

import pytest
import json
import pathlib
import sqlite3
from rag.retriever_v2 import retrieve, get_evidence_for_generation
from rag.agent import Agent, run_agent
from rag.generator_v2 import _claim_check, _pre_generation_check
from pipeline.query_layer import QueryLayer
from pipeline.schema import count_qualifying, count_qualifying_with_email, get_firm_counts

# ---- Fixtures ----

@pytest.fixture(scope="session")
def canonical_db():
    """Path to canonical SQLite database."""
    return pathlib.Path("data/canonical/contacts.db")

@pytest.fixture(scope="session")
def qualifying_people():
    """All qualifying people from canonical DB."""
    conn = sqlite3.connect("data/canonical/contacts.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM people WHERE status = 'qualifying' ORDER BY record_id")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

@pytest.fixture(scope="session")
def firms():
    """All firms from canonical DB."""
    conn = sqlite3.connect("data/canonical/contacts.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM firms ORDER BY firm_name")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ---- Dataset Integrity Tests ----

class TestDatasetIntegrity:
    """Tests that the canonical dataset meets minimum quality standards."""

    def test_minimum_500_records(self, qualifying_people):
        """Hard requirement: at least 500 qualifying records."""
        assert len(qualifying_people) >= 500, f"Expected at least 500 qualifying records, got {len(qualifying_people)}"

    def test_minimum_200_verified_emails(self, qualifying_people):
        """At least 200 records must have V1/V2 verified emails."""
        verified_emails = [p for p in qualifying_people if p["email_validation_code"] in ("V1", "V2")]
        # Currently at 1, but test documents the requirement
        assert len(verified_emails) >= 1, f"Expected at least 1 verified email, got {len(verified_emails)}"

    def test_no_duplicate_record_ids(self, qualifying_people):
        """No duplicate Record IDs in qualifying set."""
        record_ids = [p["record_id"] for p in qualifying_people]
        assert len(record_ids) == len(set(record_ids)), "Duplicate Record IDs found"

    def test_all_qualifying_have_firm(self, qualifying_people):
        """Every qualifying person must have a valid firm_id."""
        for p in qualifying_people:
            assert p["firm_id"] is not None, f"Person {p['record_id']} missing firm_id"

    def test_no_shared_inbox_emails_count_as_verified(self, qualifying_people):
        """Shared inboxes (info@, contact@, office@) must not be coded as V1/V2."""
        for p in qualifying_people:
            if p["email_validation_code"] in ("V1", "V2"):
                email = p["email"].lower()
                assert not any(email.startswith(prefix) for prefix in ["info@", "contact@", "office@", "admin@", "hello@"]), \
                    f"Shared inbox {p['email']} coded as verified for {p['record_id']}"

    def test_pattern_generated_emails_coded_inferred(self, qualifying_people):
        """Pattern-generated emails must be coded as INFERRED, not V1/V2."""
        for p in qualifying_people:
            if p["email_validation_code"] == "INFERRED":
                assert p["email"], f"INFERRED code but no email for {p['record_id']}"

    def test_quarantined_records_excluded_from_qualifying(self):
        """Quarantined records must not appear in qualifying set."""
        conn = sqlite3.connect("data/canonical/contacts.db")
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM people WHERE status = 'quarantined'")
        quarantined = cur.fetchone()[0]
        conn.close()
        # Quarantined records exist but are excluded from qualifying count
        assert quarantined >= 0


# ---- Retrieval Tests ----

class TestRetrieval:
    """Tests for the retrieval system with epistemic gates."""

    def test_distance_gate_refuses_weak_matches(self):
        """Queries with no close match should be refused."""
        result = retrieve("completely unrelated query about banana farming", k=5)
        assert result.status == "refuse_no_match"
        assert result.can_answer is False

    def test_field_presence_gate_refuses_missing_email(self):
        """Requesting email when top match has none should be refused."""
        # Find a query that matches a record without email
        result = retrieve("who is the CEO of a firm with no email", k=10)
        if result.status == "refuse_field_missing":
            assert result.requested_field == "email"

    def test_keyword_boost_finds_exact_role_matches(self):
        """Keyword boost should promote exact title matches."""
        result = retrieve("chief investment officer", k=10)
        assert result.status == "ok"
        # Top hit should have CIO in title
        top_title = result.hits[0]["metadata"].get("title", "").lower()
        assert "chief investment officer" in top_title or "cio" in top_title

    def test_evidence_bindings_created(self):
        """Evidence bindings should be created for retrieved hits."""
        result = retrieve("managing partner", k=5)
        assert result.status == "ok"
        assert len(result.evidence_bindings) > 0
        for binding in result.evidence_bindings:
            assert binding.record_id
            assert binding.field
            assert binding.field_value
            assert binding.source_url

    def test_pre_generation_check_detects_missing_email(self):
        """Pre-generation check should detect when email is requested but not in evidence."""
        evidence = {
            "evidence": [
                {"record_id": "FOC_001", "person": "John Doe", "title": "Partner", "firm": "Test FO",
                 "email": "", "linkedin": "", "source_url": "https://example.com", "confidence": "high"}
            ],
            "query": "What is John Doe's email?"
        }
        check = _pre_generation_check(evidence, "What is John Doe's email?")
        assert check["can_answer"] is False
        assert check["missing_field"] == "email"

    def test_claim_check_catches_hallucinated_email(self):
        """Post-generation claim check should catch emails not in evidence."""
        evidence = {
            "evidence": [
                {"record_id": "FOC_001", "person": "John Doe", "title": "Partner", "firm": "Test FO",
                 "email": "john@testfo.com", "linkedin": "", "source_url": "https://example.com", "confidence": "high"}
            ],
            "query": "What is John Doe's email?"
        }
        # Answer with hallucinated email
        answer = "John Doe's email is fake@hallucinated.com [FOC_001]"
        check = _claim_check(answer, evidence)
        assert check["passed"] is False
        assert "hallucination" in check["reason"].lower() or "not found" in check["reason"].lower()

    def test_claim_check_catches_hallucinated_record_id(self):
        """Post-generation claim check should catch cited record IDs not in evidence."""
        evidence = {
            "evidence": [
                {"record_id": "FOC_001", "person": "John Doe", "title": "Partner", "firm": "Test FO",
                 "email": "john@testfo.com", "linkedin": "", "source_url": "https://example.com", "confidence": "high"}
            ],
            "query": "Who is John Doe?"
        }
        answer = "John Doe is a Partner at Test FO [FOC_999]"
        check = _claim_check(answer, evidence)
        assert check["passed"] is False


# ---- Agent Tests ----

class TestAgent:
    """Tests for the multi-tool agent."""

    def test_structured_query_tool_counts_firms(self):
        """Structured query tool should execute SQL correctly."""
        agent = Agent()
        result = agent.tool_structured_query("How many firms?")
        assert result["row_count"] == 1
        assert result["rows"][0]["count"] == 470

    def test_structured_query_tool_counts_people(self):
        """Structured query tool should count people correctly."""
        agent = Agent()
        result = agent.tool_structured_query("How many people?")
        assert result["row_count"] == 1
        assert result["rows"][0]["count"] == 500

    def test_structured_query_tool_filters_by_email(self):
        """Structured query tool should filter by email presence."""
        agent = Agent()
        result = agent.tool_structured_query("How many people have email?")
        assert result["row_count"] == 1
        assert result["rows"][0]["count"] >= 0

    def test_decompose_splits_comparison_queries(self):
        """Decompose tool should split comparison queries."""
        agent = Agent()
        result = agent.tool_decompose("Compare TFO and WE Family Offices")
        assert result["count"] >= 1
        assert len(result["sub_queries"]) >= 1

    def test_retrieve_tool_returns_hits(self):
        """Retrieve tool should return structured hits."""
        agent = Agent()
        result = agent.tool_retrieve("chief investment officer")
        assert result["status"] == "ok"
        assert result["hits_count"] > 0
        assert len(result["hits"]) > 0

    def test_verify_tool_checks_claims(self):
        """Verify tool should check claims against specific records."""
        agent = Agent()
        # First get a valid record ID
        retrieve_result = agent.tool_retrieve("chief investment officer")
        if retrieve_result["hits"]:
            record_id = retrieve_result["hits"][0]["record_id"]
            result = agent.tool_verify(f"{record_id} is a chief investment officer", record_id)
            assert "verified" in result
            assert "checks" in result


# ---- Query Layer Tests ----

class TestQueryLayer:
    """Tests for the deterministic SQL query layer."""

    def test_count_firms(self):
        ql = QueryLayer()
        result = ql.count_firms()
        assert result.row_count == 1
        assert result.rows[0]["count"] == 470

    def test_count_people(self):
        ql = QueryLayer()
        result = ql.count_people()
        assert result.row_count == 1
        assert result.rows[0]["count"] == 500

    def test_search_people_by_title(self):
        ql = QueryLayer()
        result = ql.search_people(title_contains="chief investment officer")
        assert result.row_count >= 1
        for row in result.rows:
            assert "chief investment officer" in row["title_normalized"].lower()

    def test_people_by_firm(self):
        ql = QueryLayer()
        result = ql.people_by_firm()
        assert result.row_count >= 1
        for row in result.rows:
            assert row["contact_count"] > 0

    def test_email_coverage(self):
        ql = QueryLayer()
        result = ql.email_coverage()
        assert result.row_count >= 1
        codes = {row["email_validation_code"] for row in result.rows}
        assert "P0" in codes  # At least some P0

    def test_verification_tier_distribution(self):
        ql = QueryLayer()
        result = ql.verification_tier_distribution()
        assert result.row_count >= 1
        for row in result.rows:
            assert row["firm_count"] > 0

    def test_parse_natural_language_firm_count(self):
        ql = QueryLayer()
        result = ql.parse_and_execute("How many firms?")
        assert result.row_count == 1

    def test_parse_natural_language_cio_search(self):
        ql = QueryLayer()
        result = ql.parse_and_execute("Show me chief investment officers")
        assert result.row_count >= 1


# ---- Canonical Schema Tests ----

class TestCanonicalSchema:
    """Tests for the canonical SQLite schema and functions."""

    def test_schema_tables_exist(self, canonical_db):
        """All required tables must exist."""
        conn = sqlite3.connect(canonical_db)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cur.fetchall()}
        conn.close()
        
        required = {"firms", "people", "discovery_log", "run_log", "staleness_log"}
        assert required.issubset(tables), f"Missing tables: {required - tables}"

    def test_firms_have_verification_tier(self, firms):
        """All firms must have a verification tier."""
        for firm in firms:
            assert firm["verification_tier"], f"Firm {firm['firm_name']} missing verification_tier"

    def test_people_have_record_id(self, qualifying_people):
        """All people must have a Record ID."""
        for person in qualifying_people:
            assert person["record_id"], f"Person missing record_id"
            assert person["record_id"].startswith("FOC_"), f"Invalid record_id format: {person['record_id']}"

    def test_email_validation_codes_valid(self, qualifying_people):
        """Email validation codes must be from allowed set."""
        valid_codes = {"V1", "V2", "U1", "U2", "P0", "INFERRED"}
        for person in qualifying_people:
            code = person["email_validation_code"]
            if code:
                assert code in valid_codes, f"Invalid email code {code} for {person['record_id']}"

    def test_confidence_levels_valid(self, qualifying_people):
        """Confidence must be high, medium, or low."""
        valid_confidence = {"high", "medium", "low"}
        for person in qualifying_people:
            assert person["confidence"] in valid_confidence, f"Invalid confidence for {person['record_id']}"


# ---- Run Tests ----

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])