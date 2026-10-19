"""Spare model budget must not authorize unrelated collection."""

import pytest
from rca_replay import replay
from test_rca_combined_policy import policy_case
from test_rca_component_guidance import component_case


@pytest.mark.parametrize("kind", ["xid", "sxid", "disk"])
@pytest.mark.parametrize("budget", [32768, 131072])
async def test_scoped_report_does_not_prefetch_optional_queries(kind, budget):
    case = component_case() if kind == "disk" else policy_case(kind)
    case["token_budget"] = budget
    outcome = await replay(case)
    assert len(outcome["query_calls"]) == 1
    evaluation = outcome["output"]["result"]["quality"]["rca_evaluation"]
    assert evaluation["investigation"]["stop_reason"] == "goal_achieved"
    assert [call["stage"] for call in outcome["model_calls"]] == [
        "synthesis",
        "analysis_review",
        "report_writing",
    ]
