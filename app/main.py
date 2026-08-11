"""Paid-tier evidence search over the single policy-authorized Stage 2 corpus."""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import streamlit as st

from app.ui import configure_page, csv_download, load_manifest, render_release_strip, render_retrieval_result
from stage2.retrieval import RetrievalQuery, authorized_records, decompose_natural_language, retrieve

configure_page("Evidence search", "🔎")

st.markdown(
    """
    <div class="hero">
      <div class="eyebrow">Buyer workspace · read-time policy enforcement</div>
      <h1>Find a supported route to the right investor</h1>
      <p>Search released family-office decision-makers, inspect the evidence behind every fact, and carry only supported contact routes into outreach.</p>
    </div>
    """,
    unsafe_allow_html=True,
)
manifest = load_manifest()
render_release_strip(manifest)

search_tab, filters_tab = st.tabs(["Ask the dataset", "Build exact filters"])

with search_tab:
    st.subheader("Ask a research question")
    st.caption("Compound requests are split into deterministic filters and aggregates. Unknowns remain unknown; this is search, not generated advice.")
    natural_goal = st.text_input(
        "Question",
        placeholder="Find US healthcare contacts with a person-owned email and show the source mix",
        key="natural_goal",
    )
    if st.button("Search evidence", type="primary", disabled=not natural_goal, key="natural_search"):
        try:
            queries = decompose_natural_language(natural_goal)
            results = [retrieve(query) for query in queries]
            st.session_state["retrieval_results"] = results
        except ValueError as exc:
            st.error(f"That request could not be translated into supported filters: {exc}")
    for index, result in enumerate(st.session_state.get("retrieval_results", []), start=1):
        if len(st.session_state["retrieval_results"]) > 1:
            st.markdown(f"### Query part {index}")
        render_retrieval_result(result)
    if st.session_state.get("retrieval_results"):
        st.download_button(
            "Download this evidence packet (JSON)",
            json.dumps(st.session_state["retrieval_results"], indent=2),
            file_name="falcon_retrieval_evidence.json",
            mime="application/json",
        )

with filters_tab:
    corpus = authorized_records()
    countries = sorted({item["firm"].get("country") for item in corpus if item["firm"].get("country")})
    firm_types = sorted({item["firm"].get("type") for item in corpus if item["firm"].get("type")})
    role_classes = sorted({item["person"].get("role_class") for item in corpus if item["person"].get("role_class")})
    col1, col2, col3 = st.columns(3)
    country = col1.selectbox("Country", ["Any", *countries])
    firm_type = col2.selectbox("Family-office type", ["Any", *firm_types])
    role_class = col3.selectbox("Decision-maker role", ["Any", *role_classes])
    col4, col5, col6 = st.columns(3)
    route_type = col4.selectbox("Contact route", ["Any", "email", "direct_phone", "linkedin"], format_func=lambda value: value.replace("_", " ").title())
    has_email = col5.selectbox("Person-owned email", ["Any", "Required", "Not required"])
    aggregate = col6.selectbox("Measure", ["records", "firms", "source_mix", "route_mix", "countries"])
    terms_text = st.text_input("Evidence terms", placeholder="healthcare, private equity")
    if st.button("Apply exact filters", type="primary"):
        filters = {}
        if country != "Any": filters["country"] = country
        if firm_type != "Any": filters["firm_type"] = firm_type
        if role_class != "Any": filters["role_class"] = role_class
        if route_type != "Any": filters["route_type"] = route_type
        if has_email == "Required": filters["has_email"] = True
        terms = tuple(term.strip() for term in terms_text.split(",") if term.strip())
        st.session_state["exact_result"] = retrieve(RetrievalQuery(filters=filters, terms=terms, aggregate=aggregate))
    if "exact_result" in st.session_state:
        render_retrieval_result(st.session_state["exact_result"])

st.markdown("---")
left, right = st.columns([2, 1])
with left:
    st.subheader("What a displayed record means")
    st.write(
        "Each record has a named person and current role, qualifying family-office classification, actionable intelligence beyond its discovery source, freshness support, and at least one person-owned route. Generic or inferred emails never enter this view."
    )
with right:
    csv_download()
    st.page_link("pages/1_Research_Agent.py", label="Continue to multi-step research →", use_container_width=True)
