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
