"""Regressions from the 2026-10-19 production review, with synthetic identities."""

from copy import deepcopy

import pytest

from rcca_agent.analysis_review import analysis_draft, review_payload
from rcca_agent.synthesis_context import bounded_context
from rcca_agent.report_writer import report_sources
from rca_replay import replay
from test_rca_combined_policy import policy_case
from test_rca_component_guidance import component_case


def test_unresolved_criterion_is_an_assessment_not_an_assertion():
    interpretation = {
        "criterion_assessments": [
            {
                "criterion_id": "book:bounded_conclusion",
                "status": "unknown",
                "evidence_refs": [],
                "finding_refs": [],
            }
        ]
    }
    before = deepcopy(interpretation)
    draft = analysis_draft([], [], [], {}, interpretation)
    assert not draft["claims"]
    assert (
        review_payload(draft, {}, [])["draft"]["unresolved_assessments"]
        == before["criterion_assessments"]
    )
    assert interpretation == before


@pytest.mark.parametrize("kind", ["xid", "sxid", "disk"])
async def test_no_cause_is_not_replaced_by_generic_symptom_with_independent_review(
    kind,
):
    case = component_case() if kind == "disk" else policy_case(kind)
    criterion = case["responses"]["synthesis"][0]["response"]["interpretation"][
        "criterion_assessments"
    ][0]
    criterion.update(status="unknown", evidence_refs=[], finding_refs=[])
    # The independent review, not the author self-assessment, decides completion.
    outcome = await replay(case)
    result = outcome["output"]["result"]
    assert not result["cause_candidates"]
    assert (
        result["quality"]["rca_evaluation"]["investigation"]["stop_reason"]
        == "goal_achieved"
    )
    assert len(outcome["query_calls"]) == 1
    assert [c["stage"] for c in outcome["model_calls"]] == [
        "synthesis",
        "analysis_review",
        "report_writing",
    ]
    assert all(len(c["requests"]) == 1 for c in outcome["model_calls"])
    frozen = next(
        entry["snapshot"]["material"]
        for entry in outcome["output"]["evidence"]
        if entry["query_id"] == "rca_result_frozen"
    )
    definitions = [
        row
        for row in report_sources(frozen)
        if row["section"] == "cause" and row["fixed"]
    ]
    assert definitions
    cause = next(row["text"] for row in result["narrative"] if row["id"] == "cause")
    assert cause == "\n\n".join(row["text"] for row in definitions)


def test_inventory_order_does_not_consume_model_budget_twice():
    inventory = [
        {"gpu_uuid": "gpu-a", "bus_id": "00:01.0"},
        {"gpu_uuid": "gpu-b", "bus_id": "00:02.0"},
    ]
    payload = {
        "device_observations": [
            {"gpu_candidates": inventory, "evidence_refs": ["e"]},
            {"gpu_candidates": list(reversed(inventory)), "evidence_refs": ["e"]},
        ]
    }
    before = deepcopy(payload)
    view = bounded_context(payload, 16000)
    assert len(view["gpu_inventories"]) == 1
    assert payload == before
