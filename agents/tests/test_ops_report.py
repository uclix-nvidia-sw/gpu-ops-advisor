import copy

import pytest

from agent_common.artifacts import render
from ops_agent.report import write_report


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", ["valid", "invalid", "unconfigured"])
@pytest.mark.parametrize("value", [None, 0])
async def test_final_report_preserves_unknown_zero_and_fallback(reply, value):
    result = dict(
        time_range={"start": "2026-09-30T00:00:00Z", "end": "2026-09-30T01:00:00Z"},
        scope={"clusters": [{"cluster_id": "fixture"}]},
        result_status="blocked" if value is None else "partial",
        measurements=[],
        quality={},
        limitations=["<script>untrusted</script>"],
        topics=[
            dict(
                topic_id="O09",
                status="partial",
                facts=[],
                recommendations=[],
                evidence_refs=["e1"],
                missing_inputs=["expected_inventory_missing"],
                metrics=[
                    dict(
                        id="O09.gpu_energy",
                        value=value,
                        unit="kWh",
                        method="integral",
                        quality={},
                        evidence_refs=["e1"],
                    )
                ],
            )
        ],
    )
    before = copy.deepcopy(result)

    class Model:
        configured = reply != "unconfigured"
        calls = 0

        async def complete(self, system, payload):
            self.calls += 1
            return {
                "fact_ids": [
                    payload["facts"][0]["id"] if reply == "valid" else "invented"
                ]
            }

    model = Model()
    await write_report(result, model)
    assert model.calls == (reply != "unconfigured")
    assert len(result["narrative"]) == 5
    assert (
        result["topics"] == before["topics"]
        and result["result_status"] == before["result_status"]
    )
    assert all(section["text"] for section in result["narrative"])
    assert result["quality"]["report"]["method"] == (
        "llm_prioritized" if reply == "valid" else "deterministic_fallback"
    )
    text = " ".join(section["text"] for section in result["narrative"])
    assert "expected_inventory_missing" in text
    assert ("계산 가능한 운영 수치가 없습니다" in text) == (value is None)
    if value == 0:
        assert "0 kWh" in text
    page = render(result)["html"].decode()
    assert "분석 범위와 결과" in page and "&lt;script&gt;" in page
    assert "<script>" not in page


@pytest.mark.asyncio
async def test_cluster_summary_narrative_keeps_unlabeled_observation_limit():
    from types import SimpleNamespace
    from test_namespace_usage import inventory, report
    from test_report_observation import DATA, row

    topic = report({"D01": [inventory([row({"uuid": "gpu-1"}, "90")], "cpc-1")]})
    result = dict(
        time_range=DATA["time_range"],
        scope=DATA["scope"],
        topics=[topic],
        result_status=topic["status"],
        quality={},
        limitations=[],
    )
    await write_report(result, SimpleNamespace(configured=False))
    text = " ".join(section["text"] for section in result["narrative"])
    assert "클러스터 관측 GPU: 1" in text
    assert "클러스터 연결 확인 GPU: 0" in text
    assert "Pod 연결 라벨 없는 GPU: 1" in text
    assert "유휴 상태나 회수 가능 여부는 확인되지" in text
    assert result["result_status"] == "ready"


@pytest.mark.asyncio
async def test_prerequisite_and_transport_failure_are_explained_without_rewriting_values():
    from types import SimpleNamespace

    result = dict(
        time_range={"start": "2026-10-01T00:00:00Z", "end": "2026-10-02T00:00:00Z"},
        scope={"clusters": [{"cluster_id": "fixture"}]},
        result_status="blocked",
        quality={},
        limitations=[],
        topics=[
            dict(
                topic_id="O04",
                status="blocked",
                metrics=[],
                recommendations=[],
                evidence_refs=["d08", "d06"],
                missing_inputs=[
                    "allocation_contract_missing",
                    "incomplete_observation",
                ],
            )
        ],
    )
    before = copy.deepcopy(result["topics"])
    await write_report(result, SimpleNamespace(configured=False))
    text = " ".join(s["text"] for s in result["narrative"])
    assert "검증된 GPU 할당 이력이 부족" in text
    assert "조회 실패 또는 일부 기간" in text
    assert result["topics"] == before
    assert result["result_status"] == "blocked"


@pytest.mark.asyncio
async def test_operator_report_summarizes_checks_without_repeating_all_metrics():
    from types import SimpleNamespace

    metrics = [
        dict(
            id=f"O08.observed_low_activity_seconds.{i}",
            method="verified_interval",
            value=1800,
            unit="seconds",
            quality={},
            evidence_refs=["e1"],
        )
        for i in range(40)
    ]
    findings = [
        dict(
            id=f"O08.check.{i:02}",
            priority=i,
            text=f"확인 대상 {i}",
            next_check=f"작업 목적 확인 {i}",
            value_refs=[m["id"]],
            evidence_refs=["e1"],
        )
        for i, m in enumerate(metrics)
    ]
    topic = dict(
        topic_id="O08",
        status="ready",
        metrics=metrics,
        findings=findings,
        recommendations=[],
        missing_inputs=[],
        evidence_refs=["e1"],
    )
    result = dict(
        time_range={"start": "2026-10-01T00:00:00Z", "end": "2026-10-02T00:00:00Z"},
        scope={"clusters": []},
        versions={"criteria": "1.3"},
        topics=[topic],
        measurements=[],
        quality={},
        limitations=[],
        result_status="ready",
    )
    before = copy.deepcopy(topic)
    await write_report(result, SimpleNamespace(configured=False))
    text = " ".join(s["text"] for s in result["narrative"])
    assert "확인 대상 0" in text and "작업 목적 확인 4" in text
    assert "확인 대상 5" not in text and "1800 seconds" not in text
    assert "40건 중 우선 5건" in text
    assert result["topics"][0] == before
    assert result["quality"]["report"]["presentation"] == "operator_checks_v1"
    assert "먼저 확인할 운영 사항" in render(result)["html"].decode()
    assert len(render(result)["csv"].decode("utf-8-sig").splitlines()) == 41
    assert result["narrative_status"] == "omitted"


@pytest.mark.asyncio
async def test_invalid_model_cannot_replace_verified_operator_checks():
    class Model:
        configured = True

        async def complete(self, system, payload):
            return {"fact_ids": ["made-up-remediation"]}

    result = dict(
        time_range={},
        scope={},
        result_status="partial",
        quality={},
        limitations=[],
        topics=[
            dict(
                topic_id="O01",
                metrics=[],
                recommendations=[],
                missing_inputs=[],
                evidence_refs=["e1"],
                findings=[
                    dict(
                        id="node-check",
                        priority=1,
                        text="Node Ready 상태의 False 관측을 확인하세요.",
                        next_check="해당 시각의 Node 이벤트를 확인하세요.",
                        evidence_refs=["e1"],
                        value_refs=[],
                    )
                ],
            )
        ],
    )
    await write_report(result, Model())
    assert result["narrative_status"] == "failed"
    assert result["quality"]["report"]["method"] == "deterministic_fallback"
    assert "해당 시각의 Node 이벤트" in str(result["narrative"])
    assert "made-up-remediation" not in str(result["narrative"])
