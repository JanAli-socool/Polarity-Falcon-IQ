from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[2] / "app" / "main.py"


def test_buyer_workspace_pages_render_without_stage1_index():
    app = AppTest.from_file(APP, default_timeout=10).run()
    assert not app.exception
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["Qualifying contacts"] == "0"
    assert metrics["Person-owned emails"] == "0"
    assert metrics["Release gate"] == "Building"

    app.switch_page("pages/1_Research_Agent.py").run()
    assert not app.exception
    assert any("bounded planner" in item.value.casefold() for item in app.markdown)

    app.switch_page("pages/2_Trust_and_Operations.py").run()
    assert not app.exception
    assert any("required independent 48-hour operating evidence" in item.value for item in app.warning)


def test_natural_search_empty_state_is_governed_before_render():
    app = AppTest.from_file(APP, default_timeout=10).run()
    app.text_input(key="natural_goal").input(
        "Find United States healthcare contacts with email and show source mix"
    )
    app.button(key="natural_search").click().run()
    assert not app.exception
    assert any("No released record satisfies every requested condition" in item.value for item in app.info)
    assert not any("Stage 1" in item.value and "26 contact records" in item.value for item in app.markdown)
