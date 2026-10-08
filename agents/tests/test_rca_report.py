import copy

import pytest

from agent_common.llm import RemoteUncertain
from rcca_agent.report import write_report, TITLES


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply", [{"fact_ids": []}, {"fact_ids": ["invented"]}, "prose"]
)
async def test_editor_rejection_preserves_successful_analysis(reply):
    result = dict(
        result_status="partial",
        termination_reason="missing_data",
        cause_candidates=[
            dict(
                claim="PCIe 경로 조사 필요",
                causal_status="candidate",
                supporting_refs=["log-1"],
            )
        ],
        recommendations=[],
        missing_inputs=["normalized_health"],
        limitations=[],
        quality={"analysis": {"status": "complete"}},
    )
    before = copy.deepcopy(result)

    class Model:
        configured = True

        async def complete(self, system, payload):
            return reply

    await write_report(
        result, {"incident_time": "2026-10-08T00:00:00Z"}, {}, [], Model()
    )
    assert result["cause_candidates"] == before["cause_candidates"]
    assert result["quality"]["analysis"] == before["quality"]["analysis"]
    assert result["quality"]["report"]["fallback_reason"] == "editor_response_rejected"
    cause = next(s for s in result["narrative"] if s["id"] == "cause")
    assert "미확정 원인 후보: PCIe 경로 조사 필요" in cause["text"]
    assert cause["evidence_refs"] == ["log-1"]
    assert result["missing_inputs"] == ["normalized_health"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "origins", [[], ["builtin"], ["published"], ["published", "builtin"]]
)
async def test_runbook_fallback_distinguishes_selection_from_fact_eligibility(origins):
    result = dict(
        result_status="partial",
        termination_reason="missing_data",
        cause_candidates=[],
        recommendations=[],
        missing_inputs=["normalized_health", "unknown_value"],
        limitations=[],
        quality={},
        runbook_revisions=[{"id": str(i), "origin": o} for i, o in enumerate(origins)],
    )
    original = copy.deepcopy(result)

    class Model:
        configured = False

    await write_report(
        result,
        {"incident_time": "2026-10-07T00:00:00Z"},
        {},
        [dict(id="selection", query_id="runbook_selection")],
        Model(),
    )
    text = "\n".join(s["text"] for s in result["narrative"])
    assert "의미 미확인" not in text
    assert "적용할 발행 Runbook이 없어" not in text
    if "builtin" in origins:
        assert "원인 판정 규칙이나 발행된 지식이 아닙니다" in text
        assert (
            "selection"
            in next(s for s in result["narrative"] if s["id"] == "limits")[
                "evidence_refs"
            ]
        )
        if "published" in origins:
            assert "발행 Runbook을 조사에 선택하고" in text
            assert "선택 기록 없이" not in text
        else:
            assert "선택 기록 없이" in text
    else:
        assert "기본 일반 조사 템플릿" not in text
    for key, value in original.items():
        if key != "quality":
            assert result[key] == value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode", ["ok", "invalid", "error", "unconfigured", "uncertain"]
)
async def test_final_report_preserves_missing_evidence_and_withheld_actions(mode):
    result = dict(
        kind="rca",
        result_status="blocked",
        termination_reason="query_failed",
        cause_candidates=[],
        recommendations=[],
        measurements=[],
        missing_inputs=["producer_contract", "approved_runbook"],
        limitations=["현재 장비 상태 미확인"],
        quality={},
    )
    original = copy.deepcopy(result)
    data = dict(incident_time="2026-09-30T00:00:00Z", target={"cluster_id": "cpc-1"})
    clues = dict(
        reason="XID 79 <script>untrusted()</script>",
        k8s_node_name="dgx01",
        provider_actions={
            "value": {"description": "", "repair_actions": ["REBOOT_SYSTEM"]}
        },
    )
    evidence = [
        dict(id="alert", query_id="incident_snapshot"),
        dict(
            id="logs",
            query_id="D09",
            tool_status="unavailable",
            quality={
                "complete": False,
                "reason": "query_failed",
                "error_code": "mcp_tool_error",
            },
        ),
    ]
    calls = []

    class Model:
        configured = mode != "unconfigured"

        async def complete(self, system, payload):
            calls.append(payload)
            if mode == "uncertain":
                raise RemoteUncertain("still running")
            if mode == "error":
                raise ValueError("bad response")
            if mode == "invalid":
                return {"fact_ids": ["invented"]}
            # Selection must not discard uncertainty, query failures or action conditions.
            return {"fact_ids": [payload["facts"][-1]["id"]]}

    if mode == "uncertain":
        with pytest.raises(RemoteUncertain):
            await write_report(result, data, clues, evidence, Model())
        return
    await write_report(result, data, clues, evidence, Model())
    assert len(calls) == (2 if mode == "invalid" else int(mode != "unconfigured"))
    assert [s["id"] for s in result["narrative"]] == list(TITLES)
    text = "\n".join(s["text"] for s in result["narrative"])
    for expected in [
        "dgx01",
        "XID 79",
        "원인은 미확정",
        "REBOOT_SYSTEM",
        "실행 적격성 미검증",
        "mcp_tool_error",
        "Runbook",
    ]:
        assert expected in text
    for key, value in original.items():
        if key != "quality":
            assert result[key] == value
    assert result["narrative_status"] == (
        "complete"
        if mode == "ok"
        else "omitted"
        if mode == "unconfigured"
        else "failed"
    )
    expected_reason = {
        "invalid": "editor_response_rejected",
        "error": "editor_exception",
        "unconfigured": "editor_not_configured",
    }.get(mode)
    assert result["quality"]["report"].get("fallback_reason") == expected_reason
    assert {r for s in result["narrative"] for r in s["evidence_refs"]} == {
        "alert",
        "logs",
    }


@pytest.mark.asyncio
async def test_missing_data_explains_unverified_semantics_without_promoting_actions():
    result = dict(
        result_status="partial",
        termination_reason="missing_data",
        cause_candidates=[],
        recommendations=[],
        missing_inputs=["causal_confirmation_evidence", "normalized_health"],
        limitations=[],
        quality={},
    )

    class Model:
        configured = False

    await write_report(
        result, {"incident_time": "2026-10-08T00:00:00Z"}, {}, [], Model()
    )
    text = "\n".join(section["text"] for section in result["narrative"])
    assert "원본 데이터가 없다는 뜻만은 아닙니다" in text
    assert "조치 적합성·수행·복구가 확인된 것은 아닙니다" in text
    assert result["result_status"] == "partial"
    assert result["recommendations"] == []
