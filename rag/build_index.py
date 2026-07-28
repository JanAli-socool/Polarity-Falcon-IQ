# rag/build_index.py
# Chunks the final contacts CSV into per-record text blocks,
# embeds them with a local sentence-transformer, stores in Chroma.
# All local, all free.

import pandas as pd
import chromadb
from chromadb.utils import embedding_functions
import pathlib

CSV = pathlib.Path("data/final/family_office_contacts.csv")
DB_DIR = pathlib.Path("rag/chroma_db")
DB_DIR.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(CSV).fillna("")
print(f"[info] loaded {len(df)} rows from {CSV}")

# Local embedder — 100% free, ~80MB model on first run
embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

client = chromadb.PersistentClient(path=str(DB_DIR))
try:
    client.delete_collection("fo_contacts")
except Exception:
    pass
col = client.create_collection("fo_contacts", embedding_function=embed_fn)

def record_to_text(row):
    """Human-readable chunk for one contact record."""
    parts = [
        f"{row['Contact Full Name']} works at {row['Family Office Name']}.",
        f"Job title: {row['Contact Job Title']}." if row['Contact Job Title'] else "",
        f"Firm country: {row['Family Office Country']}." if row['Family Office Country'] else "",
        f"Firm city: {row['Family Office City']}." if row['Family Office City'] else "",
        f"Email: {row['Contact Primary Email']}." if row['Contact Primary Email'] else "",
        f"LinkedIn: {row['Contact LinkedIn Profile']}." if row['Contact LinkedIn Profile'] else "",
    ]
    return " ".join(p for p in parts if p)

docs, ids, metas = [], [], []
for _, row in df.iterrows():
    docs.append(record_to_text(row))
    ids.append(row['Record ID'])
    metas.append({
        "record_id": str(row['Record ID']),
        "firm": str(row['Family Office Name']),
        "person": str(row['Contact Full Name']),
        "title": str(row['Contact Job Title']),
        "email": str(row['Contact Primary Email']),
        "source_url": str(row['Contact Source URL']),
        "confidence": str(row['Confidence']),
    })

col.add(documents=docs, ids=ids, metadatas=metas)
print(f"[ok] indexed {len(docs)} records into Chroma at {DB_DIR}")

# Sanity test
print("\n[test 1] query: 'chief investment officer'")
res = col.query(query_texts=["chief investment officer"], n_results=3)
for i, doc in enumerate(res['documents'][0]):
    m = res['metadatas'][0][i]
    print(f"  [{i+1}] {m['person']:<25} — {m['title'][:60]}")

print("\n[test 2] query: 'who runs Boston Family Office'")
res = col.query(query_texts=["who runs Boston Family Office"], n_results=3)
for i, doc in enumerate(res['documents'][0]):
    m = res['metadatas'][0][i]
    print(f"  [{i+1}] {m['person']:<25} at {m['firm']:<30} — {m['title'][:40]}")

print("\n[test 3] query: 'partner in Miami' (should have weak match)")
res = col.query(query_texts=["partner in Miami"], n_results=3)
for i, doc in enumerate(res['documents'][0]):
    m = res['metadatas'][0][i]
    dist = res['distances'][0][i] if 'distances' in res else "n/a"
    print(f"  [{i+1}] {m['person']:<25} at {m['firm']:<30} (dist={dist:.3f})")