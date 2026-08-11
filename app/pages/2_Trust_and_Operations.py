"""Buyer-readable release policy, freshness, provenance, and scheduler state."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))

import streamlit as st

from app.ui import ACTIONS_URL, REPOSITORY_URL, configure_page, csv_download, load_manifest, operating_summaries, render_release_strip
from stage2.io import read_jsonl
from stage2.paths import CANONICAL_RECORDS, QUARANTINE, SOURCE_OBSERVATIONS

configure_page("Trust & operations", "🛡️")

st.markdown(
    """
    <div class="hero">
      <div class="eyebrow">Release truth · provenance · operating history</div>
      <h1>Know what the system can support today</h1>
      <p>Publication gates, source mix, freshness, conflicts, and scheduler history are shown separately so a buyer can distinguish working data from a finished release.</p>
    </div>
    """,
    unsafe_allow_html=True,
)
manifest = load_manifest()
render_release_strip(manifest)

st.subheader("Current release")
left, right = st.columns([2, 1])
with left:
    st.write(f"**Release ID:** `{manifest.get('release_id', 'not generated')}`")
    st.write(f"**Generated:** {manifest.get('created_at', 'not generated')}")
    st.write(f"**Schema:** {manifest.get('schema_version', 'unknown')}")
    st.write("The CSV, JSONL, app, counts, and search all derive from the same canonical record state. Read-time policy checks run again before search results are rendered.")
with right:
    csv_download()
    st.link_button("View repository", REPOSITORY_URL, use_container_width=True)

st.subheader("Inclusion means all requirements passed")
gates = [
    ("Named decision-maker", "A real individual, current title, firm relationship, and stable evidence—not navigation copy or a department label."),
    ("Qualifying firm", "Published evidence supports the family-office classification and scope."),
    ("Actionable route", "A person-owned professional email, direct phone, or current LinkedIn profile. Generic and inferred emails do not qualify."),
    ("Commercial intelligence", "Mandate, sector, activity, or another useful fact supported beyond the candidate discovery source."),
    ("Freshness", "Evidence is within policy age, still resolves, and does not carry an unresolved conflict or stale trust state."),
]
for name, description in gates:
    with st.container(border=True):
        st.markdown(f"**{name}**")
        st.write(description)

mix_tab, state_tab, ops_tab = st.tabs(["Source mix", "State & freshness", "Scheduled operation"])
with mix_tab:
    source_mix = manifest.get("source_mix", {})
    if source_mix:
        st.bar_chart(source_mix)
        st.dataframe(
            [{"source_class": key, "qualifying_records": value} for key, value in sorted(source_mix.items())],
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("No qualifying production record exists yet, so the recomputable production source mix is empty. Discovery candidates and quarantined Stage 1 rows are not counted.")
    st.write(f"Source observations retained: **{len(read_jsonl(SOURCE_OBSERVATIONS))}**")

with state_tab:
    records = read_jsonl(CANONICAL_RECORDS)
    quarantine_count = sum(len(read_jsonl(path)) for path in QUARANTINE.glob("*.jsonl"))
    a, b, c = st.columns(3)
    a.metric("Canonical rows", len(records))
    b.metric("Released rows", manifest.get("record_count", 0))
    c.metric("Quarantined / rejected", quarantine_count)
    if records:
        st.dataframe(
            [{
                "record_id": item.get("record_id"),
                "firm": item.get("firm", {}).get("name"),
                "person": item.get("person", {}).get("name"),
                "lifecycle": item.get("lifecycle_status"),
                "trust_state": item.get("freshness", {}).get("trust_state"),
                "last_checked": item.get("freshness", {}).get("last_evidence_check_at"),
            } for item in records],
            use_container_width=True, hide_index=True,
        )
    else:
        st.caption("Canonical state is currently empty. The 26 Stage 1 rows remain physically quarantined because they do not meet the Stage 2 route and enrichment floor.")

with ops_tab:
    summaries = operating_summaries()
    st.link_button("Open repository Actions history", ACTIONS_URL, use_container_width=True)
    if summaries:
        st.dataframe(summaries, use_container_width=True, hide_index=True)
    else:
        st.warning("No scheduler-owned cycle summary is present in this repository snapshot. The required independent 48-hour operating evidence has not yet been earned.")
    st.caption("Cycle summaries are derived from append-only raw operating events. Dependency failures, retries, recoveries, stale transitions, and quarantine decisions remain in the uncurated logs.")

st.subheader("Authority boundary")
st.code(
    "candidate sources → quarantine → enrichment evidence → policy evaluation\n"
    "→ canonical publish state → read-time authorization → deterministic tools\n"
    "→ cited-record authority check → customer display",
    language=None,
)
st.write(
    "The language model can select from allowlisted retrieval tools. It cannot authorize records, create contact facts, change trust state, or bypass release policy. If support is missing, the visible outcome is not found, conflicted, stale, quarantined, or abstained—not a plausible completion."
)
