import copy

import pytest

from agent_common.llm import RemoteUncertain
from rcca_agent.report import write_report, TITLES


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
    assert len(calls) == (mode != "unconfigured")
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
    assert {r for s in result["narrative"] for r in s["evidence_refs"]} == {
        "alert",
        "logs",
    }
