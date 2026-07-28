# Family Office Contacts — Micro-RAG

![Lint](https://github.com/JanAli-socool/falcon-fo/actions/workflows/lint-and-import.yml/badge.svg)
![Dataset Integrity](https://github.com/JanAli-socool/falcon-fo/actions/workflows/dataset-integrity.yml/badge.svg)
![RAG Smoke](https://github.com/JanAli-socool/falcon-fo/actions/workflows/rag-smoke-test.yml/badge.svg)

Assessment build for Falcon Scaling / PolarityIQ.

## What this is
A discovery + verification + RAG pipeline that produces a small, honestly-validated dataset of family-office contacts, then serves natural-language queries over it with a 3-layer epistemic control.

## Quick start
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Rebuild the dataset (optional — output is already in data/final/)
python pipeline/01_discover_probe.py
python pipeline/01b_discover_more.py
python pipeline/02_extract_firms.py
python pipeline/03_sec_seed.py
python pipeline/04_verify_firms.py
python pipeline/04b_curate_verified_firms.py
python pipeline/05_extract_people.py
python pipeline/06_build_final_dataset.py

# Build the RAG index (required before running the app)
python rag/build_index.py

# Set GROQ_API_KEY in .env, then run the app
streamlit run app/main.py
