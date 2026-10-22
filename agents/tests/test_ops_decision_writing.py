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
    from ops_agent.report_interpretation import writing_context

    sent = writing_context(fact)
    expected = deepcopy(context)
    expected["decision"].pop("option")
    assert {
        k: v
        for k, v in sent.items()
        if k not in {"writing_checks", "required_prose_terms", "prose_max_chars"}
    } == expected
    assert sent["writing_checks"]
    assert 0 < sent["prose_max_chars"] <= 220
    import re

    combined = "가" * sent["prose_max_chars"] + " " + sent["summary_start"]
    assert len(combined) <= 360
    assert len(re.sub(r"\{\{[a-z_]+\}\}", "", combined)) <= 220
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


@pytest.mark.parametrize("origin", ["schedule", "manual"])
async def test_initial_and_repair_input_supply_bounds_without_finished_advice(origin):
    from unittest.mock import AsyncMock

    from ops_agent.report_interpretation import interpret_report, payload_for

    result = {
        "topics": [pattern_topic([70, 80, 20, 25])],
        "time_range": {},
        "quality": {},
        "limitations": [],
        "report_origin": origin,
    }
    before = deepcopy(result)
    fact = payload_for(result)["topics"][0]["findings"][0]
    context = summary_context(fact)
    requests = []

    async def reply(system, payload, *args, **kwargs):
        assert "decision.option" not in system
        requests.append(payload)
        summary = context["summary_start"]
        if len(requests) == 2:
            summary = (
                "활동률이 낮았던 구간에 작업 일부의 시작 시간을 조정할지, "
                "마감·예약·가용 GPU·메모리 요구를 확인한 뒤 시범 실행을 검토하세요. "
                + summary
            )
            return {"advice": [{"fact_id": fact["fact_id"], "summary": summary}]}
        return {
            "sections": [
                {
                    "topic_id": "namespace_usage",
                    "advice": [{"fact_id": fact["fact_id"], "summary": summary}],
                }
            ]
        }

    llm = AsyncMock(configured=True)
    llm.complete.side_effect = reply
    await interpret_report(result, llm)
    assert len(requests) == 2
    first = requests[0]["topics"][0]["findings"][0]
    repaired = requests[1]["summary_repair"][0]
    for item in (first, repaired):
        assert "option" not in item["decision"]
        assert item["decision"] == {
            key: value for key, value in context["decision"].items() if key != "option"
        }
        assert item["required_summary_tokens"] == context["required_summary_tokens"]
        assert item["summary_tokens"] == context["summary_tokens"]
        assert context["decision"]["option"] not in str(item)
    assert requests[0]["response_shape"]["sections"][0]["advice"][0]["summary"] == ""
    assert requests[1]["response_shape"]["advice"][0]["summary"] == ""
    assert result["quality"]["report"]["reason"] == "repaired"
    assert result["topics"] == before["topics"]
