"""Failure reports preserve scoped observations without retrying model analysis."""

from copy import deepcopy

import pytest

from agent_common.contracts import content_hash
from rcca_agent.report_observations import summarize_reports
from rcca_agent.report_writer import report_sources
from rca_replay import replay
from test_rca_combined_policy import policy_case
from test_rca_component_guidance import component_case


@pytest.mark.parametrize("kind", ["xid", "sxid", "disk"])
@pytest.mark.parametrize("failure", ["http", "invalid", "truncated"])
async def test_author_failure_keeps_reports_without_extra_calls(kind, failure):
    case = component_case() if kind == "disk" else policy_case(kind)
    if failure == "http":
        case["responses"]["synthesis"] = [{"http_status": 400}]
    elif failure == "invalid":
        case["responses"]["synthesis"] = [{"raw_text": "{broken"}]
    else:
        case["responses"]["synthesis"][0]["finish_reason"] = "length"
    outcome = await replay(case)
    assert not outcome["missing_inputs"]
    assert sum(c["matched"] for c in outcome["query_calls"]) == 1
    assert [c["stage"] for c in outcome["model_calls"]] == [
        "synthesis",
        "analysis_review",
        "report_writing",
    ]
    assert all(len(c["requests"]) == 1 for c in outcome["model_calls"])
    assert len(outcome["model_calls"][0]["requests"]) == 1
    output = outcome["output"]["result"]
    problem = next(r for r in output["narrative"] if r["id"] == "problem")
    assert "node-1" in problem["text"]
    assert "로그 기록 시각" in problem["text"]
    assert ("filesystem is read-only" if kind == "disk" else kind.upper()) in problem[
        "text"
    ]
    assert problem["evidence_refs"]
    assert "채택된 증거 해석이 없습니다" not in problem["text"]
    assert (
        output["quality"]["rca_evaluation"]["investigation"]["stop_reason"]
        != "goal_achieved"
    )
    frozen = next(
        e["snapshot"]
        for e in outcome["output"]["evidence"]
        if e["query_id"] == "rca_result_frozen"
    )
    assert content_hash(frozen["material"]) == frozen["material_hash"]
    assert frozen["material"]["reported_observations"]
    before = deepcopy(frozen["material"])
    sources = report_sources(before)
    assert before == frozen["material"]
    assert all(r["fixed"] for r in sources if r["section"] == "problem")


def test_scoped_summary_rejects_other_targets_and_preserves_report_semantics():
    report = {
        "cluster_id": "c1",
        "target": {"node": "n1"},
        "component": "disk",
        "check_status": "valid",
        "time_basis": "loki_recorded_at",
        "observed_at": "2026-10-19T01:00:00Z",
        "raw_health": "Unhealthy",
        "reason": "read-only",
        "evidence_refs": ["e1"],
        "fact_eligible": False,
    }
    data = {"target": {"cluster_id": "c1", "node": "n1"}}
    assert summarize_reports([report], [], data)
    for bad in (
        {"cluster_id": "other"},
        {"target": {"node": "other"}},
        {"check_status": "unknown"},
        {"evidence_refs": []},
        {"time_basis": "unverified"},
    ):
        assert not summarize_reports([{**report, **bad}], [], data)
    assert not summarize_reports([report], [], {**data, "identity_conflicts": ["node"]})
    rows = summarize_reports([report, {**report, "raw_health": "Healthy"}], [], data)
    assert len(rows) == 2
    assert all("상태 보고" in r["text"] and "로그 기록 시각" in r["text"] for r in rows)
    assert "회복" not in str(rows)


def test_event_summary_never_promotes_inventory_or_current_health():
    row = {
        "cluster_id": "c1",
        "target": {"node": "n1"},
        "status": "reported_event",
        "time_basis": "producer_event_time",
        "event_time": "2026-10-19T01:00:00+00:00",
        "error_code": "sxid:11001",
        "reported_device": "PCI:0000:c4:00.0",
        "evidence_refs": ["e1"],
        "inventory_gpu_candidate": "GPU-not-a-switch",
    }
    rows = summarize_reports([], [row], {"target": {"cluster_id": "c1", "node": "n1"}})
    assert "sxid:11001" in str(rows) and "PCI:0000:c4:00.0" in str(rows)
    assert "생산자 이벤트 시각" in str(rows)
    assert "GPU-not-a-switch" not in str(rows)


@pytest.mark.parametrize("kind", ["xid", "sxid", "disk"])
async def test_author_and_writer_failure_keep_facts_and_conditional_guidance(kind):
    case = component_case() if kind == "disk" else policy_case(kind)
    case["responses"]["synthesis"] = [{"http_status": 400}]
    case["responses"]["report_writing"] = [{"http_status": 400}]
    outcome = await replay(case)
    result = outcome["output"]["result"]
    assert not outcome["missing_inputs"]
    assert sum(c["matched"] for c in outcome["query_calls"]) == 1
    assert len(outcome["model_calls"]) == 3
    assert all(len(c["requests"]) == 1 for c in outcome["model_calls"])
    assert result["quality"]["report"]["method"] == "deterministic_fallback"
    problem = next(r for r in result["narrative"] if r["id"] == "problem")
    assert "node-1" in problem["text"] and problem["evidence_refs"]
    assert "분석 처리 상태" in str(result["narrative"])
    for entry in result["quality"]["runbook_guidance"]:
        if entry["report_applicability"] == "reference_only":
            continue
        for check in entry["guidance"]["next_checks"]:
            assert check["text"] in str(result["narrative"])


def test_verified_report_summary_wins_over_model_repetition_and_hides_diagnostics():
    material = {
        "evaluation": {
            "evidence": {
                "execution_status": "failed",
                "reason": "review_rejected_interpretation",
                "interpretation": {
                    "findings": [
                        {
                            "kind": "observed",
                            "statement": "오류가 반복적으로 발생했다",
                            "evidence_refs": ["e"],
                        }
                    ]
                },
            },
            "review": {},
            "investigation": {},
        },
        "reported_observations": [
            {
                "text": "node-a SXID 오류 이벤트 1건, 상태 보고 5건",
                "evidence_refs": ["e"],
            }
        ],
    }
    sources = report_sources(material)
    problem = [row for row in sources if row["section"] == "problem"]
    assert len(problem) == 1 and problem[0]["fixed"]
    assert "1건" in problem[0]["text"] and "반복" not in problem[0]["text"]
    assert not any("review_rejected_interpretation" in row["text"] for row in sources)
    assert all(
        row["section"] == "limits" for row in sources if "분석 처리 상태" in row["text"]
    )


def test_context_reports_do_not_displace_incident_in_report_body():
    material = {
        "evaluation": {},
        "reported_observations": [
            {"text": "사건 장치 bd:00 오류 이벤트 1건", "evidence_refs": ["e"]},
            {
                "text": "다른 장치 87:00 상태 보고 5건",
                "evidence_refs": ["e"],
                "context_only": True,
            },
        ],
    }
    sources = report_sources(material)
    assert all(
        "87:00" not in row["text"] for row in sources if row["section"] == "problem"
    )
    assert any("87:00" in row["text"] and row["section"] == "limits" for row in sources)


def test_reader_preserves_arbitrary_runbook_prose_without_sentence_exceptions():
    from rcca_agent.report_writer import reader_text

    for text in (
        "이번 사건의 작업 영향과 현재 접근 상태는 수집된 관측에 따라 설명합니다.",
        "새 Fleet 오류의 의미와 적용 조건을 그대로 보존합니다.",
    ):
        assert reader_text(text) == text


@pytest.mark.parametrize("code", ["xid:48", "sxid:11012", "fleet:new-error"])
def test_context_selection_respects_component_identity_and_usable_events(code):
    from rcca_agent.report_observations import event_devices_by_scope, report_scope

    event = {
        "cluster_id": "c1",
        "target": {"node": "n1"},
        "component": "device-check",
        "status": "reported_event",
        "time_basis": "producer_event_time",
        "event_time": "2026-10-19T01:00:00Z",
        "reported_device": "PCI:0000:01:00",
        "error_code": code,
        "evidence_refs": ["e1"],
    }
    state = {
        "cluster_id": "c1",
        "target": {"node": "n1"},
        "component": "device-check",
        "check_status": "valid",
        "time_basis": "loki_recorded_at",
        "observed_at": "2026-10-19T01:01:00Z",
        "raw_health": "Unhealthy",
        "reason": "reported error",
        "evidence_refs": ["e1"],
    }
    data = {"target": {"cluster_id": "c1", "node": "n1"}}
    disk = {**state, "component": "disk", "reason": "read-only filesystem"}
    summary = summarize_reports([state, disk], [event], data)
    assert next(r for r in summary if "read-only" in r["text"])["context_only"] is False
    assert (
        next(r for r in summary if "device-check" in r["text"])["context_only"] is True
    )
    for invalid in (
        {"evidence_refs": []},
        {"time_basis": "unknown"},
        {"event_time": None},
    ):
        assert all(
            not row["context_only"]
            for row in summarize_reports([state, disk], [{**event, **invalid}], data)
        )
    devices = event_devices_by_scope([event])
    for other in (
        {"cluster_id": "c2"},
        {"target": {"node": "n2"}},
        {"component": "disk"},
    ):
        assert not devices.get(report_scope({**state, **other}))
