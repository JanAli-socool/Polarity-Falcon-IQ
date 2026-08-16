# run_goals_v2.py
# Execute the 3 goals with queries matching actual dataset content
# Also capture manual retrieval outputs for comparison

import json
import pathlib
from datetime import datetime, timezone
from rag.agent import run_agent
from rag.retriever_v2 import retrieve, get_evidence_for_generation
from rag.generator_v2 import generate_answer

GOALS = [
    {
        "id": "goal_1",
        "description": "Multi-step commercial search",
        "query": "Who are the chief investment officers at TFO Family Office Partners and Omnia Family Wealth?",
        "manual_query": "chief investment officer TFO Omnia"
    },
    {
        "id": "goal_2",
        "description": "Uncertain-data case (verbatim from brief)",
        "query": "Identify the family offices in the dataset that are the best fit for a lower-middle-market healthcare services fund seeking limited partners, and tell me how confident you are in each.",
        "manual_query": "healthcare lower middle market fund limited partners"
    },
    {
        "id": "goal_3",
        "description": "Buyer challenge - secondaries fundraise",
        "query": "Which family offices have team members with direct investment or co-investment experience, and who should I contact?",
        "manual_query": "direct investment co-investment secondaries"
    }
]

OUT_DIR = pathlib.Path("data/submission/goals_v2")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def run_manual_retrieval(query):
    """Run single retrieval + generation for comparison."""
    r = retrieve(query, k=10)
    if r.status != "ok" or not r.can_answer:
        return {
            "status": r.status,
            "reason": r.reason,
            "answer": f"Cannot answer: {r.reason}",
            "citations": [],
            "evidence_used": {"evidence": []},
            "claim_check": {"passed": True, "reason": "No generation - refused"}
        }
    
    evidence = get_evidence_for_generation(r.hits, query)
    gen = generate_answer(query, evidence)
    return {
        "status": "ok",
        "answer": gen["answer"],
        "citations": gen["cited_ids"],
        "evidence_used": evidence,
        "claim_check": gen["claim_check"],
        "pre_check": gen["pre_check"]
    }

def run_goal(goal):
    print(f"\n{'='*60}")
    print(f"GOAL: {goal['description']}")
    print(f"QUERY: {goal['query']}")
    print(f"{'='*60}")
    
    # Agent run
    agent_result = run_agent(goal['query'])
    
    # Manual retrieval for comparison
    manual_result = run_manual_retrieval(goal['manual_query'])
    
    raw_log = {
        "goal_id": goal["id"],
        "goal_description": goal["description"],
        "agent_query": goal["query"],
        "manual_query": goal["manual_query"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_result": agent_result,
        "manual_retrieval_result": manual_result
    }
    
    log_path = OUT_DIR / f"{goal['id']}_raw_log.json"
    with log_path.open("w") as f:
        json.dump(raw_log, f, indent=2, default=str)
    
    output_path = OUT_DIR / f"{goal['id']}_output.json"
    with output_path.open("w") as f:
        json.dump({
            "goal_id": goal["id"],
            "agent_query": goal["query"],
            "manual_query": goal["manual_query"],
            "agent_answer": agent_result["final_answer"],
            "manual_answer": manual_result["answer"],
            "agent_citations": agent_result["citations"],
            "manual_citations": manual_result.get("citations", []),
            "agent_claim_check": agent_result["claim_check_passed"],
            "manual_claim_check": manual_result.get("claim_check", {}).get("passed", False),
            "agent_refused": agent_result["refused"],
            "agent_steps": agent_result["steps"]
        }, f, indent=2, default=str)
    
    print(f"AGENT ANSWER:\n{agent_result['final_answer']}")
    print(f"\nMANUAL ANSWER:\n{manual_result['answer']}")
    print(f"\nAgent Citations: {agent_result['citations']}")
    print(f"Manual Citations: {manual_result.get('citations', [])}")
    print(f"Agent Claim Check: {'PASSED' if agent_result['claim_check_passed'] else 'FAILED'}")
    print(f"Manual Claim Check: {'PASSED' if manual_result.get('claim_check', {}).get('passed', False) else 'FAILED'}")
    
    return {"agent": agent_result, "manual": manual_result}

if __name__ == "__main__":
    print("Running 3 Goals for Submission (v2 - dataset-matched queries)...")
    print(f"Output directory: {OUT_DIR}")
    
    all_results = {}
    for goal in GOALS:
        all_results[goal["id"]] = run_goal(goal)
    
    summary_path = OUT_DIR / "goals_summary.json"
    with summary_path.open("w") as f:
        json.dump({
            "run_timestamp": datetime.now(timezone.utc).isoformat(),
            "goals": {
                goal["id"]: {
                    "description": goal["description"],
                    "agent_query": goal["query"],
                    "manual_query": goal["manual_query"],
                    "agent_claim_check": all_results[goal["id"]]["agent"]["claim_check_passed"],
                    "agent_refused": all_results[goal["id"]]["agent"]["refused"],
                    "manual_claim_check": all_results[goal["id"]]["manual"].get("claim_check", {}).get("passed", False),
                }
                for goal in GOALS
            }
        }, f, indent=2)
    
    print(f"\n{'='*60}")
    print("ALL GOALS COMPLETE")
    print(f"Logs saved to: {OUT_DIR}")
    print(f"Summary: {summary_path}")