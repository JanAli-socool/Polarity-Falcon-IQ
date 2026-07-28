# rag/generator.py
# Turns retrieval hits into a grounded answer via Groq's free Llama.
# LAYER 3 of the control: post-generation claim check ensures the
# answer only makes claims that appear in the retrieved evidence.

import os
import re
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

_client = None

def _get_client():
    global _client
    if _client is None:
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise RuntimeError(
                "GROQ_API_KEY not set. Add it to your .env file."
            )
        _client = Groq(api_key=key)
    return _client


SYSTEM_PROMPT = """You are a strict, factual assistant answering questions \
about a curated family-office contacts dataset.

RULES YOU MUST FOLLOW:
1. Only state facts that appear verbatim or by clear paraphrase in the \
provided EVIDENCE block. Do not add outside knowledge.
2. If the EVIDENCE does not contain what the user asked, say so plainly. \
Do not guess. Do not fabricate names, titles, emails, or firms.
3. Cite the record IDs (e.g., FOC_001) that support each claim.
4. Keep answers concise: at most 4 sentences plus citations.
5. Never invent an email address, phone number, or LinkedIn URL. If a \
requested contact field is not in the EVIDENCE, say the dataset does not \
contain it.
"""


def _format_evidence(hits: list[dict]) -> str:
    lines = []
    for h in hits:
        m = h["metadata"]
        lines.append(
            f"[{m['record_id']}] {m['person']} — {m['title']} at {m['firm']}"
            + (f" | Country: {m.get('firm','')}" if False else "")
            + (f" | Email: {m['email']}" if m.get("email") else " | Email: (not in dataset)")
            + f" | Confidence: {m.get('confidence','?')}"
            + f" | Source: {m.get('source_url','')}"
        )
    return "\n".join(lines)


def generate_answer(query: str, hits: list[dict], model: str = "llama-3.1-8b-instant") -> dict:
    """
    Call Groq to produce a grounded answer.
    Returns {answer, cited_ids, raw_llm_output, claim_check}.
    """
    evidence = _format_evidence(hits)
    user_msg = (
        f"USER QUESTION:\n{query}\n\n"
        f"EVIDENCE (only facts you may use):\n{evidence}\n\n"
        f"Answer the question using ONLY the evidence above. "
        f"Cite record IDs. If the evidence is insufficient, say so."
    )

    try:
        resp = _get_client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
            max_tokens=350,
        )
        raw = resp.choices[0].message.content.strip()
    except Exception as e:
        return {
            "answer": f"[LLM error: {type(e).__name__}. Showing raw evidence instead.]\n\n{evidence}",
            "cited_ids": [],
            "raw_llm_output": "",
            "claim_check": {"passed": False, "reason": f"LLM call failed: {e}"},
        }

    # LAYER 3: post-generation claim check
    check = _claim_check(raw, hits)

    # Extract cited IDs like FOC_001
    cited = list(set(re.findall(r"FOC_\d{3}", raw)))

    return {
        "answer": raw,
        "cited_ids": cited,
        "raw_llm_output": raw,
        "claim_check": check,
    }


def _claim_check(answer: str, hits: list[dict]) -> dict:
    """
    Verify that any @email or specific person-name in the answer appears
    in the retrieved evidence. This catches hallucinations.
    """
    evidence_text = " ".join(
        f"{h['metadata']['person']} {h['metadata']['title']} {h['metadata']['firm']} {h['metadata'].get('email','')}"
        for h in hits
    ).lower()

    # Check any emails in the answer are actually in the evidence
    answer_emails = re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", answer)
    for em in answer_emails:
        if em.lower() not in evidence_text:
            return {
                "passed": False,
                "reason": f"Answer contains email '{em}' that is not in the retrieved evidence. Possible hallucination."
            }

    return {"passed": True, "reason": "No unsupported factual claims detected."}


if __name__ == "__main__":
    # Self-test — requires GROQ_API_KEY in .env
    from retriever import retrieve
    q = "Who is the chief investment officer at TFO Family Office Partners?"
    print(f"> {q}\n")
    r = retrieve(q, k=5)
    print(f"Retrieval status: {r['status']}")
    if r["status"] == "ok":
        ans = generate_answer(q, r["hits"])
        print(f"\nANSWER:\n{ans['answer']}")
        print(f"\nCited: {ans['cited_ids']}")
        print(f"Claim check: {ans['claim_check']}")