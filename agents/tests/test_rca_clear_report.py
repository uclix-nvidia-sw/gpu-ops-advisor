"""Clear scoped RCA reports: drop caveats the goal does not need, keep real ones."""

import json
from copy import deepcopy

import pytest

from agent_common.rca_evaluation import review_scope_status

from rca_replay import replay
from test_rca_combined_policy import policy_case


def narrative(result):
    return json.dumps(result["output"]["result"]["narrative"], ensure_ascii=False)


def with_healthy_baseline(case):
    # 2026-10-19 14:50 XID 79 (8d1246e8): 29 "Healthy" baseline reports, unmapped by
    # the Fleet contract, raised unknown_value although the error report was valid.
    values = case["queries"][0]["response"]["data"]["result"][0]["values"]
    at, raw = values[0]
    healthy = json.loads(raw)
    healthy["attributes"].update(health="Healthy", reason="XIDComponent is healthy")
    values.append([str(int(at) + 30 * 10**9), json.dumps(healthy)])
    return case


async def test_healthy_baseline_does_not_mark_error_values_unknown():
    result = await replay(with_healthy_baseline(policy_case()))
    assert not result["missing_inputs"]
    output = result["output"]["result"]
    assert any(
        row["raw_health"] == "Healthy" and row["normalized_health"] == "unknown"
        for row in output["device_observations"]
    )
    assert "unknown_value" not in output["missing_inputs"]
    assert "의미 또는 유효성이 미확인" not in narrative(result)


def test_problem_names_unique_inventory_gpu():
    from rcca_agent.report_observations import summarize_reports

    event = {
        "status": "reported_event",
        "time_basis": "producer_event_time",
        "event_time": "2026-10-19T05:47:04+00:00",
        "evidence_refs": ["d09"],
        "reported_device": "PCI:0000:0f:00",
        "inventory_gpu_candidate": "GPU-e3724632",
        "device_mapping": "inventory_match",
        "error_code": "xid:79",
        "cluster_id": "cpc-1",
        "component": "accelerator-nvidia-error-xid",
        "target": {"node": "dgx01"},
    }
    data = {
        "target": {"node": "dgx01", "cluster_id": "cpc-1"},
        "time_range": {
            "start": "2026-10-19T05:18:10Z",
            "end": "2026-10-19T05:50:47Z",
        },
    }
    rows = summarize_reports([], [event], data)
    text = " ".join(row["text"] for row in rows)
    assert "PCI:0000:0f:00" in text
    assert "같은 호스트 GPU 재고 대응 GPU-e3724632" in text
    unresolved = dict(deepcopy(event), device_mapping="unresolved")
    rows = summarize_reports([], [unresolved], data)
    assert "GPU-e3724632" not in " ".join(row["text"] for row in rows)


def _review(verdict, unattributed, **statuses):
    criteria = {
        key: {"status": statuses.get(key, "pass")}
        for key in ("grounding", "identity_time", "limitations", "alternatives")
    }
    return {
        "execution_status": "complete",
        "verdict": verdict,
        "criteria": criteria,
        **({} if unattributed is None else {"unattributed_issues": unattributed}),
    }


@pytest.mark.parametrize(
    "review,expected",
    [
        (_review("acceptable", False), "satisfied"),
        (_review("acceptable", False, alternatives="needs_revision"), "satisfied"),
        (
            _review("acceptable_after_feedback", False, grounding="needs_revision"),
            "satisfied",
        ),
        (
            _review("acceptable_after_feedback", True, limitations="needs_revision"),
            "unknown",
        ),
        # Older records lack the flag; never assume their issues were resolved.
        (
            _review("acceptable_after_feedback", None, grounding="needs_revision"),
            "unknown",
        ),
        (_review("undetermined", False, limitations="undetermined"), "unknown"),
        ({"execution_status": "skipped", "verdict": None}, "unknown"),
    ],
)
def test_review_scope_status(review, expected):
    assert review_scope_status(review) == expected
