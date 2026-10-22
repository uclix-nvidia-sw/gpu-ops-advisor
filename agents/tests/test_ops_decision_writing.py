"""Decision-oriented examples must remain valid under unchanged evidence guards."""

from copy import deepcopy

import pytest

from ops_agent.namespace_advice import candidates, summary_context, validate_advice
from test_namespace_advice import completed_topic, topic
from test_namespace_comparison_patterns import pattern_topic


@pytest.mark.parametrize(
    "kind,source,purpose",
    [
        ("capacity_review", lambda: topic(activity=90, pending=2), "할당 검토"),
        ("repeated_activity", lambda: pattern_topic([85, 20, 90], 2), "점검"),
        ("schedule_candidate", topic, "시범 실행 후보"),
        (
            "relative_activity",
            lambda: pattern_topic([70, 80, 20, 25]),
            "조정 시험 후보",
        ),
        ("queue_review", lambda: topic(activity=30, pending=2), "점검"),
        ("resident_memory", lambda: topic(memory=95), "새 작업 배치"),
        ("batch_progress", completed_topic, "일정 계획"),
    ],
)
@pytest.mark.parametrize("connected", [False, True])
def test_first_sentence_explains_the_allowed_operating_purpose(
    kind, source, purpose, connected
):
    original = source()
    fact = next(f for f in candidates(original) if f["kind"] == kind)
    if connected:
        fact["workload_context"] = {
            "status": "partial",
            "groups": [
                {
                    "type_status": "declared_test",
                    "workload_type": "배치 부하 모의 테스트",
                    "phase": "Pending",
                    "node_assigned": False,
                }
            ],
            "completed_type_status": "declared_test",
        }
    before = deepcopy(fact)
    context = summary_context(fact)
    first = context["decision"]["option"].split(". ", 1)[0]
    assert purpose in first
    response = {
        "advice": [
            {
                "fact_id": fact["fact_id"],
                "summary": context["decision"]["option"]
                + " "
                + context["summary_start"],
            }
        ]
    }
    assert validate_advice(response, {"findings": [fact]})["advice"]
    assert fact == before


async def test_repair_example_keeps_operating_choice_without_workload_labels():
    from unittest.mock import AsyncMock

    from ops_agent.report_interpretation import interpret_report

    result = {
        "topics": [pattern_topic([70, 80, 20, 25])],
        "time_range": {},
        "quality": {},
        "limitations": [],
    }
    requests = []

    async def reply(system, payload, *args, **kwargs):
        requests.append(payload)
        example = deepcopy(payload["response_shape"])
        if len(requests) == 1:
            for item in example["sections"][0]["advice"]:
                item["summary"] = item["summary"].split("{{target}}", 1)[-1]
        return example

    llm = AsyncMock(configured=True)
    llm.complete.side_effect = reply
    await interpret_report(result, llm)
    assert len(requests) == 2
    for item in requests[1]["response_shape"]["advice"]:
        assert "운영자는" in item["summary"]
        assert "{{target}}" in item["summary"]
    assert result["quality"]["report"]["reason"] == "repaired"
