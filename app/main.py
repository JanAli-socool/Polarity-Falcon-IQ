# app/main.py
# Customer-facing Streamlit UI for the family-office contacts RAG.
# Designed for a non-technical investor-relations user.

import sys
import pathlib

# Make rag/ importable
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import streamlit as st
from rag.retriever import retrieve
from rag.generator import generate_answer
import os
# Bridge Streamlit Cloud secrets → os.environ, but tolerate the case
# where secrets.toml doesn't exist (local dev with .env instead).
try:
    if "GROQ_API_KEY" in st.secrets:
        os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]
except Exception:
    pass  # No secrets.toml locally — .env will be loaded by generator.py

st.set_page_config(
    page_title="Family Office Contacts — Query",
    page_icon="🏛️",
    layout="centered",
)

st.title("🏛️ Family Office Contacts")
st.caption(
    "Ask natural-language questions about the curated dataset of family "
    "office contacts. The system will only answer from verified records "
    "and will decline when evidence is insufficient."
)

with st.expander("ℹ️ About this dataset"):
    st.markdown(
        """
        - **26 contact records** across **6 verified family offices**
        - Every name and title was extracted from the firm's own team page
        - Blank fields (email, phone, LinkedIn) mean the data was not
          publicly verifiable at build time. We do not guess.
        - The system uses a 3-layer control:
            1. **Distance gate** — refuses if no record is a close match
            2. **Field-presence gate** — refuses if the requested field
               (e.g. email) isn't in the matched record
            3. **Claim check** — verifies the AI's answer only cites facts
               present in the retrieved records
        """
    )

st.markdown("### Try asking:")
st.markdown(
    "- *Who is the chief investment officer at TFO Family Office Partners?*\n"
    "- *List the partners at WE Family Offices.*\n"
    "- *Who runs Boston Family Office?*\n"
    "- *What is Chuck Carroll's role?*"
)

query = st.text_input(
    "Your question:",
    placeholder="e.g. Who runs Boston Family Office?",
)

if query:
    with st.spinner("Searching the dataset..."):
        result = retrieve(query, k=10)

    if result["status"] == "refuse_no_match":
        st.warning(f"🚫 **The dataset cannot answer this reliably.**\n\n{result['reason']}")

    elif result["status"] == "refuse_field_missing":
        st.warning(f"🚫 **The requested information is not in the dataset.**\n\n{result['reason']}")
        with st.expander("See the closest matching record anyway"):
            for h in result["hits"][:1]:
                m = h["metadata"]
                st.markdown(
                    f"**{m['person']}** — {m['title']}  \n"
                    f"Firm: {m['firm']}  \n"
                    f"Source: {m['source_url']}"
                )

    else:  # status == "ok"
        with st.spinner("Composing answer..."):
            answer = generate_answer(query, result["hits"])

        st.markdown("### Answer")
        st.markdown(answer["answer"])

        if not answer["claim_check"]["passed"]:
            st.error(
                f"⚠️ **Post-generation claim check failed:** "
                f"{answer['claim_check']['reason']} "
                f"The answer above may contain unsupported claims — treat with caution."
            )
        else:
            st.success("✅ Answer verified: all claims trace to the evidence below.")

        st.markdown("### Supporting evidence")
        for h in result["hits"][:5]:
            m = h["metadata"]
            with st.container(border=True):
                st.markdown(
                    f"**{m['record_id']}** — {m['person']}  \n"
                    f"*{m['title']}* at **{m['firm']}**  \n"
                    f"Confidence: `{m['confidence']}` · "
                    f"Distance: `{h['distance']:.3f}`  \n"
                    f"[Source page]({m['source_url']})"
                )

st.markdown("---")
st.caption(
    "Built for the Falcon Scaling / PolarityIQ assessment. "
    "All records sourced from public firm websites. "
    "See methodology doc in the repository for validation chains and known limitations."
)