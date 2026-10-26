"""Reason-only writing must keep code-owned operating conditions and evidence."""

from copy import deepcopy
from unittest.mock import AsyncMock, patch
import re

import pytest

from ops_agent import report_interpretation as module
from ops_agent.namespace_advice import (
    candidates,
    decision_context,
    summary_context,
    writing_decision,
)
from test_namespace_advice import topic, completed_topic, writer_section
from test_namespace_comparison_patterns import pattern_topic


def fact_for(case, context):
    if case.startswith("batch"):
        source = completed_topic()
        if case != "batch-complete":
            for hour in source["workloads"][0]["hours"]:
                hour.update(pending_peak=2, pending_samples=240)
        kind = "batch_progress"
    elif case.startswith("queue"):
        source, kind = topic(pending=2), "queue_review"
    else:
        kind = case
        source = {
            "capacity_review": lambda: topic(activity=90, pending=2),
            "schedule_candidate": topic,
            "resident_memory": lambda: topic(memory=95),
            "repeated_activity": lambda: pattern_topic([85, 20, 90], 2),
            "relative_activity": lambda: pattern_topic([80, 80, 20, 20]),
        }[case]()
    if case.startswith(("batch-", "queue-")) and case != "batch-complete":
        phase = case.split("-", 1)[1]
        for hour in source["workloads"][0]["hours"]:
            hour.update(
                unscheduled_peak=2 if phase == "placement" else 0,
                unscheduled_samples=240 if phase != "unknown" else 238,
            )
    fact = next(f for f in candidates(source) if f["kind"] == kind)
    if context != "none":
        fact["workload_context"] = {
            "status": "partial",
            "groups": [
                {
                    "type_status": "declared_test" if context == "typed" else "unknown",
                    "workload_type": "배치 부하 모의 테스트",
                    "phase": "Pending",
                    "node_assigned": False,
                }
            ],
            "completed_type_status": "declared_test"
            if context == "typed"
            else "unknown",
        }
    return fact


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
@pytest.mark.parametrize("context", ["none", "unknown", "typed"])
def test_valid_action_branches_keep_guards_and_reason_space(case, context):
    fact = fact_for(case, context)
    before = deepcopy(fact)
    stored = decision_context(fact)
    action = writing_decision(fact)["action"]
    reason = writer_section([fact])["advice"][0]["summary"]
    sent = module.writing_context(fact)
    assert len(reason) <= sent["prose_max_chars"]
    assert "action" not in sent["decision"] and "option" not in sent["decision"]
    assert "required_checks" not in sent and "required_prose_terms" not in sent
    section = {"advice": [{"fact_id": fact["fact_id"], "summary": reason}]}
    raw = deepcopy(section)
    result = module.validate_reasoned_advice(section, {"findings": [fact]})
    item = result["advice"][0]
    assert item["summary"].startswith(reason + " " + action + " ")
    assert section == raw and fact == before and decision_context(fact) == stored
    assert item["evidence_refs"] == fact["evidence_refs"]
    assert item["decision"] == stored if "decision" in fact else "decision" not in item
    if fact["kind"] in module.PREREQUISITES:
        required = module.PREREQUISITES[fact["kind"]]
        checked, ordered = module.checked_prerequisites(action, required)
        assert checked == set(required) and ordered
        assert len(re.findall("검토|판단", action)) == 1
    else:
        assert not re.search("검토|판단", action)


@pytest.mark.parametrize(
    "peak,samples,focus,annotated",
    [
        (0, 238, "unknown", True),
        (0, 240, "preparation", False),
        (2, 238, "placement", False),
        (2, 240, "placement", False),
    ],
)
def test_partial_zero_input_keeps_values_and_positive_evidence(
    peak, samples, focus, annotated
):
    source = topic(pending=2)
    for hour in source["workloads"][0]["hours"]:
        hour.update(unscheduled_peak=peak, unscheduled_samples=samples)
    fact = next(f for f in candidates(source) if f["kind"] == "queue_review")
    before = deepcopy(fact)
    values = summary_context(fact)["summary_tokens"]
    sent = module.writing_context(fact)
    assert sent["queue_context"]["check_first"] == focus
    observed = sent["observed_values"]["unscheduled"]
    assert observed.startswith(values["{{unscheduled}}"])
    assert ("일부 표본" in observed) is annotated
    assert fact == before and summary_context(fact)["summary_tokens"] == values


@pytest.mark.parametrize("origin", ["schedule", "manual"])
@pytest.mark.parametrize("repeat_error", [False, True])
async def test_reason_repair_preserves_healthy_reasons_and_code_actions(
    origin, repeat_error
):
    result = dict(
        topics=[pattern_topic([80, 80, 20, 20, 1, 1])],
        quality={},
        time_range={},
        report_origin=origin,
    )
    before = deepcopy(result["topics"])
    payload = module.payload_for(result)
    facts = payload["topics"][0]["findings"]
    valid = writer_section(facts)
    invalid = deepcopy(valid)
    bad_id = invalid["advice"][0]["fact_id"]
    invalid["advice"][0]["summary"] = "작업의 GPU 활동률이 낮았습니다."
    patch_item = next(
        a
        for a in (invalid if repeat_error else valid)["advice"]
        if a["fact_id"] == bad_id
    )
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [{"sections": [invalid]}, {"advice": [patch_item]}]
    await module.interpret_report(result, llm)
    assert llm.complete.call_count == 2 and result["topics"] == before
    repair = llm.complete.call_args.args[1]
    assert [a["fact_id"] for a in repair["summary_repair"]] == [bad_id]
    assert "required_checks" not in repair["summary_repair"][0]
    if repeat_error:
        assert result["narrative_status"] == "failed"
    else:
        assert result["narrative_status"] == "complete"
        for item in result["narrative"][0]["advice"]:
            reason = next(
                a["summary"] for a in valid["advice"] if a["fact_id"] == item["fact_id"]
            )
            action = writing_decision(
                next(f for f in facts if f["fact_id"] == item["fact_id"])
            )["action"]
            assert item["summary_parts"]["decision"] == reason + " " + action


@pytest.mark.parametrize(
    "reason,error",
    [
        ("미배정 Pod는 없었습니다.", "partial_placement_is_not_absence"),
        ("Pod의 GPU 활동률이 낮았습니다.", "unsupported_workload_activity_attribution"),
        ("", "invalid_namespace_advice_text"),
        ("Only an English observation.", "invalid_namespace_advice_text"),
    ],
)
def test_code_action_cannot_hide_invalid_raw_reason(reason, error):
    fact = fact_for("queue-unknown", "none")
    with pytest.raises(ValueError, match=error):
        module.validate_reasoned_advice(
            {"advice": [{"fact_id": fact["fact_id"], "summary": reason}]},
            {"findings": [fact]},
        )


async def test_code_prerequisite_failure_does_not_request_model_repair():
    result = dict(topics=[topic(activity=90, pending=2)], quality={}, time_range={})
    llm = AsyncMock(configured=True)
    original = module.writing_decision

    def missing_policy(fact):
        decision = original(fact)
        decision["action"] = decision["action"].replace("·운영정책", "")
        return decision

    with patch.object(module, "writing_decision", side_effect=missing_policy):
        await module.interpret_report(result, llm)
    assert llm.complete.call_count == 0
    assert result["quality"]["report"]["reason"] == "invalid_code_advice"
    assert result["narrative_status"] == "failed"


@pytest.mark.parametrize(
    "reason,error",
    [
        (
            "예약·대기·가용 GPU를 확인하고 일부 작업의 시범 실행을 검토하세요.",
            "reason_only_namespace_summary_required",
        ),
        (
            "예약·대기·가용 GPU를 확인한 뒤 일부 작업을 시범 실행하세요.",
            "reason_only_namespace_summary_required",
        ),
        (
            "마감·예약·대기·가용 GPU를 확인한 뒤 일부 작업의 시작 시각을 조정해 시범 실행을 검토하세요.",
            "reason_only_namespace_summary_required",
        ),
    ],
)
def test_code_conditions_do_not_satisfy_raw_operating_decisions(reason, error):
    fact = fact_for("schedule_candidate", "none")
    with pytest.raises(ValueError, match=error):
        module.validate_reasoned_advice(
            {"advice": [{"fact_id": fact["fact_id"], "summary": reason}]},
            {"findings": [fact]},
        )


def test_shortage_uncertainty_is_not_an_operating_instruction():
    fact = fact_for("capacity_review", "none")
    reason = "추가 할당이 필요한지는 현재 관측만으로 판단할 수 없습니다."
    result = module.validate_reasoned_advice(
        {"advice": [{"fact_id": fact["fact_id"], "summary": reason}]},
        {"findings": [fact]},
    )
    assert result["advice"][0]["summary"].startswith(reason + " ")


@pytest.mark.parametrize(
    "case",
    [
        "capacity_review",
        "schedule_candidate",
        "resident_memory",
        "repeated_activity",
        "relative_activity",
        "queue-unknown",
        "batch-placement",
    ],
)
def test_reason_length_uses_exact_remaining_existing_limits(case):
    fact = fact_for(case, "none")
    limit = module.writing_context(fact)["prose_max_chars"]
    for extra in (0, 1):
        item = {"fact_id": fact["fact_id"], "summary": "가" * (limit + extra)}
        if extra:
            with pytest.raises(
                ValueError,
                match="invalid_namespace_advice_text|concise_namespace_summary_required",
            ):
                module.validate_reasoned_advice(
                    {"advice": [item]}, {"findings": [fact]}
                )
        else:
            assert module.validate_reasoned_advice(
                {"advice": [item]}, {"findings": [fact]}
            )


@pytest.mark.parametrize(
    "reason",
    [
        "조건 확인 없이 작업을 옮기세요.",
        "일부 작업을 실행하십시오.",
        "스케줄러 이벤트를 점검하기 바랍니다.",
        "작업을 먼저 배치해야 합니다.",
        "작업을 먼저 배치하는 것이 좋습니다.",
        "작업을 옮기는 편이 좋습니다.",
        "배치 시각을 바꿀 필요가 있습니다.",
        "이벤트 점검을 권합니다.",
        "작업 일부를 검토 대상으로 삼습니다.",
        "조건 확인 없이 작업을 옮깁니다.",
        "작업을 실행합니다.",
        "시범 실행을 검토합니다.",
        "스케줄러 기록을 점검합니다.",
        "완료 Job과 대기 Pod의 유형을 대조합니다.",
        "Pod 이벤트를 확인합니다.",
        "작업 일부는 검토 대상입니다.",
        "작업 일부를 검토 대상으로 분류합니다.",
        "작업을 배치했습니다.",
        "시작 시각을 조정하겠습니다.",
        "작업 시각을 변경합니다.",
        "GPU를 할당합니다.",
        "GPU 요청을 늘립니다.",
        "작업을 옮길 예정입니다.",
        "작업을 실행할 수 있습니다.",
        "시작 시각 조정이 필요합니다.",
        "대기 Pod의 상태와 스케줄러 이벤트를 점검해 대기 단계를 구분하세요.",
        "완료 Job과 대기 Pod의 작업 유형을 대조하세요.",
        "작업을 옮깁니다. 효과는 판단할 수 없습니다.",
        "작업을 실행하고 효과는 판단할 수 없습니다.",
        "GPU를 늘려서 대기 여부는 확인되지 않았습니다.",
    ],
)
@pytest.mark.parametrize(
    "case",
    [
        "schedule_candidate",
        "relative_activity",
        "queue-unknown",
        "batch-unknown",
        "capacity_review",
    ],
)
def test_raw_actions_recommendations_and_classifications_have_one_reason_error(
    case, reason
):
    fact = fact_for(case, "none")
    section = {"advice": [{"fact_id": fact["fact_id"], "summary": reason}]}
    original = deepcopy(section)
    with patch.object(
        module, "validate_written_advice", wraps=module.validate_written_advice
    ) as complete:
        with pytest.raises(
            ValueError, match="^reason_only_namespace_summary_required:"
        ):
            module.validate_reasoned_advice(section, {"findings": [fact]})
    complete.assert_not_called()  # Never ask the model to fill the old prose conditions.
    assert section == original


@pytest.mark.parametrize(
    "reason",
    [
        "추가 할당이 필요한지는 현재 관측만으로 판단할 수 없습니다.",
        "부족 여부는 확인되지 않았습니다.",
        "자원 부족 여부는 확인되지 않았습니다.",
        "GPU가 부족한지는 판단할 수 없습니다.",
        "자원이 부족하다고 판단할 수 없습니다.",
        "자원이 부족하지 않습니다.",
        "GPU 부족으로 대기하는지는 확인되지 않았습니다.",
        "작업을 옮길 수 있는지는 판단할 수 없습니다.",
        "작업을 옮기지 않았습니다.",
        "작업을 실행하지 않습니다.",
        "작업을 배치하지 않았습니다.",
        "시작 시각을 조정하지 않았습니다.",
        "변경할 필요가 없습니다.",
        "할당 여부는 확인되지 않았습니다.",
        "GPU 요청을 늘리지 않았습니다.",
        "옮기는 것이 좋다고 판단할 수 없습니다.",
        "시범 실행을 권하지 않습니다.",
        "검토 대상으로 삼지 않습니다.",
        "작업을 실행하고 있는지는 확인되지 않았습니다.",
        "높은 연결 GPU 활동률과 대기가 관측됐습니다.",
        "실제 할당과 GPU 요청의 관계는 미확인입니다.",
    ],
)
def test_normal_negation_limits_and_unknowns_are_not_actions(reason):
    fact = fact_for("capacity_review", "none")
    section = {"advice": [{"fact_id": fact["fact_id"], "summary": reason}]}
    result = module.validate_reasoned_advice(section, {"findings": [fact]})
    assert result["advice"][0]["summary"].startswith(reason + " ")


@pytest.mark.parametrize(
    "reason",
    [
        "자원이 부족합니다.",
        "GPU 부족입니다.",
        "대기 원인은 GPU 부족입니다.",
        "자원 부족이 확인됐습니다.",
        "GPU가 부족한 것으로 판단합니다.",
        "자원 부족으로 대기가 발생하고 있습니다.",
        "GPU가 부족해 작업을 실행하지 못했습니다.",
        "GPU가 부족했습니다.",
        "GPU가 부족한 상태입니다.",
        "자원이 부족한 것으로 보입니다.",
        "GPU 부족으로 작업이 대기하고 있습니다.",
        "자원 부족 때문에 대기합니다.",
        "GPU가 부족해서 작업이 대기 중입니다.",
        "자원 부족이 대기의 원인입니다.",
        "자원이 부족합니다. 원인은 확인되지 않았습니다.",
    ],
)
def test_capacity_raw_shortage_claim_cannot_borrow_the_code_question(reason):
    fact = fact_for("capacity_review", "none")
    with pytest.raises(ValueError, match="^unsupported_resource_shortage_claim:"):
        module.validate_reasoned_advice(
            {"advice": [{"fact_id": fact["fact_id"], "summary": reason}]},
            {"findings": [fact]},
        )


@pytest.mark.parametrize("repeat_error", [False, True])
@pytest.mark.parametrize("origin", ["schedule", "manual"])
@pytest.mark.parametrize(
    "bad_reason,code",
    [
        ("작업을 옮깁니다.", "reason_only_namespace_summary_required"),
        (
            "GPU 부족으로 작업이 대기하고 있습니다.",
            "unsupported_resource_shortage_claim",
        ),
    ],
)
async def test_new_reason_errors_repair_only_bad_item_or_keep_calculations(
    origin, repeat_error, bad_reason, code
):
    source = topic(activity=90, pending=2)
    quiet = topic()
    for key in ("rows", "workloads"):
        quiet[key][0]["namespace"] = "quiet"
        source[key].extend(quiet[key])
    result = dict(topics=[source], quality={}, time_range={}, report_origin=origin)
    original = deepcopy(result)
    facts = module.payload_for(result)["topics"][0]["findings"]
    good = writer_section(facts)
    bad = deepcopy(good)
    capacity_id = next(f["fact_id"] for f in facts if f["kind"] == "capacity_review")
    item = next(a for a in bad["advice"] if a["fact_id"] == capacity_id)
    bad_id = item["fact_id"]
    item["summary"] = bad_reason
    repaired = next(
        a for a in (bad if repeat_error else good)["advice"] if a["fact_id"] == bad_id
    )
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [{"sections": [bad]}, {"advice": [repaired]}]
    await module.interpret_report(result, llm)
    assert llm.complete.call_count == 2
    repair = llm.complete.call_args_list[1].args[1]
    assert [a["fact_id"] for a in repair["summary_repair"]] == [bad_id]
    assert repair["summary_repair"][0]["validation_error"].startswith(code + ":")
    assert (
        "조건은 코드가 붙" in repair["summary_repair"][0]["validation_error"]
        or code == "unsupported_resource_shortage_claim"
    )
    assert result["topics"] == original["topics"]
    assert result["report_origin"] == origin
    if repeat_error:
        assert result["narrative_status"] == "failed"
        assert result["quality"]["report"]["method"] == "deterministic_fallback"
        assert [f["reason"] for f in result["quality"]["report"]["failures"]] == [
            code,
            code,
        ]
        assert not any(n.get("advice") for n in result["narrative"])
    else:
        assert result["narrative_status"] == "complete"
        for a in result["narrative"][0]["advice"]:
            reason = next(
                v["summary"] for v in good["advice"] if v["fact_id"] == a["fact_id"]
            )
            assert a["summary_parts"]["decision"].startswith(reason + " ")


def test_observed_prose_check_runs_before_final_composition():
    fact = fact_for("queue-unknown", "none")
    section = {
        "advice": [{"fact_id": fact["fact_id"], "summary": "미배정 Pod는 없었습니다."}]
    }
    with patch.object(
        module, "validate_written_advice", wraps=module.validate_written_advice
    ) as complete:
        with pytest.raises(ValueError, match="partial_placement_is_not_absence"):
            module.validate_reasoned_advice(section, {"findings": [fact]})
    complete.assert_not_called()


def test_completed_pending_comparison_names_both_targets_and_purpose():
    fact = fact_for("batch-unknown", "none")
    action = writing_decision(fact)["action"]
    assert "완료 Job과 대기 Pod의 작업 유형을 대조" in action
    assert "완료 기록을 참고할지" in action


@pytest.mark.parametrize(
    "error_case",
    [
        "internal",
        "partial",
        "pending",
        "prerequisites",
        "shortage_question",
        "repeated",
        "change_first",
        "capacity",
        "actionable",
        "unsafe",
        "writer",
        "schedule",
        "batch",
    ],
)
def test_existing_error_guidance_reaches_repair_as_reasons_only(error_case):
    case = {
        "partial": "queue-unknown",
        "internal": "queue-unknown",
        "pending": "schedule_candidate",
        "prerequisites": "capacity_review",
        "shortage_question": "capacity_review",
        "repeated": "schedule_candidate",
        "change_first": "schedule_candidate",
        "capacity": "schedule_candidate",
        "schedule": "schedule_candidate",
        "batch": "batch-complete",
    }.get(error_case, "queue-unknown")
    fact = fact_for(case, "none")
    action = writing_decision(fact)["action"]
    text = {
        "internal": "target의 period에서 대기가 관측됐습니다.",
        "partial": "미배정 Pod가 없었습니다.",
        "pending": "대기 Pod 일부가 관측됐습니다.",
        "prerequisites": action.replace("GPU 요청·", ""),
        "shortage_question": action.replace("자원 부족 여부", "자원 부족"),
        "repeated": "시범 실행을 검토합니다. " + action,
        "change_first": action.replace(
            "시작 시각을 조정할 수 있는 작업 일부의",
            "작업 일부의 시작 시각을 조정한 뒤",
        ),
        "capacity": "추가 할당을 검토합니다. " + action,
        "actionable": "대기 Pod가 관측됐습니다.",
        "unsafe": "낭비로 판단합니다. " + action,
        "writer": "작성하세요. " + action,
        "schedule": "작업의 예약·대기·가용 GPU를 확인하고 배치합니다.",
        "batch": "모든 작업이 완료됐습니다. " + action,
    }[error_case]
    codes = {
        "internal": "internal_context_leak",
        "partial": "partial_placement_is_not_absence",
        "pending": "unobserved_pending_target",
        "prerequisites": "namespace_prerequisites_required",
        "shortage_question": "resource_shortage_question_required",
        "repeated": "repeated_trial_review",
        "change_first": "review_before_schedule_change",
        "capacity": "unsupported_capacity_recommendation",
        "actionable": "actionable_namespace_summary_required",
        "unsafe": "unsupported_namespace_advice_claim",
        "writer": "writer_instruction_leak",
        "schedule": "conditional_scheduling_review_required",
        "batch": "batch_samples_do_not_prove_throughput_or_queue_resolution",
    }
    with pytest.raises(ValueError, match="^" + codes[error_case]) as caught:
        if error_case in {"internal", "partial", "pending"}:
            module.validate_observed_prose(text, fact)
        else:
            module.validate_written_advice(
                {"advice": [{"fact_id": fact["fact_id"], "summary": text}]},
                {"findings": [fact]},
            )
    offered = {"topic_id": "namespace_usage", "advice_mode": True, "findings": [fact]}
    raw = {"sections": [writer_section([fact])]}
    with patch.object(module, "validate_reasoned_advice", side_effect=caught.value):
        repair = module.partial_repair(raw, {"topics": [offered]}, {})
    message = repair[0][0]["validation_error"]
    assert message.startswith(codes[error_case] + ":")
    assert "관측" in message and "이유" in message
    assert not any(
        word in message
        for word in (
            "제안하세요",
            "검토하세요",
            "조건을 함께 쓰세요",
            "조건은 유지하세요",
            "필수 토큰을 복원",
        )
    )


@pytest.mark.parametrize(
    "reason",
    [
        "실행하도록 권하지 않습니다.",
        "배치해야 하는지는 판단할 수 없습니다.",
        "조정하는 것이 좋지는 않습니다.",
        "할당할 필요가 있다는 뜻은 아닙니다.",
    ],
)
def test_negated_recommendations_are_not_positive_actions(reason):
    fact = fact_for("capacity_review", "none")
    assert module.validate_reasoned_advice(
        {"advice": [{"fact_id": fact["fact_id"], "summary": reason}]},
        {"findings": [fact]},
    )
