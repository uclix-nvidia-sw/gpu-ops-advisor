"""Observed prose failures must not weaken evidence or prerequisite validation."""

from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from ops_agent.namespace_advice import candidates
from ops_agent.report_interpretation import (
    interpret_report,
    payload_for,
    validate_written_advice,
)
from test_namespace_advice import topic
from test_namespace_comparison_patterns import pattern_topic
from test_report_interpretation import reply_for


def queue_fact(samples=1):
    source = topic(pending=2)
    for hour in source["workloads"][0]["hours"]:
        hour.update(unscheduled_peak=0, unscheduled_samples=samples)
    return next(f for f in candidates(source) if f["kind"] == "queue_review")


@pytest.mark.parametrize("samples", [1, 240])
@pytest.mark.parametrize(
    "claim",
    [
        "미배정 Pod가 없음을 관측했으며, 관측이 불완전할 수 있습니다.",
        "미배치 Pod가 없음을 배정 완료로 단정하지 않습니다.",
        "노드 미배정이 없음을 확인했습니다.",
        "노드를 배정받지 못한 Pod가 없음을 확인했습니다.",
    ],
)
def test_nominal_absence_requires_complete_observation(samples, claim):
    fact = queue_fact(samples)
    raw = {
        "advice": [
            {
                "fact_id": fact["fact_id"],
                "summary": claim + " Pod 상태·이벤트를 점검해 대기 단계를 구분하세요.",
            }
        ]
    }
    before = deepcopy(raw)
    if samples == 1:
        with pytest.raises(ValueError, match="partial_placement_is_not_absence"):
            validate_written_advice(raw, {"findings": [fact]})
    else:
        assert validate_written_advice(raw, {"findings": [fact]})
    assert raw == before


@pytest.mark.parametrize(
    "claim",
    [
        "미배정 Pod가 없음을 단정할 수 없습니다.",
        "미배정 Pod가 없음을 확인할 수 없습니다.",
        "미배정 Pod가 없다고 단정할 수 없습니다.",
        "노드 미배정은 없었다고 판단할 수 없습니다.",
        "미배정 관측이 불완전해 실제 부재 여부는 미확인입니다.",
    ],
)
def test_unknown_absence_remains_allowed(claim):
    fact = queue_fact()
    raw = {
        "advice": [
            {
                "fact_id": fact["fact_id"],
                "summary": claim + " Pod 상태·이벤트를 점검해 대기 단계를 구분하세요.",
            }
        ]
    }
    before = deepcopy(raw)
    assert validate_written_advice(raw, {"findings": [fact]})
    assert raw == before


def relative_item(claim):
    fact = next(
        f
        for f in candidates(pattern_topic([70, 80, 20, 25]))
        if f["kind"] == "relative_activity"
    )
    raw = {
        "advice": [
            {
                "fact_id": fact["fact_id"],
                "summary": (
                    "마감·예약·가용 GPU·메모리 요구를 확인한 뒤 "
                    "작업 일부의 시작 시각 조정과 시범 실행을 검토하세요. " + claim
                ),
            }
        ]
    }
    return fact, raw


@pytest.mark.parametrize(
    "claim",
    [
        "낮은 활동을 가용 자원이나 개선 효과로 해석하지 않습니다.",
        "성능 개선을 단정하지 않습니다.",
        "처리량 개선은 단정할 수 없습니다.",
        "낮은 활동을 자원 여유나 개선 효과로 보지 않습니다.",
        "자원 여유와 성능 개선으로 해석하지 않습니다.",
        "자원 여유나 처리량 개선을 단정하지 않습니다.",
        "개선 효과를 단정하지 않습니다.",
    ],
)
def test_explicit_denial_does_not_become_a_relative_improvement_claim(claim):
    fact, raw = relative_item(claim)
    before = deepcopy(raw)
    assert validate_written_advice(raw, {"findings": [fact]})
    assert raw == before


@pytest.mark.parametrize(
    "claim",
    [
        "성능 개선을 기대합니다.",
        "개선됐지만 개선 효과로 단정하지 않습니다.",
        "개선 효과로 해석하지 않습니다. 처리량은 개선됐습니다.",
        "개선 효과로 해석하지 않는 것은 아닙니다.",
        "개선 효과로 해석하지 않을 이유가 없습니다.",
        "자원 여유가 있습니다. 자원 여유나 개선 효과로 보지 않습니다.",
        "자원 여유나 개선 효과로 보지 않는 것은 아닙니다.",
        "자원 여유나 개선 효과로 보지 않습니다. 성능 개선을 기대합니다.",
    ],
)
def test_negation_does_not_hide_another_or_double_negative_claim(claim):
    fact, raw = relative_item(claim)
    with pytest.raises(ValueError, match="conditional_relative_window_trial_required"):
        validate_written_advice(raw, {"findings": [fact]})


@pytest.mark.parametrize("missing", ["마감·", "예약·", "가용 GPU·", "메모리 요구"])
def test_allowed_denial_does_not_replace_existing_checks(missing):
    fact, raw = relative_item("개선 효과로 해석하지 않습니다.")
    raw["advice"][0]["summary"] = raw["advice"][0]["summary"].replace(missing, "")
    with pytest.raises(ValueError):
        validate_written_advice(raw, {"findings": [fact]})


@pytest.mark.parametrize("extra", [" {{activity}}", " {{private_token}}"])
def test_allowed_denial_does_not_bypass_reference_validation(extra):
    fact, raw = relative_item("개선 효과로 해석하지 않습니다.")
    raw["advice"][0]["summary"] += extra
    with pytest.raises(ValueError, match="namespace_summary_tokens_required"):
        validate_written_advice(raw, {"findings": [fact]})


@pytest.mark.parametrize("origin", ["schedule", "manual"])
@pytest.mark.parametrize("repeat_bad", [False, True])
async def test_nominal_absence_gets_one_item_repair_then_existing_fallback(
    origin, repeat_bad
):
    source = topic(pending=2)
    for hour in source["workloads"][0]["hours"]:
        hour.update(unscheduled_peak=0, unscheduled_samples=1)
    result = dict(topics=[source], quality={}, time_range={}, report_origin=origin)
    before = deepcopy(result["topics"])
    initial = reply_for(payload_for(result))
    bad = initial["sections"][0]["advice"][0]
    bad["summary"] = (
        "미배정 Pod가 없음을 관측했으며, 관측이 불완전할 수 있습니다. "
        "Pod 상태·이벤트를 점검해 대기 단계를 구분하세요."
    )
    raw = deepcopy(initial)
    fixed = deepcopy(bad)
    if not repeat_bad:
        fixed["summary"] = (
            "미배정 관측이 불완전해 배정 완료로 단정할 수 없습니다. "
            "Pod 상태·이벤트를 점검해 노드 배정 대기인지 시작 준비 중인지 구분하세요."
        )
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [initial, {"advice": [fixed]}]
    await interpret_report(result, llm)
    assert llm.complete.call_count == 2
    repair = llm.complete.call_args_list[1].args[1]["summary_repair"]
    assert [item["fact_id"] for item in repair] == [bad["fact_id"]]
    assert repair[0]["validation_error"].startswith("partial_placement_is_not_absence:")
    assert initial == raw and result["topics"] == before
    assert result["narrative_status"] == ("failed" if repeat_bad else "complete")


CAPACITY_CHECKS = "스케줄러 사유와 GPU 요청·실제 할당을 대조하고 보장량·가용 GPU·운영정책을 확인한 뒤 추가 할당을 검토하세요."
TRIAL_CHECKS = "마감·예약·대기·가용 GPU를 확인한 뒤 시작 시각을 조정할 수 있는 작업 일부의 시범 실행을 검토하세요."


@pytest.mark.parametrize(
    "field", ["target", "period", "fact_id", "writing_checks", "summary_repair"]
)
def test_literal_internal_fields_are_not_operator_prose(field):
    fact = queue_fact()
    raw = {
        "advice": [
            {
                "fact_id": fact["fact_id"],
                "summary": field
                + "의 Pod 상태·이벤트를 점검해 대기 단계를 구분하세요.",
            }
        ]
    }
    with pytest.raises(ValueError, match="internal_context_leak"):
        validate_written_advice(raw, {"findings": [fact]})


@pytest.mark.parametrize(
    "prefix",
    [
        "GPU 요청과 Pending Pod가 관측됐습니다. ",
        "Pod 상태를 확인합니다. ",
        "타깃 작업은 미확인입니다. ",
        "targeted 점검입니다. ",
    ],
)
def test_technical_terms_and_longer_words_are_not_internal_fields(prefix):
    fact = queue_fact()
    raw = {
        "advice": [
            {
                "fact_id": fact["fact_id"],
                "summary": prefix + "Pod 상태·이벤트를 점검해 대기 단계를 구분하세요.",
            }
        ]
    }
    assert validate_written_advice(raw, {"findings": [fact]})


@pytest.mark.parametrize(
    "purpose",
    [
        "",
        "자원 부족을 확인하고 ",
        "GPU 부족을 확인한 뒤 ",
        "자원 부족을 확인했습니다. ",
    ],
)
def test_capacity_checklist_and_presumed_shortage_need_a_question(purpose):
    fact = next(
        f
        for f in candidates(topic(activity=90, pending=2))
        if f["kind"] == "capacity_review"
    )
    raw = {
        "advice": [{"fact_id": fact["fact_id"], "summary": purpose + CAPACITY_CHECKS}]
    }
    with pytest.raises(ValueError, match="resource_shortage_question_required"):
        validate_written_advice(raw, {"findings": [fact]})


@pytest.mark.parametrize(
    "purpose",
    [
        "자원 부족 여부를 확인하고 ",
        "자원이 부족한지 점검하고 ",
        "GPU 요청을 충족하는지 확인하고 ",
        "GPU 요청을 충족할 노드가 있었는지 확인하고 ",
        "자원 부족을 확인할 수 없습니다. 자원 부족 여부를 확인하고 ",
        "자원 부족은 확인되지 않았습니다. GPU가 부족한지 확인하고 ",
    ],
)
def test_capacity_uncertainty_and_distinct_sequential_checks_are_allowed(purpose):
    fact = next(
        f
        for f in candidates(topic(activity=90, pending=2))
        if f["kind"] == "capacity_review"
    )
    raw = {
        "advice": [{"fact_id": fact["fact_id"], "summary": purpose + CAPACITY_CHECKS}]
    }
    before = deepcopy(raw)
    assert validate_written_advice(raw, {"findings": [fact]})
    assert raw == before


@pytest.mark.parametrize(
    "opening",
    [
        "시작 시각을 조정할 수 있는지 검토하되, ",
        "작업 일부의 시범 실행을 검토합니다. ",
        "시작 시각 조정을 검토할 수 있습니다. ",
    ],
)
def test_same_trial_review_is_not_repeated_around_prerequisites(opening):
    fact = next(f for f in candidates(topic()) if f["kind"] == "schedule_candidate")
    raw = {"advice": [{"fact_id": fact["fact_id"], "summary": opening + TRIAL_CHECKS}]}
    with pytest.raises(ValueError, match="repeated_trial_review"):
        validate_written_advice(raw, {"findings": [fact]})


@pytest.mark.parametrize(
    "opening", ["", "작업 마감은 담당자가 검토합니다. ", "예약 조건을 검토한 뒤 "]
)
def test_separate_review_purposes_are_not_duplicate_trial_reviews(opening):
    fact = next(f for f in candidates(topic()) if f["kind"] == "schedule_candidate")
    raw = {"advice": [{"fact_id": fact["fact_id"], "summary": opening + TRIAL_CHECKS}]}
    assert validate_written_advice(raw, {"findings": [fact]})


@pytest.mark.parametrize("origin", ["schedule", "manual"])
@pytest.mark.parametrize("repeat_bad", [False, True])
@pytest.mark.parametrize(
    "problem,kind,summary,code",
    [
        (
            "internal",
            "queue_review",
            "target의 period에 Pod 상태·이벤트를 점검해 대기 단계를 구분하세요.",
            "internal_context_leak",
        ),
        (
            "presumed",
            "capacity_review",
            "자원 부족을 확인하고 " + CAPACITY_CHECKS,
            "resource_shortage_question_required",
        ),
        (
            "purpose",
            "capacity_review",
            CAPACITY_CHECKS,
            "resource_shortage_question_required",
        ),
        (
            "repeated",
            "schedule_candidate",
            "시작 시각 조정을 검토하되, " + TRIAL_CHECKS,
            "repeated_trial_review",
        ),
    ],
)
async def test_prose_failures_repair_only_the_named_item_once(
    origin, repeat_bad, problem, kind, summary, code
):
    source = (
        topic(activity=90, pending=2)
        if kind == "capacity_review"
        else topic(pending=2)
        if kind == "queue_review"
        else topic()
    )
    result = dict(topics=[source], quality={}, time_range={}, report_origin=origin)
    before = deepcopy(result["topics"])
    initial = reply_for(payload_for(result))
    facts = {
        f["fact_id"]: f for t in payload_for(result)["topics"] for f in t["findings"]
    }
    bad = next(
        a
        for s in initial["sections"]
        for a in s.get("advice", [])
        if facts[a["fact_id"]]["kind"] == kind
    )
    fixed = deepcopy(bad)
    bad["summary"] = summary
    if repeat_bad:
        fixed = deepcopy(bad)
    original = deepcopy(initial)
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [initial, {"advice": [fixed]}]
    await interpret_report(result, llm)
    repair = llm.complete.call_args_list[1].args[1]["summary_repair"]
    assert llm.complete.call_count == 2
    assert [item["fact_id"] for item in repair] == [bad["fact_id"]]
    assert repair[0]["validation_error"].startswith(code + ":")
    assert initial == original and result["topics"] == before
    assert result["narrative_status"] == ("failed" if repeat_bad else "complete")
    if not repeat_bad:
        final = {
            a["fact_id"]: a["summary_parts"]["decision"]
            for s in result["narrative"]
            for a in s.get("advice", [])
        }
        assert all(
            final[a["fact_id"]] == a["summary"]
            for s in original["sections"]
            for a in s.get("advice", [])
            if a["fact_id"] != bad["fact_id"]
        )


def test_shortage_question_can_precede_the_final_conditional_judgment():
    fact = next(
        f
        for f in candidates(topic(activity=90, pending=2))
        if f["kind"] == "capacity_review"
    )
    text = "추가 할당을 검토하려면 스케줄러 사유와 GPU 요청·실제 할당을 대조해 자원 부족 여부를 확인하고 보장량·가용 GPU·운영정책을 확인한 뒤 변경 여부를 판단하세요."
    assert validate_written_advice(
        {"advice": [{"fact_id": fact["fact_id"], "summary": text}]},
        {"findings": [fact]},
    )
