"""Natural-language planning over allowlisted evidence tools."""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))

import streamlit as st

from app.ui import bridge_secrets, configure_page, load_manifest, render_record, render_release_strip
from stage2.agent import GOAL_2, run_agent

configure_page("Research agent", "↗️")
bridge_secrets()

st.markdown(
    """
    <div class="hero">
      <div class="eyebrow">Multi-step research · bounded planner</div>
      <h1>Turn a commercial question into inspectable research</h1>
      <p>The model may plan allowlisted searches. It cannot write facts into the answer: deterministic tools retrieve evidence, and a final authority gate checks every cited record before display.</p>
    </div>
    """,
    unsafe_allow_html=True,
)
render_release_strip(load_manifest())

examples = {
    "Custom goal": "",
    "Goal 1 · shortlist and contact burden": (
        "Build a US healthcare family-office outreach shortlist. Count matching firms, identify decision-makers with person-owned professional email, and show the contact-route and source mix."
    ),
    "Goal 2 · healthcare LP fit (required wording)": GOAL_2,
    "Goal 3 · evidence-refresh prioritization": (
        "For the Falcon Scaling partnerships lead, find healthcare-focused family-office decision-makers with a current person-owned route, compare available evidence coverage, and identify where missing mandate evidence prevents outreach prioritization."
    ),
}
choice = st.selectbox("Start with a saved buyer challenge", list(examples))
default_goal = examples[choice]
if st.session_state.get("selected_example") != choice:
    st.session_state["agent_goal"] = default_goal
    st.session_state["selected_example"] = choice
goal = st.text_area(
    "Research goal",
    key="agent_goal",
    height=120,
    placeholder="Describe the shortlist, comparison, trust, or contact decision you need to make.",
)

left, right = st.columns([1, 2])
with left:
    run = st.button("Run bounded research", type="primary", disabled=not goal, use_container_width=True)
with right:
    st.caption("If model planning is unavailable, deterministic search remains available and the run is visibly labeled as fallback—not presented as an agent success.")

if run:
    with st.spinner("Planning, retrieving, and checking evidence authority..."):
        try:
            st.session_state["agent_result"] = run_agent(goal, use_model=True, save_trace=True)
        except Exception as exc:
            st.error(f"The run stopped safely before rendering: {type(exc).__name__}: {exc}")

if "agent_result" in st.session_state:
    result = st.session_state["agent_result"]
    st.markdown("---")
    a, b, c = st.columns(3)
    a.metric("Run status", result["status"].title())
    planner_label = {"model": "Model", "deterministic_fallback": "Deterministic fallback", "none": "Not run"}.get(result["planner_mode"], "Unknown")
    b.metric("Planner", planner_label)
    c.metric("Authorized tool calls", len(result["plan"]["tool_calls"]))

    if result["planner_mode"] == "deterministic_fallback":
        st.warning("Model planning was unavailable. These are deterministic retrieval results, not evidence of model-selected actions.")
    elif result["status"] == "refused":
        st.warning(result["reason"])
    authority = result["render_authority"]
    if not authority["passed"]:
        st.error("Nothing was rendered because the authority check found an unauthorized citation.")
    elif authority["decision"] == "abstain":
        st.info("The system abstained: authorized tools did not return a supported record or aggregate for this goal.")
    else:
        st.success("Render authority passed. Every displayed record came from the policy-authorized release.")

    st.subheader("What the system did")
    st.write(result["customer_explanation"])
    for index, call in enumerate(result["plan"]["tool_calls"], 1):
        st.write(f"{index}. **{call['tool'].replace('_', ' ').title()}** — `{json.dumps(call['arguments'], sort_keys=True)}`")

    if authority["passed"]:
        st.subheader("Supported result")
        for item in result["tool_results"]:
            tool_result = item["result"]
            with st.expander(item["tool"].replace("_", " ").title(), expanded=True):
                if item["tool"] == "compare_lmm_healthcare_lp_fit":
                    st.caption(tool_result["method"])
                    if not tool_result["results"]:
                        st.info(" ".join(tool_result["limitations"]))
                    for comparison in tool_result["results"]:
                        st.markdown(f"### {comparison['firm']} · {comparison['confidence']} confidence")
                        st.progress(comparison["fit_score"] / 100, text=f"Supported signal score: {comparison['fit_score']}/100")
                        signal_cols = st.columns(4)
                        for col, (signal, supported) in zip(signal_cols, comparison["signals"].items()):
                            col.metric(signal.replace("_", " ").title(), "Supported" if supported else "Not found")
                        for limitation in comparison["limitations"]:
                            st.warning(limitation)
                        st.write("**Supported action:**", comparison["supported_action"])
                        render_record(comparison["recommended_contact"])
                else:
                    st.write(
                        f"{tool_result['matched_record_count']} contacts across {tool_result['matched_firm_count']} firms; "
                        f"aggregate: `{json.dumps(tool_result['aggregate'], sort_keys=True)}`"
                    )
                    if tool_result["status"] == "no_supported_match":
                        st.info("No released record satisfied every condition. The system did not infer a match.")
                    for record in tool_result.get("records", []):
                        render_record(record)

    st.subheader("Replay and audit")
    st.caption(f"Trace ID: {result['trace_id']} · Raw action, tool, decision, retry, and refusal events are retained without curation.")
    with st.expander("Inspect raw trace"):
        st.json(result["trace"], expanded=False)
    trace_jsonl = "\n".join(json.dumps(event, sort_keys=True) for event in result["trace"]) + "\n"
    st.download_button(
        "Download raw trace (JSONL)", trace_jsonl,
        file_name=f"{result['trace_id']}.jsonl", mime="application/x-ndjson",
    )
