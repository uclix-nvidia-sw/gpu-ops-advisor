import copy
import json
from pathlib import Path

import pytest

from agent_common.llm import RemoteUncertain
from rcca_agent.report import write_report, TITLES
from rcca_agent.collection_checks import collection_checks


@pytest.mark.asyncio
async def test_additional_checks_only_request_missing_connections_not_repeated_queries():
    class Model:
        configured = False

    evidence = [
        dict(id=q, query_id=q, tool_status="ok", quality={"complete": True})
        for q in ("D09", "D02", "D06", "D13")
    ]
    profile = {
        "query_contract": "single-query-v3-draft",
        "queries": {e["id"]: {} for e in evidence},
    }
    checks = collection_checks(
        profile,
        list(profile["queries"]),
        {e["id"]: [e] for e in evidence},
        [{"pod_uid": "pod"}],
        ["sxid:11001"],
    )
    result = dict(
        result_status="partial",
        termination_reason="missing_data",
        cause_candidates=[],
        recommendations=[],
        missing_inputs=["causal_confirmation_evidence", "normalized_health"],
        limitations=[],
        quality={"collection_checks": checks},
    )
    await write_report(
        result, {"incident_time": "2026-10-15T04:18:10Z"}, {}, evidence, Model()
    )
    sections = {s["id"]: s for s in result["narrative"]}
    assert "Fabric Manager" in sections["next"]["text"]
    assert "NVSwitch 포트" in sections["next"]["text"]
    assert "GPU–작업 연결" not in sections["next"]["text"]
    assert "자동 수집 완료" in sections["action"]["text"]
    assert "현재 장치 상태" in sections["limits"]["text"]
    assert result["recommendations"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["xid", "sxid"])
async def test_event_identity_and_time_lead_report_without_promoting_recovery(kind):
    event = dict(
        event_time="2026-10-15T04:17:48Z",
        cluster_id="cluster-a",
        target={"node": "node-a"},
        reported_device="0000:07:00",
        error_code=f"{kind}:79",
        device_mapping="inventory_match" if kind == "xid" else "unresolved",
        inventory_gpu_candidate="GPU-event" if kind == "xid" else None,
        evidence_refs=["log"],
        fact_eligible=False,
    )
    result = dict(
        result_status="partial",
        termination_reason="missing_data",
        cause_candidates=[],
        recommendations=[],
        missing_inputs=[],
        limitations=[],
        quality={"analysis": {"error_events": [event]}},
    )
    original = copy.deepcopy(event)

    class Model:
        configured = False

    await write_report(
        result, {"incident_time": "2026-10-15T04:18:10Z"}, {}, [], Model()
    )
    sections = {s["id"]: s for s in result["narrative"]}
    first = sections["problem"]["text"].split("\n\n")[0]
    assert first.startswith("2026-10-15 13:17:48 KST, cluster-a / node-a")
    assert ("GPU-event와 일치" in first) == (kind == "xid")
    assert ("NVSwitch·포트 연결 정보" in first) == (kind == "sxid")
    assert sections["problem"]["evidence_refs"] == ["log"]
    assert list(sections)[:5] == ["problem", "impact", "cause", "action", "next"]
    assert result["quality"]["analysis"]["error_events"][0] == original
    assert result["recommendations"] == []
    assert result["result_status"] == "partial"


@pytest.mark.asyncio
async def test_published_conditional_recovery_is_visible_without_eligible_action():
    book = json.loads(
        (
            Path(__file__).parents[2] / "rcca-agent/runbooks/xid/RB-XID-79.json"
        ).read_text(encoding="utf-8")
    )["content"]
    result = dict(
        result_status="partial",
        termination_reason="missing_data",
        cause_candidates=[],
        recommendations=[],
        missing_inputs=[],
        limitations=[],
        quality={},
    )

    class Model:
        configured = False

    await write_report(
        result,
        {"incident_time": "2026-10-15T04:18:10Z"},
        {},
        [
            dict(
                id="book",
                query_id="runbook",
                query_version=7,
                quality={"origin": "published"},
                snapshot=book,
            )
        ],
        Model(),
    )
    sections = {s["id"]: s for s in result["narrative"]}
    assert "RESTART_BM" in sections["action"]["text"]
    assert "bare-metal" in sections["action"]["text"]
    assert "조치 후 확인" in sections["action"]["text"]
    assert "CONTACT_SUPPORT" in sections["action"]["text"]
    assert sections["action"]["evidence_refs"] == ["book"]
    assert "복구 조치는 아직 없습니다" not in sections["action"]["text"]
    assert "실행 조건 충족" not in sections["action"]["text"]
    assert result["recommendations"] == []


@pytest.mark.asyncio
async def test_status_inventory_match_is_explained_without_inventing_event_time():
    result = dict(
        result_status="partial",
        termination_reason="missing_data",
        cause_candidates=[],
        recommendations=[],
        missing_inputs=[],
        limitations=[],
        quality={},
        device_observations=[
            dict(
                pci_inventory_relation="inventory_candidate_only",
                target={"node": "node-b"},
                reported_pci_addresses=["PCI:0000:07:00"],
                evidence_refs=["log"],
                gpu_candidates=[
                    {"gpu_uuid": "GPU-match", "bus_id": "00000000:07:00.0"},
                    {"gpu_uuid": "GPU-other", "bus_id": "0000:08:00.0"},
                ],
            )
        ],
    )

    class Model:
        configured = False

    await write_report(
        result, {"incident_time": "2026-10-15T04:18:10Z"}, {}, [], Model()
    )
    text = result["narrative"][0]["text"]
    assert "node-b의 오류 주소 PCI:0000:07:00" in text
    assert "GPU-match와 일치" in text
    assert "GPU-other" not in text
    assert "오류 발생 시각은 별도 이벤트 근거가 필요" in text


@pytest.mark.asyncio
async def test_operator_problem_order_preserves_alert_time_and_identity():
    result = dict(
        result_status="partial",
        termination_reason="missing_data",
        cause_candidates=[],
        recommendations=[],
        missing_inputs=[],
        limitations=[],
        quality={
            "analysis": {
                "reported_errors": [{"error_code": "xid:79", "evidence_refs": ["log"]}]
            }
        },
    )

    class Model:
        configured = True

        async def complete(self, system, payload):
            return {"fact_ids": [f["id"] for f in reversed(payload["facts"])]}

    await write_report(
        result,
        {
            "incident_time": "2026-10-12T05:00:00Z",
            "target": {"node": "fixture-node", "gpu_uuid": "fixture-gpu"},
        },
        {"reason": "raw XID 79 event"},
        [{"id": "alert", "query_id": "incident_snapshot"}],
        Model(),
    )
    problem = result["narrative"][0]
    paragraphs = problem["text"].split("\n\n")
    assert paragraphs[0] == "XID 79 오류가 보고된 것을 확인했습니다."
    assert paragraphs[1] == "대상\n노드: fixture-node"
    assert "사건 기준 시각: 2026-10-12T05:00:00Z" in paragraphs[2]
    assert "오류 발생 시각은 별도 이벤트 근거가 필요합니다" in paragraphs[2]
    assert "raw XID 79 event" in paragraphs[3]
    assert "fixture-gpu" in paragraphs[4]
    assert set(problem["evidence_refs"]) == {"log", "alert"}
    assert result["result_status"] == "partial"


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
    assert [s["id"] for s in result["narrative"]] == [
        k for k in TITLES if k != "guidance"
    ]
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


@pytest.mark.asyncio
@pytest.mark.parametrize("state_missing", [False, True])
@pytest.mark.parametrize("unverified", [False, True])
async def test_report_explains_only_observed_gaps(state_missing, unverified):
    result = dict(
        result_status="partial",
        termination_reason="missing_data",
        cause_candidates=[],
        recommendations=[],
        limitations=[],
        missing_inputs=["causal_confirmation_evidence", "unknown_value"]
        + (["normalized_health"] if state_missing else []),
        quality={
            "analysis": {
                "reported_errors": [{"error_code": "xid:79", "evidence_refs": ["log"]}]
            }
        },
        device_observations=[
            dict(
                time_basis="loki_recorded_at",
                fact_eligible=False,
                evidence_refs=["log"],
            )
        ]
        if unverified
        else [],
    )
    before = copy.deepcopy(result)

    class Model:
        configured = False

    await write_report(
        result, {"incident_time": "2026-10-12T00:00:00Z"}, {}, [], Model()
    )
    sections = {s["id"]: s for s in result["narrative"]}
    assert "XID 79 오류가 보고된 것을 확인했습니다." in sections["problem"]["text"]
    text = sections["next"]["text"]
    assert "실제 원인은 확정하지 못했습니다" in text
    assert ("현재 장치 상태는 검증하지 못했습니다" in text) == state_missing
    assert ("수집된 로그 중 상태 의미가 미검증인 관측" in text) == unverified
    assert ("log" in sections["next"]["evidence_refs"]) == unverified
    assert "로그의 생산자 계약·관측 시각·장비 신원과" not in text
    assert "causal_confirmation_evidence" not in text
    assert "unknown_value" not in text
    for key in (
        "missing_inputs",
        "device_observations",
        "result_status",
        "cause_candidates",
    ):
        assert result[key] == before[key]
