# rag/generator_v2.py
# Generator with Pre-Generation Claim Check + Evidence Binding
# LAYER 3 (pre): Check that query can be answered from evidence BEFORE calling LLM
# LAYER 4 (post): Verify generated answer only makes claims present in evidence

import os
import re
import json
import sys
import pathlib
from dotenv import load_dotenv
from groq import Groq

# Make pipeline/ importable
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

load_dotenv()

_client = None

def _get_client():
    global _client
    if _client is None:
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY not set. Add it to your .env file.")
        _client = Groq(api_key=key)
    return _client


SYSTEM_PROMPT = """You are a strict, factual assistant answering questions about a curated family-office contacts dataset.

RULES YOU MUST FOLLOW:
1. Only state facts that appear verbatim or by clear paraphrase in the provided EVIDENCE block. Do not add outside knowledge.
2. If the EVIDENCE does not contain what the user asked, say so plainly. Do not guess. Do not fabricate names, titles, emails, or firms.
3. Cite the record IDs (e.g., FOC_001) that support each claim.
4. Keep answers concise: at most 4 sentences plus citations.
5. Never invent an email address, phone number, or LinkedIn URL. If a requested contact field is not in the EVIDENCE, say the dataset does not contain it.
6. Use the exact field values from evidence. Do not modify, complete, or infer.
7. If evidence is insufficient, state: "The dataset does not contain sufficient evidence to answer this question."
"""


def _format_evidence(evidence_dict: dict) -> str:
    """Format evidence for LLM with explicit source attribution."""
    lines = []
    for item in evidence_dict["evidence"]:
        line = f"[{item['record_id']}] {item['person']} — {item['title']} at {item['firm']}"
        if item['email']:
            line += f" | Email: {item['email']}"
        else:
            line += " | Email: (not in dataset)"
        if item['linkedin']:
            line += f" | LinkedIn: {item['linkedin']}"
        line += f" | Confidence: {item['confidence']} | Source: {item['source_url']}"
        lines.append(line)
    return "\n".join(lines)


def _pre_generation_check(evidence_dict: dict, query: str) -> dict:
    """
    LAYER 3: Pre-generation claim check.
    Verify the evidence contains what's needed to answer the query.
    """
    q_low = query.lower()
    evidence = evidence_dict["evidence"]
    
    # Check for email requests
    if any(w in q_low for w in ["email", "e-mail", "contact", "reach"]):
        has_email = any(e.get("email") for e in evidence)
        if not has_email:
            return {
                "can_answer": False,
                "reason": "No email addresses found in the retrieved evidence for the matching records.",
                "missing_field": "email",
            }
    
    # Check for LinkedIn requests
    if any(w in q_low for w in ["linkedin", "profile"]):
        has_li = any(e.get("linkedin") for e in evidence)
        if not has_li:
            return {
                "can_answer": False,
                "reason": "No LinkedIn profiles found in the retrieved evidence for the matching records.",
                "missing_field": "linkedin",
            }
    
    # Check for phone requests
    if any(w in q_low for w in ["phone", "call", "number"]):
        return {
            "can_answer": False,
            "reason": "Phone numbers are not stored in this dataset.",
            "missing_field": "phone",
        }
    
    # Check for specific role requests
    role_phrases = [
        "chief investment officer", "chief financial officer",
        "chief executive officer", "chief operating officer",
        "managing partner", "managing director",
        "portfolio manager", "founder", "president", "partner",
    ]
    for role in role_phrases:
        if role in q_low:
            has_role = any(role in e.get("title", "").lower() for e in evidence)
            if not has_role:
                return {
                    "can_answer": False,
                    "reason": f"No records with title containing '{role}' found in the evidence.",
                    "missing_field": "title",
                }
    
    return {"can_answer": True, "reason": "Evidence appears sufficient for query"}


def _claim_check(answer: str, evidence_dict: dict) -> dict:
    """
    LAYER 4: Post-generation claim check.
    Verify that any email, person name, or specific claim in answer appears in evidence.
    """
    evidence_text = " ".join(
        f"{e['person']} {e['title']} {e['firm']} {e.get('email','')} {e.get('linkedin','')}"
        for e in evidence_dict["evidence"]
    ).lower()
    
    evidence_record_ids = {e["record_id"] for e in evidence_dict["evidence"]}
    
    # Check emails in answer
    answer_emails = re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", answer)
    for em in answer_emails:
        if em.lower() not in evidence_text:
            return {
                "passed": False,
                "reason": f"Answer contains email '{em}' not found in retrieved evidence. Possible hallucination.",
                "violations": [f"email:{em}"],
            }
    
    # Check cited record IDs are actually in evidence
    cited_ids = re.findall(r"FOC_\d{3}", answer)
    for cid in cited_ids:
        if cid not in evidence_record_ids:
            return {
                "passed": False,
                "reason": f"Answer cites record ID '{cid}' not present in retrieved evidence.",
                "violations": [f"record_id:{cid}"],
            }
    
    # Check for fabricated names (names in answer not in evidence)
    # Extract capitalized name-like patterns from answer
    answer_names = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b", answer)
    evidence_names = set()
    for e in evidence_dict["evidence"]:
        evidence_names.add(e["person"].lower())
        # Also add first+last
        parts = e["person"].split()
        if len(parts) >= 2:
            evidence_names.add(f"{parts[0]} {parts[-1]}".lower())
    
    for name in answer_names:
        if name.lower() not in evidence_names and len(name) > 5:
            # Could be a firm name, check that too
            evidence_firms = {e["firm"].lower() for e in evidence_dict["evidence"]}
            if name.lower() not in evidence_firms:
                return {
                    "passed": False,
                    "reason": f"Answer contains name '{name}' not found in retrieved evidence.",
                    "violations": [f"name:{name}"],
                }
    
    return {"passed": True, "reason": "No unsupported factual claims detected.", "violations": []}


def generate_answer(query: str, evidence_dict: dict, model: str = "llama-3.1-8b-instant") -> dict:
    """
    Generate a grounded answer with pre- and post-generation claim checks.
    Returns {answer, cited_ids, claim_check, pre_check, evidence_used}.
    """
    # LAYER 3: Pre-generation check
    pre_check = _pre_generation_check(evidence_dict, query)
    
    if not pre_check["can_answer"]:
        return {
            "answer": f"The dataset does not contain sufficient evidence to answer this question. {pre_check['reason']}",
            "cited_ids": [],
            "raw_llm_output": "",
            "claim_check": {"passed": True, "reason": "No generation attempted - insufficient evidence"},
            "pre_check": pre_check,
            "evidence_used": evidence_dict,
        }
    
    evidence = _format_evidence(evidence_dict)
    user_msg = (
        f"USER QUESTION:\n{query}\n\n"
        f"EVIDENCE (only facts you may use):\n{evidence}\n\n"
        f"Answer the question using ONLY the evidence above. "
        f"Cite record IDs in square brackets. If the evidence is insufficient, say so."
    )
    
    try:
        resp = _get_client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
            max_tokens=400,
        )
        raw = resp.choices[0].message.content.strip()
    except Exception as e:
        return {
            "answer": f"[LLM error: {type(e).__name__}. Showing raw evidence instead.]\n\n{evidence}",
            "cited_ids": [],
            "raw_llm_output": "",
            "claim_check": {"passed": False, "reason": f"LLM call failed: {e}"},
            "pre_check": pre_check,
            "evidence_used": evidence_dict,
        }
    
    # LAYER 4: Post-generation claim check
    claim_check = _claim_check(raw, evidence_dict)
    
    # Extract cited IDs
    cited = list(set(re.findall(r"FOC_\d{3}", raw)))
    
    return {
        "answer": raw,
        "cited_ids": cited,
        "raw_llm_output": raw,
        "claim_check": claim_check,
        "pre_check": pre_check,
        "evidence_used": evidence_dict,
    }


def generate_refusal(reason: str, evidence_dict: dict = None) -> dict:
    """Generate a structured refusal response."""
    return {
        "answer": f"I cannot answer this question from the dataset. {reason}",
        "cited_ids": [],
        "raw_llm_output": "",
        "claim_check": {"passed": True, "reason": "Refusal - no generation attempted"},
        "pre_check": {"can_answer": False, "reason": reason},
        "evidence_used": evidence_dict or {"evidence": [], "query": ""},
    }


if __name__ == "__main__":
    from retriever_v2 import retrieve, get_evidence_for_generation
    
    q = "Who is the chief investment officer at TFO Family Office Partners?"
    print(f"> {q}\n")
    r = retrieve(q, k=5)
    print(f"Retrieval status: {r.status}")
    print(f"Can answer: {r.can_answer}")
    
    if r.status == "ok":
        evidence = get_evidence_for_generation(r.hits, q)
        ans = generate_answer(q, evidence)
        print(f"\nANSWER:\n{ans['answer']}")
        print(f"\nCited: {ans['cited_ids']}")
        print(f"Pre-check: {ans['pre_check']}")
        print(f"Claim check: {ans['claim_check']}")
    else:
        print(f"Reason: {r.reason}")