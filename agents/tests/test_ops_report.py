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
