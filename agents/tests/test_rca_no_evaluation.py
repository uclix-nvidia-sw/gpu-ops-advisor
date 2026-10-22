"""Published legacy plans cannot reactivate RCA grading or extra model calls."""

from copy import deepcopy
import pytest
from agent_common.contracts import content_hash, validate_result
from rca_replay import replay
from test_rca_combined_policy import policy_case
from test_rca_component_guidance import component_case


@pytest.mark.parametrize("kind", ["xid", "sxid", "disk"])
@pytest.mark.parametrize("mode", ["combined", "separate"])
@pytest.mark.parametrize("failure", [None, "http", "length", "budget"])
async def test_every_published_plan_uses_author_and_writer_only(
    kind, mode, failure, monkeypatch
):
    from rcca_agent import decision_policy, synthesis
    import legacy_review_fixtures as analysis_review

    def obsolete(*args, **kwargs):
        raise AssertionError("Retired evaluation stage was called")

    monkeypatch.setattr(analysis_review, "review_analysis", obsolete)
    monkeypatch.setattr(synthesis, "reserve_review_budget", obsolete, raising=False)
    for name in ("assess_policies", "finish_assessment", "model_assessment"):
        monkeypatch.setattr(decision_policy, name, obsolete, raising=False)
    case = component_case() if kind == "disk" else policy_case(kind)
    case["attempt"]["profile"]["rca"]["generation_mode"] = mode
    books = deepcopy(case["attempt"]["context"]["runbooks"])
    if failure == "http":
        case["responses"]["synthesis"] = [{"http_status": 400}]
    elif failure == "length":
        case["responses"]["synthesis"][0]["finish_reason"] = "length"
    elif failure == "budget":
        case["token_budget"] = 0
    else:
        case["token_budget"] = 131072
    result = await replay(case)
    output = result["output"]
    validate_result(output["result"], output["evidence"])
    assert case["attempt"]["context"]["runbooks"] == books
    assert not result["missing_inputs"]
    calls = result["model_calls"]
    assert [c["stage"] for c in calls] == (
        [] if failure == "budget" else ["synthesis", "report_writing"]
    )
    assert all(len(c["requests"]) == 1 for c in calls)
    for call in calls:
        assert (
            not {"review", "review_feedback", "decision_assessment", "sufficiency"}
            & call["input"].keys()
        )
    evidence = output["evidence"]
    assert not {
        "analysis_review",
        "investigation_decision",
        "evidence_evaluation",
        "investigation_plan_extension",
    } & {e["query_id"] for e in evidence}
    plan = next(
        e["snapshot"] for e in evidence if e["query_id"] == "investigation_plan"
    )
    assert "required_queries" not in plan
    assert set(plan["planned_queries"]) == set(plan["allowed_queries"])
    assert set(plan["planned_queries"]) <= {e["query_id"] for e in evidence}
    assert all(
        e["quality"].get("round", 0) == 0
        for e in evidence
        if e["query_id"].startswith("D")
    )
    quality = output["result"]["quality"]
    assert quality["analysis"]["workflow"] == "single_collection"
    assert quality["analysis"]["followups"] == 0
    assert "objective" not in quality["rca_evaluation"]["investigation"]
    assert quality["rca_evaluation"]["review"]["verdict"] is None
    assert quality["rca_evaluation"]["review"]["reason"] == "not_requested"
    record = next(e["snapshot"] for e in evidence if e["query_id"] == "rca_synthesis")
    assert "budget_allocation" not in record["diagnostics"]
    frozen = next(
        e["snapshot"] for e in evidence if e["query_id"] == "rca_result_frozen"
    )
    assert frozen["material_hash"] == content_hash(frozen["material"])
    text = str(output["result"]["narrative"])
    assert "분석 품질 검토" not in text and "조사 종료 이유" not in text
    assert output["result"]["quality"]["runbook_guidance"]
