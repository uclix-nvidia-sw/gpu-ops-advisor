"""Distinguish direct uncertainty from nonuse claims without changing facts."""

from copy import deepcopy
import json
from unittest.mock import AsyncMock

import pytest

from ops_agent.namespace_advice import (
    AdviceValidationError,
    candidates,
    validate_advice,
)
from ops_agent.report_interpretation import (
    interpret_report,
    payload_for,
    validate_reasoned_advice,
    writing_context,
)
from test_namespace_advice import topic, writer_section


def check(fact, text):
    return validate_reasoned_advice(
        {"advice": [{"fact_id": fact["fact_id"], "summary": text}]},
        {"findings": [fact]},
    )


@pytest.mark.parametrize("activity", [0, 1])
@pytest.mark.parametrize(
    "text",
    [
        "GPU 미사용을 단정할 수 없습니다.",
        "GPU 미사용인지는 확인되지 않았습니다.",
        "GPU 미사용 여부는 알 수 없습니다.",
        "GPU를 사용하지 않았다고 판단할 수 없습니다.",
        "GPU를 사용하지 않았는지는 알 수 없습니다.",
        "GPU를 쓰지 않았다고 단정할 수 없습니다.",
        "GPU 사용이 없었음을 확인할 수 없습니다.",
        "관측값만으로 실제 사용 여부를 판단할 수 없습니다.",
    ],
)
def test_direct_uncertainty_passes_without_editing_prose_or_facts(activity, text):
    fact = candidates(topic(activity=activity))[0]
    before = deepcopy(fact)
    accepted = check(fact, text)
    assert accepted["advice"][0]["summary"].startswith(text + " ")
    assert fact == before


@pytest.mark.parametrize("activity", [0, 1])
@pytest.mark.parametrize(
    "text",
    [
        "GPU는 미사용입니다.",
        "GPU를 사용하지 않았습니다.",
        "GPU 사용이 없었습니다.",
        "활동이 없었습니다.",
        "GPU는 미사용입니다. 원인은 단정할 수 없습니다.",
        "GPU는 미사용이지만 원인은 알 수 없습니다.",
        "GPU 미사용의 원인을 단정할 수 없습니다.",
        "GPU 미사용으로 인한 영향을 알 수 없습니다.",
        "GPU 미사용이 아님을 단정할 수 없습니다.",
        "GPU 미사용을 단정할 수 없다는 설명은 틀렸습니다.",
        "GPU는 미사용입니다. GPU 미사용을 단정할 수 없습니다.",
        "GPU 미사용을 단정할 수 없습니다. GPU는 미사용입니다.",
        "GPU 사용이 없었음을 관측했지만 원인은 알 수 없습니다.",
    ],
)
def test_uncertain_cause_or_added_denial_does_not_hide_nonuse_claim(activity, text):
    fact = candidates(topic(activity=activity))[0]
    with pytest.raises(
        ValueError,
        match="observed_zero_is_not_proof_of_nonuse|low_activity_is_not_zero_activity",
    ):
        check(fact, text)


@pytest.mark.parametrize("activity", [0, 1])
@pytest.mark.parametrize(
    "text",
    [
        "활동이 없었다고 단정할 수 없습니다.",
        "활동이 없었는지는 알 수 없습니다.",
        "활동이 없었는지는 확인되지 않았습니다.",
    ],
)
def test_activity_absence_uncertainty_respects_positive_observation(activity, text):
    fact = candidates(topic(activity=activity))[0]
    before = deepcopy(fact)
    if activity > 0:
        with pytest.raises(ValueError, match="low_activity_is_not_zero_activity"):
            check(fact, text)
    else:
        accepted = check(fact, text)
        assert accepted["advice"][0]["summary"].startswith(text + " ")
    assert fact == before


@pytest.mark.parametrize(
    "problem,text,stage,violation,instruction",
    [
        ("empty", "", "raw_reason", "empty", "빈 이유문"),
        ("english", "private model output", "raw_reason", "missing_korean", "한국어"),
        (
            "length",
            "관측 내용입니다." * 12,
            "composed_prose",
            "prose_length",
            "prose_max_chars",
        ),
        (
            "nonuse",
            "GPU는 미사용입니다.",
            "composed_summary",
            "nonuse_claim",
            "실제 사용 여부",
        ),
    ],
)
async def test_failure_details_and_repair_follow_the_actual_violation(
    problem, text, stage, violation, instruction, caplog
):
    result = {"topics": [topic()], "quality": {}, "time_range": {}}
    before = deepcopy(result["topics"])
    wire = payload_for(result)
    fact = wire["topics"][0]["findings"][0]
    valid = {"sections": [writer_section(wire["topics"][0]["findings"])]}
    invalid = deepcopy(valid)
    invalid["sections"][0]["advice"][0]["summary"] = text
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [invalid, {"advice": valid["sections"][0]["advice"]}]

    await interpret_report(result, llm)

    failure = result["quality"]["report"]["failures"][0]
    detail = failure["namespace_errors"][0]
    assert detail == {
        "reason": "observed_zero_is_not_proof_of_nonuse"
        if problem == "nonuse"
        else "invalid_namespace_advice_text",
        "fact_id": fact["fact_id"],
        "kind": fact["kind"],
        "field": "summary",
        "stage": stage,
        "violation_kind": violation,
        **(
            {"measured_chars": detail["measured_chars"], "limit_chars": 252}
            if problem == "length"
            else {}
        ),
    }
    if problem == "length":
        assert (
            detail["measured_chars"] - detail["limit_chars"]
            == len(text) - writing_context(fact)["prose_max_chars"]
        )
    request = llm.complete.call_args.args[1]["summary_repair"][0]
    assert instruction in request["validation_error"]
    if problem in {"empty", "english"}:
        assert "줄이세요" not in request["validation_error"]
    assert result["narrative_status"] == "complete"
    assert llm.complete.call_count == 2
    assert result["topics"] == before
    if text:
        assert text not in json.dumps(failure, ensure_ascii=False)
        assert text not in caplog.text


async def test_same_code_distinguishes_two_failures_and_keeps_fallback():
    result = {"topics": [topic()], "quality": {}, "time_range": {}}
    before = deepcopy(result["topics"])
    wire = payload_for(result)
    first = {"sections": [writer_section(wire["topics"][0]["findings"])]}
    item = first["sections"][0]["advice"][0]
    item["summary"] = ""
    second = {"advice": [{**item, "summary": "private model output"}]}
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [first, second]
    await interpret_report(result, llm)
    failures = result["quality"]["report"]["failures"]
    assert [f["reason"] for f in failures] == ["invalid_namespace_advice_text"] * 2
    assert [f["namespace_errors"][0]["violation_kind"] for f in failures] == [
        "empty",
        "missing_korean",
    ]
    assert result["narrative_status"] == "failed"
    assert result["quality"]["report"]["method"] == "deterministic_fallback"
    assert result["topics"] == before
    assert "private model output" not in json.dumps(result)


async def test_incident_error_does_not_discard_namespace_failure_details():
    from test_report_interpretation import result as base_result, reply_for

    result = base_result.__wrapped__()
    result["topics"][0] = topic()
    result["topics"].reverse()
    first = reply_for(payload_for(result))
    first["sections"][0]["meaning"] = "사건은 3건입니다."
    item = first["sections"][1]["advice"][0]
    item["summary"] = ""
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [first, None]
    await interpret_report(result, llm)
    first_failure = result["quality"]["report"]["failures"][0]
    assert first_failure["reason"] == "unsupported_prose"
    assert first_failure["topic_id"] == "incident_summary"
    assert first_failure["namespace_errors"][0]["violation_kind"] == "empty"
    assert first_failure["namespace_errors"][0]["fact_id"] == item["fact_id"]


def test_diagnostic_excludes_noncanonical_identifiers():
    exc = AdviceValidationError(
        "invalid_namespace_advice_text",
        {"fact_id": "https://private.example/key", "kind": "private-data"},
        "raw_reason",
        "empty",
        "빈 설명입니다",
    )
    assert "fact_id" not in exc.advice_error and "kind" not in exc.advice_error
    assert "private" not in json.dumps(exc.advice_error)


@pytest.mark.parametrize(
    "text,violation",
    [
        (None, "not_string"),
        ("관측" * 181, "summary_length"),
        ("관측\n설명", "line_break"),
    ],
)
def test_outer_summary_diagnostics_keep_original_error_code(text, violation):
    fact = candidates(topic())[0]
    with pytest.raises(
        AdviceValidationError, match="concise_namespace_summary_required"
    ) as caught:
        validate_advice(
            {"advice": [{"fact_id": fact["fact_id"], "summary": text}]},
            {"findings": [fact]},
        )
    assert caught.value.advice_error["violation_kind"] == violation
    if violation == "summary_length":
        assert caught.value.advice_error["measured_chars"] == 362
        assert caught.value.advice_error["limit_chars"] == 360


@pytest.mark.parametrize(
    "case",
    [
        "capacity_review",
        "schedule_candidate",
        "resident_memory",
        "repeated_activity",
        "relative_activity",
        "queue-placement",
        "queue-preparation",
        "queue-unknown",
        "batch-complete",
        "batch-placement",
        "batch-preparation",
        "batch-unknown",
    ],
)
def test_uncertainty_and_exact_length_boundary_across_action_branches(case):
    from test_ops_reason_action import fact_for

    fact = fact_for(case, "none")
    assert check(fact, "GPU 미사용을 단정할 수 없습니다.")["advice"]
    with pytest.raises(ValueError, match="observed_zero_is_not_proof_of_nonuse"):
        check(fact, "GPU는 미사용입니다. 원인은 단정할 수 없습니다.")
    budget = writing_context(fact)["prose_max_chars"]
    text = "관측" + " " * (budget - len("관측됐습니다.")) + "됐습니다."
    assert len(text) == budget
    assert check(fact, text)["advice"]
    with pytest.raises(AdviceValidationError) as caught:
        check(fact, text.replace("관측", "관측 ", 1))
    assert caught.value.advice_error["violation_kind"] == "prose_length"
    assert (
        caught.value.advice_error["measured_chars"]
        == caught.value.advice_error["limit_chars"] + 1
    )
