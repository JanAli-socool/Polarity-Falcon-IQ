from __future__ import annotations

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app" / "main.py"
MANIFEST = ROOT / "data" / "final" / "release_manifest.json"


def test_buyer_workspace_pages_render_from_canonical_manifest():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    app = AppTest.from_file(APP, default_timeout=10).run()
    assert not app.exception

    metrics = {item.label: item.value for item in app.metric}
    assert metrics["Qualifying contacts"] == str(manifest["record_count"])
    assert metrics["Person-owned emails"] == str(
        manifest["qualifying_email_count"]
    )

    expected_gate = "Ready" if manifest["release_ready"] else "Building"
    assert metrics["Release gate"] == expected_gate

    app.switch_page("pages/1_Research_Agent.py").run()
    assert not app.exception
    assert any(
        "bounded planner" in item.value.casefold()
        for item in app.markdown
    )

    app.switch_page("pages/2_Trust_and_Operations.py").run()
    assert not app.exception
    assert any(
        "Cycle summaries are derived from append-only" in item.value
        for item in app.caption
    )


def test_retrieval_empty_state_is_governed_before_render():
    from stage2.retrieval import RetrievalQuery, retrieve

    result = retrieve(
        RetrievalQuery(
            filters={"country": "__guaranteed_no_match__"}
        )
    )
    assert result["status"] == "no_supported_match"

    app = AppTest.from_file(APP, default_timeout=10).run()
    app.session_state["retrieval_results"] = [result]
    app.run()

    assert not app.exception
    assert any(
        "No released record satisfies every requested condition"
        in item.value
        for item in app.info
    )
    assert any(
        "authorized denominator" in item.value
        for item in app.markdown
    )
    assert not any(
        "Stage 1" in item.value
        and "26 contact records" in item.value
        for item in app.markdown
    )
