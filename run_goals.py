# run_goals.py
# Execute the 3 goals and capture raw logs for submission

import json
import pathlib
from datetime import datetime, timezone
from rag.agent import run_agent

GOALS = [
    {
        "id": "goal_1",
        "description": "Multi-step commercial search",
        "query": "Identify family offices with healthcare investment mandates and provide the named CIO with verified contact route for each."
    },
    {
        "id": "goal_2",
        "description": "Uncertain-data case (verbatim from brief)",
        "query": "Identify the family offices in the dataset that are the best fit for a lower-middle-market healthcare services fund seeking limited partners, and tell me how confident you are in each."
    },
    {
        "id": "goal_3",
        "description": "Buyer challenge - secondaries fundraise",
        "query": "I'm raising a Fund II for a Southeast US-based secondaries specialist. Which family offices in the dataset have allocated to secondaries funds before, and who is the right person to approach?"
    }
]

OUT_DIR = pathlib.Path("data/submission/goals")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def run_goal(goal):
    print(f"\n{'='*60}")
    print(f"GOAL: {goal['description']}")
    print(f"QUERY: {goal['query']}")
    print(f"{'='*60}")
    
    result = run_agent(goal['query'])
    
    # Capture raw log
    raw_log = {
        "goal_id": goal["id"],
        "goal_description": goal["description"],
        "query": goal["query"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_result": result
    }
    
    # Save raw log
    log_path = OUT_DIR / f"{goal['id']}_raw_log.json"
    with log_path.open("w") as f:
        json.dump(raw_log, f, indent=2, default=str)
    
    # Save structured output
    output_path = OUT_DIR / f"{goal['id']}_output.json"
    with output_path.open("w") as f:
        json.dump({
            "goal_id": goal["id"],
            "query": goal["query"],
            "final_answer": result["final_answer"],
            "citations": result["citations"],
            "evidence_summary": result["evidence_summary"],
            "claim_check_passed": result["claim_check_passed"],
            "refused": result["refused"],
            "steps": result["steps"]
        }, f, indent=2, default=str)
    
    print(f"Final Answer:\n{result['final_answer']}")
    print(f"\nCitations: {result['citations']}")
    print(f"Claim Check: {'PASSED' if result['claim_check_passed'] else 'FAILED'}")
    print(f"Refused: {result['refused']}")
    print(f"Steps: {len(result['steps'])}")
    
    return result

if __name__ == "__main__":
    print("Running 3 Goals for Submission...")
    print(f"Output directory: {OUT_DIR}")
    
    all_results = {}
    for goal in GOALS:
        all_results[goal["id"]] = run_goal(goal)
    
    # Save combined summary
    summary_path = OUT_DIR / "goals_summary.json"
    with summary_path.open("w") as f:
        json.dump({
            "run_timestamp": datetime.now(timezone.utc).isoformat(),
            "goals": {
                goal["id"]: {
                    "description": goal["description"],
                    "query": goal["query"],
                    "claim_check_passed": all_results[goal["id"]]["claim_check_passed"],
                    "refused": all_results[goal["id"]]["refused"],
                    "citations_count": len(all_results[goal["id"]]["citations"]),
                    "steps_count": len(all_results[goal["id"]]["steps"])
                }
                for goal in GOALS
            }
        }, f, indent=2)
    
    print(f"\n{'='*60}")
    print("ALL GOALS COMPLETE")
    print(f"Logs saved to: {OUT_DIR}")
    print(f"Summary: {summary_path}")