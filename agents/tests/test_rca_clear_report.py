"""Clear scoped RCA reports: drop caveats the goal does not need, keep real ones."""

import json
from copy import deepcopy

from rca_replay import replay
from rca_replay_cases import reply, review
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


async def test_non_blocking_unknown_stays_in_diagnostics_not_report():
    result = await replay(policy_case())
    output = result["output"]["result"]
    assert "causal_confirmation_evidence" in output["missing_inputs"]
    assert "원인을 뒷받침할 추가 근거가 필요합니다" not in narrative(result)


async def test_unattributed_review_feedback_keeps_grounded_interpretation():
    # 2026-10-19 14:50 XID 79 (8d1246e8): four whole-draft critiques (alternatives,
    # omitted context) discarded an interpretation that passed grounding/identity.
    case = policy_case()
    verdict = review("revision_required")
    for key in ("grounding", "identity_time"):
        verdict["criteria"][key]["status"] = "pass"
    verdict["issues"] = [
        {
            "claim_id": None,
            "reason": "대안 원인을 함께 검토하세요.",
            "evidence_refs": {"$input": "/input_evidence_refs"},
            "suggested_resolution": "현재 증거가 대안을 판별하지 못함을 밝히세요.",
        }
    ]
    case["responses"]["analysis_review"] = [reply(verdict)]
    result = await replay(case)
    assert not result["missing_inputs"]
    evaluation = result["output"]["result"]["quality"]["rca_evaluation"]
    assert evaluation["evidence"]["execution_status"] == "complete"
    assert evaluation["evidence"]["interpretation"]["findings"]
    assert evaluation["review"]["verdict"] == "acceptable_after_feedback"
    assert evaluation["investigation"]["stop_reason"] == "goal_achieved"
    assert "변경 초안 미검토" not in narrative(result)


async def test_unattributed_issue_with_failed_grounding_still_rejects():
    case = policy_case()
    verdict = review("revision_required")
    verdict["issues"] = [
        {
            "claim_id": None,
            "reason": "근거와 맞지 않는 주장입니다.",
            "evidence_refs": {"$input": "/input_evidence_refs"},
            "suggested_resolution": "주장을 제거하세요.",
        }
    ]
    case["responses"]["analysis_review"] = [reply(verdict)]
    result = await replay(case)
    evaluation = result["output"]["result"]["quality"]["rca_evaluation"]
    assert evaluation["evidence"]["reason"] == "review_rejected_interpretation"
    assert evaluation["review"]["execution_status"] == "skipped"
    assert evaluation["investigation"]["stop_reason"] != "goal_achieved"


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
