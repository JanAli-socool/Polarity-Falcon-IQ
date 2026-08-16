# rag/retriever_v2.py
# Rewritten RAG Retriever with Pre-Generation Claim Check + Evidence Binding
# Uses sentence-transformers directly + SQLite for storage (bypasses chromadb persistent client issues)

import sqlite3
import pathlib
import re
import json
import numpy as np
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

# Load embeddings at module level
from sentence_transformers import SentenceTransformer
_embed_model = SentenceTransformer('all-MiniLM-L6-v2')

DB_PATH = pathlib.Path("data/canonical/contacts.db")
CHROMA_DB = pathlib.Path("rag/chroma_db/chroma.sqlite3")

# Calibrated thresholds
DISTANCE_REFUSE_THRESHOLD = 0.50
DISTANCE_STRONG_MATCH = 0.40


@dataclass
class EvidenceBinding:
    """Binds a claim to specific evidence in the dataset."""
    claim: str
    record_id: str
    field: str
    field_value: str
    source_url: str
    confidence: str


@dataclass
class RetrievalResult:
    status: str
    reason: str
    hits: list
    top_distance: Optional[float]
    requested_field: Optional[str]
    evidence_bindings: list
    can_answer: bool


def _get_embeddings(texts: List[str]) -> np.ndarray:
    """Get embeddings for a list of texts."""
    return _embed_model.encode(texts, normalize_embeddings=True)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Compute cosine similarity between two sets of normalized vectors."""
    return np.dot(a, b.T)


def retrieve(query: str, k: int = 10) -> RetrievalResult:
    """
    Retrieve top-k records using sentence-transformers embeddings + SQLite.
    Applies keyword boost, then epistemic gates.
    """
    if not query or not query.strip():
        return RetrievalResult(
            status="refuse_no_match",
            reason="empty query",
            hits=[],
            top_distance=None,
            requested_field=None,
            evidence_bindings=[],
            can_answer=False,
        )

    # Get all records from canonical DB
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute("""
        SELECT p.record_id, p.full_name, p.job_title, p.title_normalized,
               p.email, p.linkedin_url, p.source_url, p.confidence,
               f.firm_name, f.verification_tier, f.firm_country,
               f.official_url as firm_official_url
        FROM people p
        JOIN firms f ON p.firm_id = f.firm_id
        WHERE p.status = 'qualifying'
        ORDER BY p.record_id
    """)
    rows = cur.fetchall()
    conn.close()
    
    if not rows:
        return RetrievalResult(
            status="refuse_no_match",
            reason="no records in dataset",
            hits=[],
            top_distance=None,
            requested_field=None,
            evidence_bindings=[],
            can_answer=False,
        )
    
    # Build document texts for embedding (same format as chroma index)
    doc_texts = []
    records = []
    for row in rows:
        parts = [
            f"{row['full_name']} works at {row['firm_name']}.",
            f"Job title: {row['job_title']}." if row['job_title'] else "",
            f"Firm country: {row['firm_country']}." if row['firm_country'] else "",
            f"Firm city: ." if False else "",  # Not in canonical DB
            f"Email: {row['email']}." if row['email'] else "",
            f"LinkedIn: {row['linkedin_url']}." if row['linkedin_url'] else "",
        ]
        doc_text = " ".join(part for part in parts if part)
        doc_texts.append(doc_text)
        records.append(dict(row))
    
    # Compute query embedding
    query_emb = _get_embeddings([query])[0]
    
    # Compute document embeddings (cache this in production!)
    doc_embs = _get_embeddings(doc_texts)
    
    # Compute similarities
    similarities = _cosine_similarity(query_emb.reshape(1, -1), doc_embs)[0]
    distances = 1 - similarities  # Convert to distance
    
    # Build hits
    hits = [
        {
            "document": doc_texts[i],
            "metadata": {
                "record_id": records[i]["record_id"],
                "person": records[i]["full_name"],
                "title": records[i]["title_normalized"] or records[i]["job_title"] or "",
                "firm": records[i]["firm_name"],
                "email": records[i]["email"] or "",
                "linkedin": records[i]["linkedin_url"] or "",
                "source_url": records[i]["source_url"] or "",
                "confidence": records[i]["confidence"] or "low",
            },
            "distance": float(distances[i]),
        }
        for i in range(len(records))
    ]
    
    # KEYWORD BOOST (re-rank)
    q_low = query.lower()
    role_phrases = [
        "chief investment officer", "chief financial officer",
        "chief executive officer", "chief operating officer",
        "chief compliance officer", "chief tax officer",
        "managing partner", "managing director",
        "portfolio manager", "founder",
        "president", "partner", "principal",
        "director", "vice president",
    ]
    boosted_phrase = next((p for p in role_phrases if p in q_low), None)
    if boosted_phrase:
        def _boost_key(h):
            title_low = h["metadata"].get("title", "").lower()
            exact = boosted_phrase in title_low
            return h["distance"] - (0.15 if exact else 0.0)
        hits = sorted(hits, key=_boost_key)
    
    # Take top k
    hits = hits[:k]
    
    if not hits:
        return RetrievalResult(
            status="refuse_no_match",
            reason="no records in dataset",
            hits=[],
            top_distance=None,
            requested_field=None,
            evidence_bindings=[],
            can_answer=False,
        )

    top_hit = hits[0]
    top_title_low = top_hit["metadata"].get("title", "").lower()
    boost_applied = boosted_phrase is not None and boosted_phrase in top_title_low
    effective_top_dist = top_hit["distance"] - (0.15 if boost_applied else 0.0)

    # LAYER 1: Distance gate
    if effective_top_dist > DISTANCE_REFUSE_THRESHOLD:
        return RetrievalResult(
            status="refuse_no_match",
            reason=(
                f"The closest record had an effective semantic distance of "
                f"{effective_top_dist:.2f}, above the refuse threshold "
                f"({DISTANCE_REFUSE_THRESHOLD}). The dataset does not contain "
                f"sufficient evidence to answer this reliably."
            ),
            hits=[],
            top_distance=effective_top_dist,
            requested_field=None,
            evidence_bindings=[],
            can_answer=False,
        )

    # LAYER 2: Field-presence gate
    requested_field = _detect_requested_field(query)
    if requested_field:
        top_meta = top_hit["metadata"]
        if requested_field not in ("email",):
            return RetrievalResult(
                status="refuse_field_missing",
                reason=(
                    f"The dataset does not currently store '{requested_field}' "
                    f"as a queryable field. Available fields: name, title, firm, email, "
                    f"LinkedIn, source URL, confidence, verification tier."
                ),
                hits=hits,
                top_distance=effective_top_dist,
                requested_field=requested_field,
                evidence_bindings=[],
                can_answer=False,
            )
        if not top_meta.get(requested_field, "").strip():
            return RetrievalResult(
                status="refuse_field_missing",
                reason=(
                    f"The best-matching record ({top_meta.get('person','?')} at "
                    f"{top_meta.get('firm','?')}) does not have a "
                    f"'{requested_field}' value in the dataset. This field "
                    f"was not verifiable from public sources at build time."
                ),
                hits=hits,
                top_distance=effective_top_dist,
                requested_field=requested_field,
                evidence_bindings=[],
                can_answer=False,
            )

    # LAYER 3: Pre-generation evidence binding
    evidence_bindings = _build_evidence_bindings(hits, query)
    can_answer = _assess_answerability(hits, query, requested_field)

    return RetrievalResult(
        status="ok",
        reason="match within threshold",
        hits=hits,
        top_distance=effective_top_dist,
        requested_field=requested_field,
        evidence_bindings=evidence_bindings,
        can_answer=can_answer,
    )


def _detect_requested_field(query: str) -> str | None:
    """Detect if user is asking for a specific field."""
    q = query.lower()
    if any(w in q for w in ["email", "e-mail", "contact ", "reach out", "how to contact"]):
        return "email"
    if any(w in q for w in ["phone", "call", "number"]):
        return "phone"
    if any(w in q for w in ["linkedin", "profile"]):
        return "linkedin"
    return None


def _build_evidence_bindings(hits: list, query: str) -> list:
    """Build evidence bindings for each hit - maps claims to specific fields."""
    bindings = []
    q_low = query.lower()
    
    for h in hits[:5]:
        m = h["metadata"]
        
        bindings.append(EvidenceBinding(
            claim=f"{m['person']} works at {m['firm']}",
            record_id=m["record_id"],
            field="identity",
            field_value=f"{m['person']} — {m['title']} at {m['firm']}",
            source_url=m.get("source_url", ""),
            confidence=m.get("confidence", "low"),
        ))
        
        if m.get("title"):
            bindings.append(EvidenceBinding(
                claim=f"{m['person']} holds title: {m['title']}",
                record_id=m["record_id"],
                field="title",
                field_value=m["title"],
                source_url=m.get("source_url", ""),
                confidence=m.get("confidence", "low"),
            ))
        
        if m.get("email") and any(w in q_low for w in ["email", "contact", "reach"]):
            bindings.append(EvidenceBinding(
                claim=f"{m['person']} email: {m['email']}",
                record_id=m["record_id"],
                field="email",
                field_value=m["email"],
                source_url=m.get("source_url", ""),
                confidence=m.get("confidence", "low"),
            ))
        
        if m.get("linkedin"):
            bindings.append(EvidenceBinding(
                claim=f"{m['person']} LinkedIn: {m['linkedin']}",
                record_id=m["record_id"],
                field="linkedin",
                field_value=m["linkedin"],
                source_url=m.get("source_url", ""),
                confidence=m.get("confidence", "low"),
            ))
    
    return bindings


def _assess_answerability(hits: list, query: str, requested_field: str | None) -> bool:
    """Assess if we have enough evidence to answer the query."""
    if not hits:
        return False
    
    top = hits[0]["metadata"]
    
    if requested_field:
        if requested_field == "email" and not top.get("email", "").strip():
            return False
        if requested_field == "phone":
            return False
        if requested_field == "linkedin" and not top.get("linkedin", "").strip():
            return False
    
    if top.get("confidence") == "low" and len(hits) < 2:
        return False
    
    return True


def get_evidence_for_generation(hits: list, query: str) -> dict:
    """Format evidence for LLM generation with explicit source attribution."""
    evidence_items = []
    for h in hits[:5]:
        m = h["metadata"]
        item = {
            "record_id": m["record_id"],
            "person": m["person"],
            "title": m.get("title", ""),
            "firm": m["firm"],
            "email": m.get("email", ""),
            "linkedin": m.get("linkedin", ""),
            "source_url": m.get("source_url", ""),
            "confidence": m.get("confidence", "low"),
            "distance": round(h["distance"], 3),
        }
        evidence_items.append(item)
    
    return {
        "query": query,
        "evidence": evidence_items,
        "evidence_count": len(evidence_items),
        "top_distance": round(hits[0]["distance"], 3) if hits else None,
    }


if __name__ == "__main__":
    for q in [
        "chief investment officer",
        "who runs Boston Family Office",
        "partner in Miami",
        "what is Chuck Carroll's email",
        "list all managing directors",
    ]:
        print(f"\n> {q}")
        r = retrieve(q, k=10)
        print(f"  status: {r.status}")
        print(f"  can_answer: {r.can_answer}")
        print(f"  top_dist: {r.top_distance}")
        print(f"  requested_field: {r.requested_field}")
        print(f"  evidence_bindings: {len(r.evidence_bindings)}")
        if r.status == "ok":
            for h in r.hits[:2]:
                m = h["metadata"]
                print(f"    - {m['person']} @ {m['firm']} (d={h['distance']:.3f}) title={m.get('title','')[:40]}")
        else:
            print(f"  reason: {r.reason[:120]}")