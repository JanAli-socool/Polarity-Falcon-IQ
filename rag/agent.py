# rag/agent.py
# Agent with Tools: retrieve, verify, structured_query, decompose
# Implements a tool-using agent for multi-step commercial search

import json
import re
import sys
import pathlib
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum

# Make rag/ importable
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from retriever_v2 import retrieve, get_evidence_for_generation
from generator_v2 import generate_answer, generate_refusal
from pipeline.query_layer import QueryLayer


class ToolName(Enum):
    RETRIEVE = "retrieve"
    VERIFY = "verify"
    STRUCTURED_QUERY = "structured_query"
    DECOMPOSE = "decompose"


@dataclass
class ToolCall:
    tool: ToolName
    args: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class AgentStep:
    step_number: int
    thought: str
    tool_call: Optional[ToolCall] = None
    observation: Optional[str] = None


@dataclass
class AgentResult:
    query: str
    steps: List[AgentStep]
    final_answer: str
    citations: List[str]
    evidence_summary: Dict[str, Any]
    claim_check_passed: bool
    refused: bool


class Agent:
    """
    Agent for multi-step commercial search over family office dataset.
    Tools:
    - retrieve: Semantic search with epistemic gates
    - verify: Check specific claims against evidence
    - structured_query: Deterministic SQL queries for counts/filters
    - decompose: Break complex queries into sub-queries
    """
    
    def __init__(self):
        self.query_layer = QueryLayer()
        self.step_counter = 0
        self.steps: List[AgentStep] = []
    
    def _add_step(self, thought: str, tool_call: ToolCall = None, observation: str = None):
        self.step_counter += 1
        self.steps.append(AgentStep(
            step_number=self.step_counter,
            thought=thought,
            tool_call=tool_call,
            observation=observation,
        ))
    
    def tool_retrieve(self, query: str, k: int = 10) -> Dict[str, Any]:
        """Tool: Semantic retrieval with epistemic gates."""
        result = retrieve(query, k)
        return {
            "status": result.status,
            "reason": result.reason,
            "hits_count": len(result.hits),
            "top_distance": result.top_distance,
            "requested_field": result.requested_field,
            "can_answer": result.can_answer,
            "hits": [
                {
                    "record_id": h["metadata"]["record_id"],
                    "person": h["metadata"]["person"],
                    "title": h["metadata"].get("title", ""),
                    "firm": h["metadata"]["firm"],
                    "email": h["metadata"].get("email", ""),
                    "linkedin": h["metadata"].get("linkedin", ""),
                    "confidence": h["metadata"].get("confidence", "low"),
                    "source_url": h["metadata"].get("source_url", ""),
                    "distance": round(h["distance"], 3),
                }
                for h in result.hits[:5]
            ],
            "evidence_bindings": [
                {
                    "claim": b.claim,
                    "record_id": b.record_id,
                    "field": b.field,
                    "field_value": b.field_value,
                    "source_url": b.source_url,
                }
                for b in result.evidence_bindings
            ],
        }
    
    def tool_verify(self, claim: str, record_id: str) -> Dict[str, Any]:
        """Tool: Verify a specific claim against a specific record."""
        from pipeline.schema import get_conn
        
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT p.*, f.firm_name, f.verification_tier, f.official_url
            FROM people p
            JOIN firms f ON p.firm_id = f.firm_id
            WHERE p.record_id = ?
        """, (record_id,))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            return {"verified": False, "reason": f"Record {record_id} not found"}
        
        person = dict(row)
        claim_lower = claim.lower()
        
        # Check claim against record fields
        checks = {}
        
        if "email" in claim_lower:
            checks["email"] = {
                "claimed": claim,
                "actual": person["email"],
                "match": person["email"].lower() in claim_lower if person["email"] else False,
            }
        
        if "title" in claim_lower or "role" in claim_lower:
            checks["title"] = {
                "claimed": claim,
                "actual": person["job_title"],
                "match": any(w in person["job_title"].lower() for w in claim_lower.split() if len(w) > 3),
            }
        
        if "firm" in claim_lower or "company" in claim_lower:
            checks["firm"] = {
                "claimed": claim,
                "actual": person["firm_name"],
                "match": person["firm_name"].lower() in claim_lower,
            }
        
        all_match = all(c.get("match", True) for c in checks.values())
        
        return {
            "verified": all_match,
            "record_id": record_id,
            "person": person["full_name"],
            "checks": checks,
        }
    
    def tool_structured_query(self, question: str) -> Dict[str, Any]:
        """Tool: Execute deterministic SQL query for counts/filters/aggregates."""
        result = self.query_layer.parse_and_execute(question)
        return {
            "query_type": result.query_type.value if hasattr(result.query_type, 'value') else str(result.query_type),
            "sql": result.sql,
            "params": result.params,
            "row_count": result.row_count,
            "rows": result.rows[:20],  # Limit rows in response
            "explanation": result.explanation,
        }

    def tool_structured_query_with_filters(self, question: str, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Tool: Execute deterministic SQL query with explicit filters."""
        result = self.query_layer.execute_with_filters(question, filters)
        return {
            "query_type": result.query_type.value if hasattr(result.query_type, 'value') else str(result.query_type),
            "sql": result.sql,
            "params": result.params,
            "row_count": result.row_count,
            "rows": result.rows[:20],
            "explanation": result.explanation,
        }
    
    def tool_decompose(self, complex_query: str) -> Dict[str, Any]:
        """Tool: Decompose a complex multi-part query into structured sub-queries with filters."""
        q = complex_query.lower()
        sub_queries = []
        filters = {}
        
        # Extract firm names (quoted or capitalized phrases)
        firm_matches = re.findall(r'"([^"]+)"', complex_query)  # "TFO Family Office"
        if firm_matches:
            filters["firm_name"] = firm_matches[0]
        
        # Geography detection
        geo_terms = {
            "united states": "united states", "usa": "united states", "u.s.": "united states", "us": "united states",
            "canada": "canada", "uk": "united kingdom", "united kingdom": "united kingdom",
            "switzerland": "switzerland", "singapore": "singapore", "hong kong": "hong kong",
            "germany": "germany", "france": "france", "australia": "australia",
            "south africa": "south africa", "brazil": "brazil", "uae": "united arab emirates",
            "japan": "japan", "china": "china", "india": "india",
        }
        for geo, normalized in geo_terms.items():
            if geo in q:
                filters["country"] = normalized
                break
        
        # Sector detection
        sector_terms = {
            "healthcare": ["healthcare", "health care", "life sciences", "biotech", "pharma"],
            "technology": ["technology", "tech", "software", "digital", "ai", "artificial intelligence"],
            "financial_services": ["financial services", "fintech", "banking", "wealth management", "asset management"],
            "private_equity": ["private equity", "pe", "buyout", "venture capital", "vc"],
            "real_estate": ["real estate", "property", "reit"],
            "energy": ["energy", "oil", "gas", "renewable", "solar", "wind"],
            "industrials": ["industrials", "manufacturing", "industrial"],
            "consumer": ["consumer", "retail", "ecommerce", "brand"],
        }
        for sector, terms in sector_terms.items():
            if any(term in q for term in terms):
                terms.append(sector)
        
        # Role/title detection
        role_terms = {
            "investment_decision_maker": ["chief investment officer", "cio", "investment director", "portfolio manager", "investment manager"],
            "executive_decision_maker": ["chief executive officer", "ceo", "president", "chairman", "founder", "co-founder"],
            "partner_or_principal": ["managing partner", "general partner", "senior partner", "partner", "principal"],
            "capital_or_relationship_lead": ["head of capital", "head of relationships", "investor relations", "capital formation"],
        }
        for role_class, terms in role_terms.items():
            if any(term in q for term in terms):
                filters["role_class"] = role_class
                break
        
        # Email/LinkedIn filters
        if "email" in q:
            filters["has_email"] = True
        if "linkedin" in q:
            filters["route_type"] = "linkedin"
        
        # Trust state
        if "current" in q or "recent" in q:
            filters["trust_state"] = "supported_current"
        
        # Compound query patterns
        sub_queries = []
        if " vs " in q or " versus " in q or " compare " in q:
            parts = re.split(r"\s+(?:vs|versus|compare)\s+", q, flags=re.IGNORECASE)
            for part in parts:
                part = part.strip().replace(" and ", " ").strip()
                if part:
                    sub_queries.append(part.strip())
        
        elif " and " in q and ("how many" in q or "count" in q or "list" in q):
            parts = re.split(r"\s+and\s+", q)
            for part in parts:
                part = part.strip()
                if part:
                    sub_queries.append(part)
        
        elif " for " in q and ("show" in q or "list" in q or "find" in q):
            parts = re.split(r"\s+for\s+", q, flags=re.IGNORECASE)
            if len(parts) >= 2:
                sub_queries.append(parts[0].strip())
                sub_queries.append(f"for {parts[1].strip()}")
        
        # Default: single query
        if not sub_queries:
            sub_queries = [complex_query]
        
        return {
            "original_query": complex_query,
            "sub_queries": sub_queries,
            "filters": filters,
            "count": len(sub_queries),
        }
    
    def run(self, query: str) -> AgentResult:
        """Run the agent on a query."""
        self.step_counter = 0
        self.steps = []
        
        self._add_step(f"Received query: {query}")
        
        # Step 1: Check if decomposition needed
        decompose_result = self.tool_decompose(query)
        self._add_step(
            f"Decomposed query into {decompose_result['count']} sub-queries",
            ToolCall(ToolName.DECOMPOSE, {"query": query}, decompose_result),
            f"Sub-queries: {decompose_result['sub_queries']}"
        )
        
        all_evidence = []
        all_citations = []
        sub_answers = []
        
        # Process each sub-query
        for i, sub_q in enumerate(decompose_result["sub_queries"]):
            self._add_step(f"Processing sub-query {i+1}/{len(decompose_result['sub_queries'])}: {sub_q}")
            
            # Try structured query first for count/filter questions
            if any(kw in sub_q.lower() for kw in ["how many", "count", "number of", "list all", "show all"]):
                sq_result = self.tool_structured_query(sub_q)
                self._add_step(
                    "Executed structured query",
                    ToolCall(ToolName.STRUCTURED_QUERY, {"question": sub_q}, sq_result),
                    f"Returned {sq_result['row_count']} rows"
                )
                
                # Format structured result as answer
                if sq_result["row_count"] > 0:
                    answer_parts = []
                    for row in sq_result["rows"][:10]:
                        answer_parts.append(str(row))
                    sub_answers.append(f"Structured query result: {'; '.join(answer_parts)}")
                else:
                    sub_answers.append("Structured query returned no results.")
                continue
            
            # Use structured query with filters if filters are present
            sub_q_filters = decompose_result.get("filters", {})
            if sub_q_filters:
                # Build structured query with filters
                sq_filters = {}
                for k, v in sub_q_filters.items():
                    if k in ["firm_name", "country", "firm_type", "role_class", "route_type", "has_email", 
                            "intelligence_kind", "intelligence_term", "source_class", "trust_state"]:
                        sq_filters[k] = v
                
                sq_result = self.tool_structured_query_with_filters(sub_q, sq_filters)
                self._add_step(
                    f"Executed structured query with filters: {sq_filters}",
                    ToolCall(ToolName.STRUCTURED_QUERY, {"question": sub_q, "filters": sq_filters}, sq_result),
                    f"Returned {sq_result['row_count']} rows"
                )
                
                if sq_result["row_count"] > 0:
                    answer_parts = []
                    for row in sq_result["rows"][:10]:
                        answer_parts.append(str(row))
                    sub_answers.append(f"Structured query result: {'; '.join(answer_parts)}")
                else:
                    sub_answers.append("Structured query returned no results.")
                continue
            
            # Otherwise use semantic retrieval
            retrieve_result = self.tool_retrieve(sub_q, k=10)
            
            if retrieve_result["status"] != "ok" or not retrieve_result["can_answer"]:
                sub_answers.append(f"Could not answer: {retrieve_result['reason']}")
                continue
            
            # Generate answer from evidence
            evidence = get_evidence_for_generation(
                [{"metadata": h, "distance": h["distance"]} for h in retrieve_result["hits"]],
                sub_q
            )
            
            gen_result = generate_answer(sub_q, evidence)
            
            self._add_step(
                "Generated answer from evidence",
                None,
                f"Claim check: {'PASSED' if gen_result['claim_check']['passed'] else 'FAILED'}"
            )
            
            if not gen_result["claim_check"]["passed"]:
                self._add_step(
                    "Claim check failed - refusing answer",
                    None,
                    f"Reason: {gen_result['claim_check']['reason']}"
                )
                sub_answers.append(f"[Refused] {gen_result['claim_check']['reason']}")
            else:
                sub_answers.append(gen_result["answer"])
                all_citations.extend(gen_result["cited_ids"])
                all_evidence.extend(evidence["evidence"])
        
        # Combine sub-answers
        if len(sub_answers) == 1:
            final_answer = sub_answers[0]
        else:
            final_answer = "Combined results:\n" + "\n\n".join(
                f"**{decompose_result['sub_queries'][i]}**\n{ans}"
                for i, ans in enumerate(sub_answers)
            )
        
        # Deduplicate citations
        unique_citations = list(dict.fromkeys(all_citations))
        
        return AgentResult(
            query=query,
            steps=self.steps,
            final_answer=final_answer,
            citations=unique_citations,
            evidence_summary={
                "total_evidence_items": len(all_evidence),
                "unique_firms": len(set(e["firm"] for e in all_evidence)),
                "unique_people": len(set(e["person"] for e in all_evidence)),
            },
            claim_check_passed=all(
                "Refused" not in ans for ans in sub_answers
            ),
            refused=any("Refused" in ans for ans in sub_answers),
        )


def run_agent(query: str) -> Dict[str, Any]:
    """Convenience function to run agent and return dict."""
    agent = Agent()
    result = agent.run(query)
    return {
        "query": result.query,
        "steps": [
            {
                "step": s.step_number,
                "thought": s.thought,
                "tool": s.tool_call.tool.value if s.tool_call else None,
                "tool_args": s.tool_call.args if s.tool_call else None,
                "tool_result": s.tool_call.result if s.tool_call else None,
                "observation": s.observation,
            }
            for s in result.steps
        ],
        "final_answer": result.final_answer,
        "citations": result.citations,
        "evidence_summary": result.evidence_summary,
        "claim_check_passed": result.claim_check_passed,
        "refused": result.refused,
    }


if __name__ == "__main__":
    # Test queries
    test_queries = [
        "Who is the chief investment officer at TFO Family Office Partners?",
        "How many firms are in the dataset?",
        "List all managing partners and their firms",
        "Compare TFO Family Office Partners and WE Family Offices",
    ]
    
    for q in test_queries:
        print(f"\n{'='*60}")
        print(f"QUERY: {q}")
        print(f"{'='*60}")
        result = run_agent(q)
        print(f"\nFINAL ANSWER:\n{result['final_answer']}")
        print(f"\nCitations: {result['citations']}")
        print(f"Claim check passed: {result['claim_check_passed']}")
        print(f"Refused: {result['refused']}")
        print(f"\nSteps:")
        for step in result["steps"]:
            print(f"  {step['step']}. {step['thought']}")
            if step["tool"]:
                print(f"     Tool: {step['tool']} -> {step['observation']}")