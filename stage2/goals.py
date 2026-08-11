"""Required commercial goals and deterministic manual-retrieval packets."""

from __future__ import annotations

from typing import Any

from stage2.agent import GOAL_2
from stage2.retrieval import RetrievalQuery, compare_lmm_healthcare_lp_fit, retrieve

GOAL_1 = (
    "Build an evidence-backed US healthcare family-office outreach shortlist: find decision-makers "
    "with a person-owned professional email, count matching firms, and report the source and "
    "contact-route mix."
)
GOAL_3 = (
    "For the Falcon Scaling partnerships lead preparing a healthcare fund outreach sprint, find "
    "current US family-office decision-makers with a person-owned professional email, count the "
    "firms, and show the source and contact-route mix so the team can prioritize outreach without "
    "re-validating routes."
)
GOALS = {"goal_1": GOAL_1, "goal_2": GOAL_2, "goal_3": GOAL_3}


def manual_retrieval(goal_key: str) -> dict[str, Any]:
    """Return inspectable non-agent retrieval for side-by-side goal evidence."""
    if goal_key == "goal_2":
        return {
            "method": "Fixed four-signal evidence comparator over the authorized release.",
            "outputs": [compare_lmm_healthcare_lp_fit()],
        }
    filters: dict[str, Any] = {
        "country": "united states",
        "has_email": True,
    }
    if goal_key == "goal_3":
        filters["trust_state"] = "supported_current"
    terms = ("healthcare",)
    return {
        "method": "Four deterministic queries over one authorized denominator: shortlist, firm count, source mix, and route mix.",
        "outputs": [
            retrieve(RetrievalQuery(filters=filters, terms=terms, limit=100)),
            retrieve(RetrievalQuery(filters=filters, terms=terms, limit=1, aggregate="firms")),
            retrieve(RetrievalQuery(filters=filters, terms=terms, limit=1, aggregate="source_mix")),
            retrieve(RetrievalQuery(filters=filters, terms=terms, limit=1, aggregate="route_mix")),
        ],
    }
