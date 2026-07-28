# rag/retriever.py
# Retrieval + 3-layer epistemic control.
# Layer 1: distance gate (refuse if no chunk is close enough)
# Layer 2: field-presence gate (refuse if user asks for a field the record doesn't have)
# Layer 3: post-generation claim check (in generator.py)

import chromadb
from chromadb.utils import embedding_functions
import pathlib
import re

DB_DIR = pathlib.Path("rag/chroma_db")

# Calibrated from sanity tests:
#   test 2 (strong match): distances ~0.3-0.4
#   test 3 (weak match, "Miami" not in data): distances ~0.52+
DISTANCE_REFUSE_THRESHOLD = 0.50  # above this = refuse
DISTANCE_STRONG_MATCH = 0.40      # below this = high confidence

_embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)
_client = chromadb.PersistentClient(path=str(DB_DIR))
_col = _client.get_collection("fo_contacts", embedding_function=_embed_fn)

def retrieve(query: str, k: int = 5) -> dict:
    """
    Retrieve top-k records, apply keyword boost, then apply epistemic gates.
    Returns a dict:
      {status, reason, hits, top_distance, requested_field}
    """
    if not query or not query.strip():
        return {"status": "refuse_no_match", "reason": "empty query",
                "hits": [], "top_distance": None, "requested_field": None}

    result = _col.query(query_texts=[query], n_results=k)
    docs = result["documents"][0]
    metas = result["metadatas"][0]
    dists = result["distances"][0]

    if not docs:
        return {"status": "refuse_no_match", "reason": "no records in index",
                "hits": [], "top_distance": None, "requested_field": None}

    # Build hit objects
    hits = [
        {"document": d, "metadata": m, "distance": dist}
        for d, m, dist in zip(docs, metas, dists)
    ]

    # ─── KEYWORD BOOST (re-rank) ───────────────────────────────────
    # Small-embedding models sometimes lose exact role matches to records
    # with repeated related words. If the query names a specific role
    # phrase, promote records whose title contains that exact phrase.
    q_low = query.lower()
    role_phrases = [
        "chief investment officer", "chief financial officer",
        "chief executive officer", "chief operating officer",
        "chief compliance officer", "chief tax officer",
        "managing partner", "managing director",
        "portfolio manager", "founder",
    ]
    boosted_phrase = next((p for p in role_phrases if p in q_low), None)
    if boosted_phrase:
        def _boost_key(h):
            title_low = h["metadata"].get("title", "").lower()
            exact = boosted_phrase in title_low
            return h["distance"] - (0.15 if exact else 0.0)
        hits = sorted(hits, key=_boost_key)

    # Effective distance for gating = boosted distance of top hit
    top_hit = hits[0]
    top_title_low = top_hit["metadata"].get("title", "").lower()
    boost_applied = boosted_phrase is not None and boosted_phrase in top_title_low
    effective_top_dist = top_hit["distance"] - (0.15 if boost_applied else 0.0)

    # ─── LAYER 1: distance gate (uses effective distance) ──────────
    if effective_top_dist > DISTANCE_REFUSE_THRESHOLD:
        return {
            "status": "refuse_no_match",
            "reason": (
                f"The closest record had an effective semantic distance of "
                f"{effective_top_dist:.2f}, above the refuse threshold "
                f"({DISTANCE_REFUSE_THRESHOLD}). The dataset does not contain "
                f"sufficient evidence to answer this reliably."
            ),
            "hits": [],
            "top_distance": effective_top_dist,
            "requested_field": None,
        }

    # ─── LAYER 2: field-presence gate ──────────────────────────────
    requested_field = _detect_requested_field(query)
    if requested_field:
        top_meta = top_hit["metadata"]
        # For fields we don't store in metadata (phone, linkedin), always refuse
        if requested_field not in ("email",):
            return {
                "status": "refuse_field_missing",
                "reason": (
                    f"The dataset does not currently store '{requested_field}' "
                    f"as a queryable field. See the methodology doc for the "
                    f"list of fields captured in this build."
                ),
                "hits": hits,
                "top_distance": effective_top_dist,
                "requested_field": requested_field,
            }
        if not top_meta.get(requested_field, "").strip():
            return {
                "status": "refuse_field_missing",
                "reason": (
                    f"The best-matching record ({top_meta.get('person','?')} at "
                    f"{top_meta.get('firm','?')}) does not have a "
                    f"'{requested_field}' value in the dataset. This field "
                    f"was not verifiable from public sources at build time."
                ),
                "hits": hits,
                "top_distance": effective_top_dist,
                "requested_field": requested_field,
            }

    return {
        "status": "ok",
        "reason": "match within threshold",
        "hits": hits,
        "top_distance": effective_top_dist,
        "requested_field": requested_field,
    }


def _detect_requested_field(query: str) -> str | None:
    """Naive intent detection: is the user asking for email/phone/etc.?"""
    q = query.lower()
    if any(w in q for w in ["email", "e-mail", "contact ", "reach out", "how to contact"]):
        return "email"
    if any(w in q for w in ["phone", "call", "number"]):
        return "phone"  # note: we don't have a phone metadata field; will always refuse
    if any(w in q for w in ["linkedin", "profile"]):
        return "linkedin"  # same — not in metadata
    return None


if __name__ == "__main__":
    # Quick self-test
    for q in [
        "chief investment officer",
        "who runs Boston Family Office",
        "partner in Miami",
        "what is Chuck Carroll's email",
    ]:
        print(f"\n> {q}")
        r = retrieve(q, k=10)
        print(f"  status: {r['status']}")
        print(f"  top_dist: {r['top_distance']}")
        if r["status"] == "ok":
            for h in r["hits"][:2]:
                print(f"    - {h['metadata']['person']} @ {h['metadata']['firm']} (d={h['distance']:.3f})")
        else:
            print(f"  reason: {r['reason'][:100]}")