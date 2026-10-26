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
    action = expected["decision"].pop("action")
    expected.pop("summary_start")
    expected.pop("required_summary_tokens")
    expected["observed_values"] = {
        k[2:-2]: v for k, v in expected.pop("summary_tokens").items()
    }
    assert {
        k: v
        for k, v in sent.items()
        if k
        not in {
            "writing_checks",
            "required_checks",
            "required_prose_terms",
            "prose_max_chars",
            "writing_focus",
        }
    } == {k: v for k, v in expected.items() if k != "writing_focus"}
    assert sent["writing_checks"]
    assert 0 < sent["prose_max_chars"] <= 220
    import re

    combined = (
        "가" * sent["prose_max_chars"] + " " + action + " " + context["summary_start"]
    )
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
@pytest.mark.parametrize("problem", ["overlong", "observation_only"])
async def test_initial_and_repair_input_supply_bounds_without_finished_advice(
    origin, problem
):
    from unittest.mock import AsyncMock
    from ops_agent.report_interpretation import (
        interpret_report,
        payload_for,
        validate_reasoned_advice,
    )
    from test_namespace_advice import writer_section

    result = dict(
        topics=[pattern_topic([70, 80, 20, 25])],
        time_range={},
        quality={},
        report_origin=origin,
    )
    before = deepcopy(result["topics"])
    facts = payload_for(result)["topics"][0]["findings"]
    valid = writer_section(facts)
    invalid = deepcopy(valid)
    invalid["advice"][0]["summary"] = "관측 " * 150 if problem == "overlong" else ""
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [
        {"sections": [invalid]},
        {"advice": [valid["advice"][0]]},
    ]
    await interpret_report(result, llm)
    first, repair = [call.args[1] for call in llm.complete.call_args_list]
    sent = first["topics"][0]["findings"][0]
    fixed = repair["summary_repair"][0]
    for context in (sent, fixed):
        assert (
            "option" not in context["decision"] and "action" not in context["decision"]
        )
        assert (
            "required_checks" not in context and "required_prose_terms" not in context
        )
        assert context["prose_max_chars"] > 0
        assert "summary_start" not in context and "summary_tokens" not in context
    assert sent["writing_checks"] == fixed["writing_checks"]
    assert "다시 작성하지 마세요" in repair["instruction"]
    assert result["narrative_status"] == "complete" and result["topics"] == before
    expected = validate_reasoned_advice(valid, {"findings": facts})
    assert (
        result["narrative"][0]["advice"][0]["summary"]
        == expected["advice"][0]["summary"]
    )


@pytest.mark.parametrize("phase", ["placement", "preparation", "unknown"])
def test_code_action_matches_queue_stage_without_inventing_coverage(phase):
    from ops_agent.report_interpretation import writing_context, validate_written_advice

    source = topic(pending=2)
    for hour in source["workloads"][0]["hours"]:
        hour.update(
            unscheduled_peak=2 if phase == "placement" else 0,
            unscheduled_samples=240 if phase != "unknown" else 1,
        )
    fact = next(f for f in candidates(source) if f["kind"] == "queue_review")
    before = deepcopy(fact)
    sent = writing_context(fact)
    action = summary_context(fact)["decision"]["action"]
    assert sent["queue_context"]["check_first"] == phase
    if phase == "placement":
        assert "GPU 요청·노드 선택 조건" in action
    elif phase == "preparation":
        assert "이미지 다운로드·초기화 이벤트" in action and "스케줄러" not in action
    else:
        assert "노드 배정 대기인지" in action and "초기화 중인지" in action
    assert "required_checks" not in sent and "action" not in sent["decision"]
    assert validate_written_advice(
        {"advice": [{"fact_id": fact["fact_id"], "summary": action}]},
        {"findings": [fact]},
    )
    assert fact == before


def test_known_batch_type_is_used_without_another_type_check():
    from ops_agent.report_interpretation import writing_context

    fact = next(
        f for f in candidates(completed_topic()) if f["kind"] == "batch_progress"
    )
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
    sent = writing_context(fact)
    action = summary_context(fact)["decision"]["action"]
    assert "이 후보의 완료 Job에 테스트 유형이 연결됨" in sent["decision"]["known"]
    assert "시작·완료 기록" in action
    assert "유형도 대조" not in action and "남은 대기" not in action
    assert fact == before


async def test_code_supplies_check_verb_without_model_repair():
    from unittest.mock import AsyncMock
    from ops_agent.report_interpretation import (
        interpret_report,
        payload_for,
        validate_written_advice,
    )
    from test_namespace_advice import writer_section

    result = dict(topics=[topic(pending=2)], quality={}, time_range={})
    facts = payload_for(result)["topics"][0]["findings"]
    valid = writer_section(facts)
    with pytest.raises(ValueError, match="actionable_namespace_summary_required"):
        validate_written_advice(valid, {"findings": facts})
    llm = AsyncMock(configured=True)
    llm.complete.return_value = {"sections": [valid]}
    await interpret_report(result, llm)
    assert llm.complete.call_count == 1 and result["narrative_status"] == "complete"
    for item in result["narrative"][0]["advice"]:
        assert (
            "확인" in item["summary_parts"]["decision"]
            or "점검" in item["summary_parts"]["decision"]
        )


@pytest.mark.parametrize(
    "problem,code",
    [
        ("partial_zero", "partial_placement_is_not_absence"),
        ("absent_target", "unobserved_pending_target"),
        ("missing_policy", "reason_only_namespace_summary_required"),
        ("change_first", "reason_only_namespace_summary_required"),
    ],
)
@pytest.mark.parametrize("origin", ["schedule", "manual"])
async def test_semantic_writing_errors_repair_only_the_affected_item(
    problem, code, origin
):
    from unittest.mock import AsyncMock
    from ops_agent.report_interpretation import interpret_report, payload_for
    from test_namespace_advice import writer_section

    source = topic(activity=90, pending=2) if problem == "missing_policy" else topic()
    if problem == "partial_zero":
        source = topic(pending=2)
        for hour in source["workloads"][0]["hours"]:
            hour.update(unscheduled_peak=0, unscheduled_samples=1)
    if problem == "change_first":
        source = pattern_topic([70, 80, 20, 25])
    result = dict(topics=[source], quality={}, time_range={}, report_origin=origin)
    before = deepcopy(result["topics"])
    facts = payload_for(result)["topics"][0]["findings"]
    valid = writer_section(facts)
    invalid = deepcopy(valid)
    item = invalid["advice"][0]
    item["summary"] = {
        "partial_zero": "대기 Pod가 관측됐으나 노드 미배정은 없었으므로 배정이 완료됐습니다.",
        "absent_target": "이 네임스페이스의 대기 Pod 일부가 낮은 연결 GPU 활동 구간에도 관측됐습니다.",
        "missing_policy": "높은 GPU 활동과 대기가 관측돼 스케줄러 사유와 GPU 요청·실제 할당·보장량·가용 GPU를 확인한 뒤 추가 할당을 검토하세요.",
        "change_first": "마감·예약·가용 GPU·메모리 요구를 확인한 뒤 일부 작업의 시작 시각을 조정해 시범 실행을 검토하세요.",
    }[problem]
    target = {"findings": [next(f for f in facts if f["fact_id"] == item["fact_id"])]}
    from ops_agent.report_interpretation import (
        advice_with_evidence,
        advice_with_actions,
    )

    # The existing validator accepts this captured failure class; keep its gates unchanged.
    assert validate_advice(
        advice_with_evidence(advice_with_actions({"advice": [item]}, target), target),
        target,
    )
    patch = next(a for a in valid["advice"] if a["fact_id"] == item["fact_id"])
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [{"sections": [invalid]}, {"advice": [patch]}]
    await interpret_report(result, llm)
    repair = llm.complete.call_args.args[1]
    assert [a["fact_id"] for a in repair["summary_repair"]] == [item["fact_id"]]
    assert repair["summary_repair"][0]["validation_error"].startswith(code + ":")
    assert result["quality"]["report"]["failures"] == [{"attempt": 1, "reason": code}]
    assert result["quality"]["report"]["reason"] == "repaired"
    assert result["narrative_status"] == "complete"
    assert result["topics"] == before


@pytest.mark.parametrize(
    "removed",
    ["스케줄러 사유·", "GPU 요청·", "실제 할당·", "보장량·", "가용 GPU·", "운영정책·"],
)
def test_capacity_prerequisites_are_all_checked_before_review(removed):
    from ops_agent.report_interpretation import validate_written_advice

    fact = next(
        f
        for f in candidates(topic(activity=90, pending=2))
        if f["kind"] == "capacity_review"
    )
    text = "GPU 활동과 대기가 관측돼, 스케줄러 사유·GPU 요청·실제 할당·보장량·가용 GPU·운영정책·작업 기록에서 자원 부족 여부를 확인한 뒤 추가 할당을 검토하세요."
    section = {
        "advice": [{"fact_id": fact["fact_id"], "summary": text.replace(removed, "")}]
    }
    with pytest.raises(ValueError, match="namespace_prerequisites_required"):
        validate_written_advice(section, {"findings": [fact]})
    section["advice"][0]["summary"] = text
    assert validate_written_advice(section, {"findings": [fact]})


@pytest.mark.parametrize("samples", [1, 240])
def test_partial_zero_is_not_absence_but_partial_positive_is_presence(samples):
    from ops_agent.report_interpretation import validate_written_advice

    source = topic(pending=2)
    for hour in source["workloads"][0]["hours"]:
        hour.update(unscheduled_peak=0, unscheduled_samples=samples)
    fact = next(f for f in candidates(source) if f["kind"] == "queue_review")
    item = {
        "fact_id": fact["fact_id"],
        "summary": "노드를 기다리는 Pod는 관측되지 않았습니다. 대기 Pod의 이벤트를 확인하세요.",
    }
    if samples == 1:
        with pytest.raises(ValueError, match="partial_placement_is_not_absence"):
            validate_written_advice({"advice": [item]}, {"findings": [fact]})
    else:
        assert validate_written_advice({"advice": [item]}, {"findings": [fact]})
    for hour in source["workloads"][0]["hours"]:
        hour["unscheduled_peak"] = 1
    fact = next(f for f in candidates(source) if f["kind"] == "queue_review")
    item["fact_id"] = fact["fact_id"]
    item["summary"] = "일부 노드 미배정 Pod가 관측돼 스케줄러 이벤트를 확인하세요."
    assert validate_written_advice({"advice": [item]}, {"findings": [fact]})


@pytest.mark.parametrize("missing", ["마감·", "예약·", "대기·", "가용 GPU·"])
def test_scheduling_prerequisites_cannot_be_left_until_after_review(missing):
    from ops_agent.report_interpretation import validate_written_advice

    fact = next(f for f in candidates(topic()) if f["kind"] == "schedule_candidate")
    text = "작업 마감·예약·대기·가용 GPU·요구를 확인한 뒤 조정 가능한 작업 일부의 시범 실행을 검토하세요."
    item = {
        "fact_id": fact["fact_id"],
        "summary": text.replace(missing, "") + " " + missing + "기록도 확인하세요.",
    }
    with pytest.raises(ValueError, match="namespace_prerequisites_required"):
        validate_written_advice({"advice": [item]}, {"findings": [fact]})
    item["summary"] = text
    assert validate_written_advice({"advice": [item]}, {"findings": [fact]})


async def test_failed_semantic_repair_preserves_calculations_without_accepting_prose():
    from unittest.mock import AsyncMock
    from ops_agent.report_interpretation import interpret_report, payload_for
    from test_namespace_advice import writer_section

    result = dict(topics=[topic()], quality={}, time_range={})
    before = deepcopy(result["topics"])
    valid = writer_section(payload_for(result)["topics"][0]["findings"])
    invalid = deepcopy(valid)
    invalid["advice"][0]["summary"] = "이 네임스페이스의 대기 Pod 일부가 관측됐습니다."
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [{"sections": [invalid]}, {"advice": invalid["advice"]}]
    await interpret_report(result, llm)
    assert result["narrative_status"] == "failed"
    assert result["topics"] == before
    assert "narrative" not in result or not any(
        s.get("advice") for s in result["narrative"]
    )
    assert [f["reason"] for f in result["quality"]["report"]["failures"]] == [
        "unobserved_pending_target"
    ] * 2


def test_folded_queue_prose_does_not_change_existing_selection_or_repair_scope():
    from ops_agent.report_interpretation import partial_repair
    from test_namespace_advice import writer_section

    source = completed_topic()
    for hour in source["workloads"][0]["hours"]:
        hour.update(
            pending_peak=2,
            pending_samples=240,
            unscheduled_peak=0,
            unscheduled_samples=1,
        )
    facts = candidates(source)
    offered = {"topic_id": "namespace_usage", "advice_mode": True, "findings": facts}
    section = writer_section(facts)
    before = deepcopy(section)
    queue = next(
        a
        for a in section["advice"]
        if next(f for f in facts if f["fact_id"] == a["fact_id"])["kind"]
        == "queue_review"
    )
    queue["summary"] = "노드 미배정은 없었습니다. 스케줄러 이벤트를 점검하세요."
    from ops_agent.report_interpretation import validate_reasoned_advice

    kept = validate_reasoned_advice(section, offered)
    assert [a["kind"] for a in kept["advice"]] == ["batch_progress"]
    batch = next(a for a in section["advice"] if a["fact_id"] != queue["fact_id"])
    batch["summary"] = (
        "노드 미배정은 없었습니다. 완료 Job의 작업 유형과 스케줄러 이벤트를 점검하세요."
    )
    repair = partial_repair({"sections": [section]}, {"topics": [offered]}, {})
    assert [a["fact_id"] for a in repair[0]] == [batch["fact_id"]]
    assert before != section  # Both synthetic errors are retained as raw model prose.


def test_zero_pending_keeps_future_presence_checks_without_inventing_a_target():
    from ops_agent.report_interpretation import validate_written_advice

    fact = next(f for f in candidates(topic()) if f["kind"] == "schedule_candidate")
    item = {
        "fact_id": fact["fact_id"],
        "summary": "작업 마감·예약·가용 GPU와 대기 Pod의 유무를 확인한 뒤 조정 가능한 작업 일부의 시범 실행을 검토하세요.",
    }
    before = deepcopy(item)
    assert validate_written_advice({"advice": [item]}, {"findings": [fact]})
    assert item == before


@pytest.mark.parametrize(
    "summary",
    [
        "자원 부족 여부를 확인하고 추가 할당을 검토하려면 GPU 요청·실제 할당·보장량·가용 GPU·스케줄러 사유·운영정책을 확인·대조한 뒤에만 변경 여부를 판단하세요.",
        "자원 부족 여부를 확인하고 추가 할당을 조건부 검토하되 GPU 요청·실제 할당·보장량·가용 GPU·스케줄러 사유·운영정책을 확인한 뒤에만 판단하세요.",
        "GPU 요청·실제 할당·보장량·가용 GPU·스케줄러 사유를 확인·대조해 자원 부족 여부를 확인한 뒤 운영정책을 점검하고 추가 할당을 검토하세요.",
    ],
)
def test_valid_prerequisites_allow_conditional_judgment_and_sequential_checks(summary):
    from ops_agent.report_interpretation import validate_written_advice

    fact = next(
        f
        for f in candidates(topic(activity=90, pending=2))
        if f["kind"] == "capacity_review"
    )
    raw = {"advice": [{"fact_id": fact["fact_id"], "summary": summary}]}
    before = deepcopy(raw)
    assert validate_written_advice(raw, {"findings": [fact]})
    assert raw == before


@pytest.mark.parametrize(
    "observation",
    [
        "대기 관측도 완전했습니다. ",
        "대기 Pod가 없었으므로, ",
        "대기 Pod가 없고 ",
        "대기 없음이 관측됐지만 ",
    ],
)
def test_observation_words_cannot_replace_explicit_prerequisite_checks(observation):
    from ops_agent.report_interpretation import validate_written_advice

    fact = next(f for f in candidates(topic()) if f["kind"] == "schedule_candidate")
    item = {
        "fact_id": fact["fact_id"],
        "summary": observation
        + "마감·예약·가용 GPU를 확인한 뒤 작업 일부의 시범 실행을 검토하세요.",
    }
    with pytest.raises(ValueError, match="누락된 조건: 대기 상태"):
        validate_written_advice({"advice": [item]}, {"findings": [fact]})
    item["summary"] = (
        observation
        + "마감·예약·대기 상태·가용 GPU를 확인한 뒤 작업 일부의 시범 실행을 검토하세요."
    )
    assert validate_written_advice({"advice": [item]}, {"findings": [fact]})


def test_other_checks_after_final_review_cannot_be_covered_by_policy_only_gate():
    from ops_agent.report_interpretation import validate_written_advice

    fact = next(
        f
        for f in candidates(topic(activity=90, pending=2))
        if f["kind"] == "capacity_review"
    )
    item = {
        "fact_id": fact["fact_id"],
        "summary": "운영정책을 확인·대조한 뒤에만 추가 할당을 검토하세요. GPU 요청·실제 할당·보장량·가용 GPU와 스케줄러 사유를 점검해야 합니다.",
    }
    with pytest.raises(ValueError, match="namespace_prerequisites_required") as error:
        validate_written_advice({"advice": [item]}, {"findings": [fact]})
    assert "스케줄러 사유·GPU 요청·실제 할당·보장량·가용 GPU·운영정책" in str(
        error.value
    )
    assert "원문에 조건이나 행동을 채우지 말고" in str(error.value)


@pytest.mark.parametrize("origin", ["schedule", "manual"])
async def test_code_prerequisites_survive_reason_repair_without_writer_requirements(
    origin,
):
    from unittest.mock import AsyncMock
    from ops_agent.report_interpretation import (
        interpret_report,
        payload_for,
        PREREQUISITES,
        checked_prerequisites,
    )
    from test_namespace_advice import writer_section

    result = dict(
        topics=[topic(activity=90, pending=2)],
        quality={},
        time_range={},
        report_origin=origin,
    )
    before = deepcopy(result["topics"])
    facts = payload_for(result)["topics"][0]["findings"]
    valid = writer_section(facts)
    invalid = deepcopy(valid)
    invalid["advice"][0]["summary"] = ""
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [
        {"sections": [invalid]},
        {"advice": [valid["advice"][0]]},
    ]
    await interpret_report(result, llm)
    first, repair = [call.args[1] for call in llm.complete.call_args_list]
    for context in (first["topics"][0]["findings"][0], repair["summary_repair"][0]):
        assert (
            "required_checks" not in context and "required_prose_terms" not in context
        )
    for item in result["narrative"][0]["advice"]:
        if item["kind"] in PREREQUISITES:
            required = PREREQUISITES[item["kind"]]
            checked, ordered = checked_prerequisites(
                item["summary_parts"]["decision"], required
            )
            assert set(required) <= checked and ordered
    assert result["narrative_status"] == "complete" and result["topics"] == before


@pytest.mark.parametrize(
    "subject",
    [
        "일부 작업은 활동이 낮았고",
        "일부 작업이 낮은 활동률을 보였고",
        "Pod는 낮은 활동률을 보였습니다.",
    ],
)
def test_namespace_gpu_activity_is_not_a_per_workload_measurement(subject):
    from ops_agent.report_interpretation import validate_written_advice

    fact = next(f for f in candidates(topic()) if f["kind"] == "schedule_candidate")
    item = {
        "fact_id": fact["fact_id"],
        "summary": subject
        + " 마감·예약·대기·가용 GPU를 확인한 뒤 작업 일부의 시범 실행을 검토하세요.",
    }
    with pytest.raises(ValueError, match="unsupported_workload_activity_attribution"):
        validate_written_advice({"advice": [item]}, {"findings": [fact]})
    item["summary"] = (
        "작업이 연결된 GPU의 활동률은 낮게 관측됐습니다. 마감·예약·대기·가용 GPU를 확인한 뒤 작업 일부의 시범 실행을 검토하세요."
    )
    assert validate_written_advice({"advice": [item]}, {"findings": [fact]})
    item["summary"] = (
        "작업이 낮은 활동률의 GPU에 연결됐습니다. 마감·예약·대기·가용 GPU를 확인한 뒤 작업 일부의 시범 실행을 검토하세요."
    )
    assert validate_written_advice({"advice": [item]}, {"findings": [fact]})


@pytest.mark.parametrize("samples", [1, 240])
@pytest.mark.parametrize(
    "absence",
    [
        "노드 미배정은 없었으므로",
        "노드 미배정은 없었고",
        "미배정은 없다고 판단됩니다",
        "노드 미배정은 없었으며",
        "노드 미배정은 없었지만",
        "노드 미배정은 없었으나",
        "미배치 Pod가 없었는데",
        "노드를 기다리는 Pod는 없었으며",
        "노드를 배정받지 못한 Pod가 없었지만",
        "미배정 Pod는 관측되지 않았으며",
        "미배치 Pod는 관측되지 않았지만",
        "미배정 Pod가 없어",
        "미배치 Pod가 없어서",
    ],
)
def test_partial_absence_conjugations_require_complete_samples(samples, absence):
    from ops_agent.report_interpretation import validate_written_advice

    source = topic(pending=2)
    for hour in source["workloads"][0]["hours"]:
        hour.update(unscheduled_peak=0, unscheduled_samples=samples)
    fact = next(f for f in candidates(source) if f["kind"] == "queue_review")
    raw = {
        "advice": [
            {
                "fact_id": fact["fact_id"],
                "summary": absence + ", 대기 Pod 상태·이벤트를 점검하세요.",
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


@pytest.mark.parametrize("kind", ["relative_activity", "schedule_candidate"])
@pytest.mark.parametrize(
    "action", ["조정해", "조정해서", "변경해", "조정하고", "변경한 뒤", "조정한 후"]
)
def test_time_change_is_reviewed_before_action_in_both_candidate_kinds(kind, action):
    from ops_agent.report_interpretation import (
        advice_with_evidence,
        validate_written_advice,
    )

    source = (
        topic() if kind == "schedule_candidate" else pattern_topic([70, 80, 20, 25])
    )
    fact = next(f for f in candidates(source) if f["kind"] == kind)
    offered = {"findings": [fact]}
    conditions = "마감·예약·대기·가용 GPU·메모리 요구를 확인한 뒤 "
    raw = {
        "advice": [
            {
                "fact_id": fact["fact_id"],
                "summary": conditions
                + f"일부 작업의 시작 시각을 {action} 시범 실행을 검토하세요.",
            }
        ]
    }
    before = deepcopy(raw)
    code = "review_before_schedule_change"
    if kind == "relative_activity" and action.startswith("변경"):
        code = "conditional_relative_window_trial_required"
        with pytest.raises(ValueError, match=code):
            validate_advice(advice_with_evidence(raw, offered), offered)
    else:
        assert validate_advice(advice_with_evidence(raw, offered), offered)
    with pytest.raises(ValueError, match=code):
        validate_written_advice(raw, offered)
    assert raw == before
    raw["advice"][0]["summary"] = (
        conditions
        + "시작 시각을 조정할 수 있는 작업 일부의 시범 실행 여부를 검토하세요."
    )
    assert validate_written_advice(raw, offered)


@pytest.mark.parametrize(
    "kind,source,summary",
    [
        (
            "relative_activity",
            lambda: pattern_topic([70, 80, 20, 25]),
            "비교 구간보다 연결 GPU의 활동률이 낮았습니다. 마감·예약·가용 GPU·메모리 요구를 확인한 뒤, 시작 시각을 조정할 수 있는 작업 일부의 시범 실행을 검토하세요.",
        ),
        (
            "capacity_review",
            lambda: topic(activity=90, pending=2),
            "높은 GPU 활동률과 대기가 같은 구간에 관측됐습니다. 스케줄러 사유와 GPU 요청·실제 할당을 대조해 자원 부족 여부를 확인하고, 보장량·가용 GPU·운영정책을 확인한 뒤 추가 할당을 검토하세요.",
        ),
        (
            "batch_progress",
            completed_topic,
            "일부 Job이 끝났습니다. 같은 작업 유형의 일정에 참고할 수 있을지, 완료 Job의 실제 Pod 시작·완료 기록을 대조해 확인하세요.",
        ),
    ],
)
def test_short_observation_and_purposeful_check_keep_existing_guards(
    kind, source, summary
):
    from ops_agent.report_interpretation import validate_written_advice

    fact = next(f for f in candidates(source()) if f["kind"] == kind)
    raw = {"advice": [{"fact_id": fact["fact_id"], "summary": summary}]}
    before = deepcopy(raw)
    output = validate_written_advice(raw, {"findings": [fact]})
    assert output["advice"][0]["summary"].startswith(summary + " ")
    assert raw == before
    if kind == "capacity_review":
        raw["advice"][0]["summary"] = summary.replace("·운영정책", "")
        with pytest.raises(ValueError, match="namespace_prerequisites_required"):
            validate_written_advice(raw, {"findings": [fact]})
    if kind == "relative_activity":
        raw["advice"][0]["summary"] = summary.replace("·예약", "")
        with pytest.raises(
            ValueError, match="conditional_relative_window_trial_required"
        ):
            validate_written_advice(raw, {"findings": [fact]})


@pytest.mark.parametrize("repair_shortage", [False, True])
async def test_repeated_observation_repair_identifies_forbidden_question(
    repair_shortage,
):
    from unittest.mock import AsyncMock
    from ops_agent.report_interpretation import interpret_report, payload_for
    from test_namespace_advice import writer_section

    result = dict(topics=[pattern_topic([85, 20, 90], 2)], quality={}, time_range={})
    before = deepcopy(result["topics"])
    facts = payload_for(result)["topics"][0]["findings"]
    original = writer_section(facts)
    invalid = deepcopy(original)
    item = next(
        a
        for a in invalid["advice"]
        if next(f for f in facts if f["fact_id"] == a["fact_id"])["kind"]
        == "repeated_activity"
    )
    item["summary"] = (
        "서로 떨어진 시점에 높은 GPU 활동과 대기가 관측됐지만 노드 부족 여부는 미확인입니다."
    )
    patch = deepcopy(item)
    if not repair_shortage:
        patch["summary"] = (
            "서로 떨어진 시점에 높은 연결 GPU 활동과 대기가 관측됐습니다."
        )
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [{"sections": [invalid]}, {"advice": [patch]}]
    await interpret_report(result, llm)
    first, repair = [call.args[1] for call in llm.complete.call_args_list]
    context = next(
        f for f in first["topics"][0]["findings"] if f["fact_id"] == item["fact_id"]
    )
    fixed = repair["summary_repair"][0]
    assert context["writing_checks"] == fixed["writing_checks"]
    question = context["writing_checks"][1]
    assert "관측" in question
    assert "노드 부족으로" not in question
    assert "관측" in question
    assert fixed["validation_error"].startswith(
        "separate_observations_do_not_prove_continuity:"
    )
    assert "포화·부족·때문" in fixed["validation_error"]
    assert result["narrative_status"] == ("failed" if repair_shortage else "complete")
    assert result["topics"] == before
    assert original != invalid


@pytest.mark.parametrize("samples", [1, 240])
@pytest.mark.parametrize("repeat_absence", [False, True])
async def test_number_repair_retains_partial_placement_bound(samples, repeat_absence):
    from unittest.mock import AsyncMock
    from ops_agent.report_interpretation import interpret_report, payload_for
    from test_namespace_advice import writer_section

    source = topic(pending=2)
    for hour in source["workloads"][0]["hours"]:
        hour.update(unscheduled_peak=0, unscheduled_samples=samples)
    result = dict(topics=[source], quality={}, time_range={})
    before = deepcopy(result["topics"])
    facts = payload_for(result)["topics"][0]["findings"]
    section = writer_section(facts)
    section["advice"][0]["summary"] = "대기 Pod가 2개 관측됐습니다."
    patch = deepcopy(section["advice"][0])
    patch["summary"] = (
        "노드 미배정은 없었습니다."
        if repeat_absence
        else "미배정 관측이 일부여서 대기 단계는 미확인입니다."
        if samples == 1
        else "완전한 표본에서 노드 미배정은 관측되지 않았습니다."
    )
    # A complete-zero candidate requires preparation events in its repaired prose.
    if samples == 240 and repeat_absence:
        patch["summary"] = "완전한 표본에서 노드 미배정은 없었습니다."
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [{"sections": [section]}, {"advice": [patch]}]
    await interpret_report(result, llm)
    first, repair = [call.args[1] for call in llm.complete.call_args_list]
    original = first["topics"][0]["findings"][0]
    fixed = repair["summary_repair"][0]
    assert fixed["validation_error"].startswith("namespace_summary_tokens_required:")
    assert original["writing_checks"] == fixed["writing_checks"]
    for context in (original, fixed):
        assert context["queue_context"]["unscheduled_complete"] == (samples == 240)
    for call in llm.complete.call_args_list:
        assert (
            "queue_context.unscheduled_complete=false에서 미배치 관측 영은 미배정 없음·배정 완료를 뜻하지 않습니다"
            in call.args[0]
        )
        assert "양수 관측은 미배정 Pod가 관측됐다는 근거" in call.args[0]
    assert "관측의 한계를 유지" in repair["instruction"]
    assert result["narrative_status"] == (
        "failed" if samples == 1 and repeat_absence else "complete"
    )
    assert result["topics"] == before


@pytest.mark.parametrize(
    "kind", ["relative_activity", "capacity_review", "batch_progress"]
)
async def test_length_repair_preserves_every_prerequisite_and_guard(kind):
    from unittest.mock import AsyncMock
    from ops_agent.report_interpretation import (
        interpret_report,
        payload_for,
        validate_written_advice,
    )
    from test_namespace_advice import writer_section

    source = {
        "relative_activity": lambda: pattern_topic([70, 80, 20, 25]),
        "capacity_review": lambda: topic(activity=90, pending=2),
        "batch_progress": completed_topic,
    }[kind]()
    result = dict(topics=[source], quality={}, time_range={})
    before = deepcopy(result["topics"])
    facts = payload_for(result)["topics"][0]["findings"]
    valid = writer_section(facts)
    fact = next(f for f in facts if f["kind"] == kind)
    patch = next(a for a in valid["advice"] if a["fact_id"] == fact["fact_id"])
    invalid = deepcopy(valid)
    next(a for a in invalid["advice"] if a["fact_id"] == fact["fact_id"])["summary"] = (
        "관측 설명 " * 150
    )
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [{"sections": [invalid]}, {"advice": [patch]}]
    await interpret_report(result, llm)
    repair = llm.complete.call_args.args[1]["summary_repair"][0]
    assert "prose_max_chars=" in repair["validation_error"]
    assert "required_checks" not in repair and "required_prose_terms" not in repair
    assert len(patch["summary"]) <= repair["prose_max_chars"]
    assert result["narrative_status"] == "complete" and result["topics"] == before
    action = summary_context(fact)["decision"]["action"]
    assert validate_written_advice(
        {"advice": [{"fact_id": fact["fact_id"], "summary": action}]},
        {"findings": [fact]},
    )
    if kind != "batch_progress":
        bad = (
            action.replace("·예약", "")
            if kind == "relative_activity"
            else action.replace("·운영정책", "")
        )
        with pytest.raises(ValueError):
            validate_written_advice(
                {"advice": [{"fact_id": fact["fact_id"], "summary": bad}]},
                {"findings": [fact]},
            )


async def test_workload_activity_repair_keeps_the_gpu_as_measurement_subject():
    from unittest.mock import AsyncMock
    from ops_agent.report_interpretation import interpret_report, payload_for
    from test_namespace_advice import writer_section

    result = dict(topics=[topic()], quality={}, time_range={})
    before = deepcopy(result["topics"])
    facts = payload_for(result)["topics"][0]["findings"]
    section = writer_section(facts)
    item = section["advice"][0]
    item["summary"] = "작업은 활동률이 낮았습니다."
    fixed = {
        **item,
        "summary": "연결 GPU의 활동률이 낮았습니다.",
    }
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [{"sections": [section]}, {"advice": [fixed]}]
    await interpret_report(result, llm)
    first, repair = [call.args[1] for call in llm.complete.call_args_list]
    for call in llm.complete.call_args_list:
        system = call.args[0]
        assert "개별 작업·Pod의 활동률" in system
        assert "관측 현상" in system
        assert "운영 행동은 다시 작성하지 마세요" in system
    original_context = first["topics"][0]["findings"][0]
    patched_context = repair["summary_repair"][0]
    for key in (
        "decision",
        "queue_context",
        "required_checks",
        "required_prose_terms",
        "writing_checks",
    ):
        assert original_context.get(key) == patched_context.get(key)
    assert result["quality"]["report"]["failures"] == [
        {"attempt": 1, "reason": "unsupported_workload_activity_attribution"}
    ]
    assert result["narrative_status"] == "complete" and result["topics"] == before


@pytest.mark.parametrize("phase", ["placement", "preparation", "unknown"])
def test_queue_purpose_names_the_evidence_question_without_failure_presupposition(
    phase,
):
    source = topic(pending=2)
    for hour in source["workloads"][0]["hours"]:
        hour.update(
            unscheduled_peak=2 if phase == "placement" else 0,
            unscheduled_samples=1 if phase == "unknown" else 240,
        )
    fact = next(f for f in candidates(source) if f["kind"] == "queue_review")
    before = deepcopy(fact)
    action = summary_context(fact)["decision"]["action"]
    if phase == "placement":
        assert (
            "요청을 충족할 노드가 있었는지" in action
            and "선택 조건이 맞았는지" in action
        )
    elif phase == "preparation":
        assert "준비 중인 단계와 실패 기록 유무" in action
    else:
        assert "노드 배정 대기인지" in action and "초기화 중인지" in action
    assert fact == before


@pytest.mark.parametrize(
    "prose",
    [
        "일부 작업의 낮은 GPU 활동률이 관측됐습니다.",
        "해당 작업 일부의 GPU 활동률이 낮았습니다.",
        "연결된 일부 Pod의 GPU 활동률이 낮았고 대기 Pod는 관측되지 않았습니다.",
        "작업의 높은 GPU 활동률이 관측됐습니다.",
        "Pod들의 GPU 활동률이 높았습니다.",
        "파드의 연산 활동이 높게 관측됐습니다.",
        "작업 일부의 GPU 활동률이 상대적으로 낮았습니다.",
        "작업의 GPU 활동률이 측정되었습니다.",
        "Pod의 활동률이 높게 관측됐습니다.",
        "작업의 GPU 활동률은 낮습니다.",
        "작업들의 높은 연산 활동이 관측되었습니다.",
    ],
)
def test_possessive_workload_activity_claim_uses_existing_rejection(prose):
    from ops_agent.report_interpretation import validate_written_advice

    fact = next(f for f in candidates(topic()) if f["kind"] == "schedule_candidate")
    raw = {
        "advice": [
            {
                "fact_id": fact["fact_id"],
                "summary": prose
                + " 마감·예약·대기·가용 GPU를 확인한 뒤 작업 일부의 시범 실행을 검토하세요.",
            }
        ]
    }
    before = deepcopy(raw)
    with pytest.raises(
        ValueError, match="unsupported_workload_activity_attribution:.*"
    ) as exc:
        validate_written_advice(raw, {"findings": [fact]})
    assert "소유격 포함" in str(exc.value)
    assert raw == before


@pytest.mark.parametrize(
    "prose",
    [
        "작업이 연결된 GPU의 활동률은 낮게 관측됐습니다.",
        "일부 Pod가 연결된 GPU의 활동률이 낮았습니다.",
        "작업의 GPU 요청과 연결 GPU의 활동률을 구분해 확인하세요.",
        "Pod의 상태와 연결 GPU의 활동률을 대조하세요.",
        "연결 GPU의 낮은 활동률이 관측됐습니다.",
        "작업의 GPU 활동률은 측정되지 않았습니다.",
        "작업 일부의 GPU 활동률은 확인되지 않았습니다.",
        "Pod의 GPU 활동률은 알 수 없습니다.",
        "작업의 연결 GPU 활동률이 낮게 관측됐습니다.",
        "작업에 연결된 GPU 활동률이 낮았습니다.",
        "일부 작업의 낮은 GPU 활동률로 단정할 수 없습니다.",
        "개별 Pod의 GPU 활동률을 추정하지 않습니다.",
        "Pod가 낮은 활동률의 GPU에 연결됐습니다.",
    ],
)
def test_connected_gpu_and_unknown_workload_measurements_are_not_rejected(prose):
    from ops_agent.report_interpretation import validate_written_advice

    fact = next(f for f in candidates(topic()) if f["kind"] == "schedule_candidate")
    raw = {
        "advice": [
            {
                "fact_id": fact["fact_id"],
                "summary": prose
                + " 마감·예약·대기·가용 GPU를 확인한 뒤 작업 일부의 시범 실행을 검토하세요.",
            }
        ]
    }
    before = deepcopy(raw)
    assert validate_written_advice(raw, {"findings": [fact]})["advice"]
    assert raw == before


@pytest.mark.parametrize("repeat_bad_claim", [False, True])
async def test_possessive_activity_repairs_only_bad_prose_once(repeat_bad_claim):
    from unittest.mock import AsyncMock
    from ops_agent.report_interpretation import interpret_report, payload_for
    from test_report_interpretation import reply_for

    source = topic()
    source["workloads"][0]["completed_jobs"] = completed_topic()["workloads"][0][
        "completed_jobs"
    ]
    result = dict(topics=[source], time_range={}, quality={})
    before = deepcopy(result["topics"])
    offered = payload_for(result)
    valid = reply_for(offered)
    invalid = deepcopy(valid)
    bad = next(
        a
        for a in invalid["sections"][0]["advice"]
        if next(
            f for f in offered["topics"][0]["findings"] if f["fact_id"] == a["fact_id"]
        )["kind"]
        == "schedule_candidate"
    )
    bad["summary"] = "작업 일부의 GPU 활동률이 낮았습니다."
    original_reply = deepcopy(invalid)
    patch = deepcopy(bad)
    if not repeat_bad_claim:
        patch["summary"] = "연결 GPU의 활동률이 낮았습니다."
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [invalid, {"advice": [patch]}]
    await interpret_report(result, llm)
    assert llm.complete.call_count == 2
    first, repair = [call.args[1] for call in llm.complete.call_args_list]
    assert "topics" not in repair and len(repair["summary_repair"]) == 1
    requested = repair["summary_repair"][0]
    context = next(
        f for f in first["topics"][0]["findings"] if f["fact_id"] == bad["fact_id"]
    )
    assert requested["fact_id"] == bad["fact_id"]
    assert requested["previous_summary"] == bad["summary"]
    assert requested["validation_error"].startswith(
        "unsupported_workload_activity_attribution:"
    )
    assert "소유격 포함" in requested["validation_error"]
    for key in (
        "decision",
        "observed_values",
        "queue_context",
        "required_checks",
        "required_prose_terms",
        "prose_max_chars",
    ):
        assert requested.get(key) == context.get(key)
    assert invalid == original_reply and result["topics"] == before
    if repeat_bad_claim:
        assert result["narrative_status"] == "failed"
        assert [f["reason"] for f in result["quality"]["report"]["failures"]] == [
            "unsupported_workload_activity_attribution"
        ] * 2
    else:
        assert result["narrative_status"] == "complete"
        output = result["narrative"][0]["advice"]
        for item in output:
            expected = (
                patch["summary"]
                if item["fact_id"] == bad["fact_id"]
                else next(
                    a["summary"]
                    for a in invalid["sections"][0]["advice"]
                    if a["fact_id"] == item["fact_id"]
                )
            )
            assert item["summary_parts"]["decision"].startswith(expected + " ")


@pytest.mark.parametrize(
    "prose",
    [
        "미배정은 없다고 단정할 수 없습니다.",
        "노드 미배정은 없었다고 판단할 수 없습니다.",
        "미배정 Pod가 없는지는 확인되지 않았습니다.",
        "미배정 관측은 일부여서 전체 배정 여부를 알 수 없습니다.",
        "노드 미배정 Pod가 관측됐습니다.",
    ],
)
def test_partial_placement_unknown_and_observed_presence_are_not_absence(prose):
    from ops_agent.report_interpretation import validate_written_advice

    source = topic(pending=2)
    for hour in source["workloads"][0]["hours"]:
        hour.update(unscheduled_peak=0, unscheduled_samples=1)
    if "관측됐습니다" in prose:
        for hour in source["workloads"][0]["hours"]:
            hour["unscheduled_peak"] = 1
    fact = next(f for f in candidates(source) if f["kind"] == "queue_review")
    raw = {
        "advice": [
            {
                "fact_id": fact["fact_id"],
                "summary": prose + " Pod 상태·이벤트를 점검해 대기 단계를 확인하세요.",
            }
        ]
    }
    before = deepcopy(raw)
    assert validate_written_advice(raw, {"findings": [fact]})
    assert raw == before


@pytest.mark.parametrize("kind", ["relative_activity", "schedule_candidate"])
@pytest.mark.parametrize("action", ["조정해", "조정해서", "조정하고"])
@pytest.mark.parametrize("question", ["할지", "할지를"])
def test_trial_question_is_not_an_already_performed_time_change(kind, action, question):
    from ops_agent.report_interpretation import validate_written_advice

    source = (
        topic() if kind == "schedule_candidate" else pattern_topic([70, 80, 20, 25])
    )
    fact = next(f for f in candidates(source) if f["kind"] == kind)
    prose = (
        f"시작 시각을 조정할 수 있는 작업 일부를 {action} 시범 실행{question}, "
        "마감·예약·대기·가용 GPU·메모리 요구를 확인한 뒤에 검토하세요."
    )
    raw = {"advice": [{"fact_id": fact["fact_id"], "summary": prose}]}
    before = deepcopy(raw)
    assert validate_written_advice(raw, {"findings": [fact]})
    assert raw == before
    raw["advice"][0]["summary"] = prose.replace("·예약", "")
    with pytest.raises(ValueError):
        validate_written_advice(raw, {"findings": [fact]})


@pytest.mark.parametrize(
    "action",
    [
        "조정한 뒤",
        "조정한 후",
        "조정해 시범 실행할지 살펴보고 시작 시각을 변경한 뒤",
    ],
)
def test_trial_question_does_not_excuse_an_explicit_prior_time_change(action):
    from ops_agent.report_interpretation import validate_written_advice

    fact = next(f for f in candidates(topic()) if f["kind"] == "schedule_candidate")
    raw = {
        "advice": [
            {
                "fact_id": fact["fact_id"],
                "summary": "마감·예약·대기·가용 GPU를 확인한 뒤 작업 일부의 시작 시각을 "
                + action
                + " 시범 실행할지 검토하세요.",
            }
        ]
    }
    with pytest.raises(ValueError, match="review_before_schedule_change"):
        validate_written_advice(raw, {"findings": [fact]})


@pytest.mark.parametrize("repeat_absence", [False, True])
async def test_partial_absence_conjunction_repairs_only_bad_prose_once(repeat_absence):
    from unittest.mock import AsyncMock
    from ops_agent.report_interpretation import interpret_report, payload_for
    from test_report_interpretation import reply_for

    source = topic(pending=2)
    for hour in source["workloads"][0]["hours"]:
        hour.update(unscheduled_peak=0, unscheduled_samples=1)
    result = dict(topics=[source], quality={}, time_range={})
    before = deepcopy(result["topics"])
    payload = payload_for(result)
    initial = reply_for(payload)
    bad = next(
        a
        for a in initial["sections"][0]["advice"]
        if next(
            f for f in payload["topics"][0]["findings"] if f["fact_id"] == a["fact_id"]
        )["kind"]
        == "queue_review"
    )
    bad["summary"] = (
        "노드 미배정은 없었지만 관측이 일부여서 배정 완료를 단정할 수 없습니다. "
    )
    original = deepcopy(initial)
    fixed = deepcopy(bad)
    if not repeat_absence:
        fixed["summary"] = "미배정 관측이 일부여서 대기 단계는 미확인입니다. "
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [initial, {"advice": [fixed]}]
    await interpret_report(result, llm)
    assert llm.complete.call_count == 2
    repair = llm.complete.call_args_list[1].args[1]
    assert [a["fact_id"] for a in repair["summary_repair"]] == [bad["fact_id"]]
    assert repair["summary_repair"][0]["validation_error"].startswith(
        "partial_placement_is_not_absence:"
    )
    assert initial == original and result["topics"] == before
    assert result["narrative_status"] == ("failed" if repeat_absence else "complete")
    if not repeat_absence:
        for item in result["narrative"][0]["advice"]:
            expected = (
                fixed
                if item["fact_id"] == bad["fact_id"]
                else next(
                    a
                    for a in initial["sections"][0]["advice"]
                    if a["fact_id"] == item["fact_id"]
                )
            )
            assert item["summary_parts"]["decision"].startswith(
                expected["summary"] + " "
            )


@pytest.mark.parametrize(
    "prefix,suffix",
    [
        ("", ""),
        ("메모리 점유는 낮았습니다. ", ""),
        ("메모리 점유는 낮았으며, ", ""),
        ("메모리 점유가 낮게 관측됐으며, ", ""),
        ("메모리 점유가 낮게 측정되었으나, ", ""),
        ("메모리 요구는 미확인입니다. ", ""),
        ("메모리 요구를 확인하지 않고 ", ""),
        ("메모리 요구를 확인하지 못했지만 ", ""),
        ("메모리 요구를 확인할 수 없지만 ", ""),
        ("메모리 요구 확인은 생략하고 ", ""),
        ("메모리 요구 확인 없이 ", ""),
        ("", " 메모리 요구는 그 후 확인하세요."),
    ],
)
def test_relative_memory_observation_is_not_a_prerequisite_check(prefix, suffix):
    from ops_agent.report_interpretation import (
        advice_with_evidence,
        validate_written_advice,
    )

    fact = next(
        f
        for f in candidates(pattern_topic([70, 80, 20, 25]))
        if f["kind"] == "relative_activity"
    )
    raw = {
        "advice": [
            {
                "fact_id": fact["fact_id"],
                "summary": prefix
                + "마감·예약·가용 GPU를 확인한 뒤 시작 시각을 조정할 수 있는 작업 일부의 시범 실행을 검토하세요."
                + suffix,
            }
        ]
    }
    before = deepcopy(raw)
    offered = {"findings": [fact]}
    # Existing evidence checks still pass; their memory label is not a prose check.
    assert validate_advice(advice_with_evidence(raw, offered), offered)
    with pytest.raises(
        ValueError, match="namespace_prerequisites_required:.*누락된 조건: 메모리 요구"
    ):
        validate_written_advice(raw, offered)
    assert raw == before


@pytest.mark.parametrize(
    "checks",
    [
        "마감·예약·가용 GPU·메모리 요구를 확인한 뒤",
        "마감·예약·가용 자원·메모리 요구를 확인한 뒤",
        "마감·예약·가용 GPU·메모리 요구를 먼저 확인하세요. 그 뒤",
        "메모리 요구를 확인하고 마감·예약·가용 GPU를 확인한 뒤",
        "메모리 요구는 확인했지만, 마감·예약·가용 GPU를 확인한 뒤",
        "메모리 요구는 이미 확인했습니다. 마감·예약·가용 GPU를 확인한 뒤",
        "메모리 요구 확인은 생략하지 않고 마감·예약·가용 GPU를 확인한 뒤",
        "메모리 요구 확인을 제외하지 않고 마감·예약·가용 GPU를 확인한 뒤",
        "마감·예약·가용 GPU를 확인한 뒤 메모리 요구도 대조하고",
        "메모리 점유는 낮았으며, 마감·예약·가용 GPU·메모리 요구를 확인한 뒤",
        "마감·예약·가용 GPU를 확인한 뒤 메모리 요구가 작업에 맞는지 점검하고",
    ],
)
def test_relative_memory_checks_accept_existing_sentence_forms(checks):
    from ops_agent.report_interpretation import validate_written_advice

    fact = next(
        f
        for f in candidates(pattern_topic([70, 80, 20, 25]))
        if f["kind"] == "relative_activity"
    )
    raw = {
        "advice": [
            {
                "fact_id": fact["fact_id"],
                "summary": checks
                + " 시작 시각을 조정할 수 있는 작업 일부의 시범 실행을 검토하세요.",
            }
        ]
    }
    before = deepcopy(raw)
    assert validate_written_advice(raw, {"findings": [fact]})
    assert raw == before


@pytest.mark.parametrize("origin", ["schedule", "manual"])
@pytest.mark.parametrize("repeat_missing", [False, True])
async def test_relative_memory_condition_is_checked_before_model_call(
    origin, repeat_missing
):
    from unittest.mock import AsyncMock, patch
    from ops_agent import report_interpretation as module
    from test_report_interpretation import reply_for

    result = dict(
        topics=[pattern_topic([80, 80, 20, 20, 1, 1])],
        quality={},
        time_range={},
        report_origin=origin,
    )
    before = deepcopy(result["topics"])
    llm = AsyncMock(configured=True)
    llm.complete.return_value = reply_for(module.payload_for(result))
    original = module.writing_decision

    def code_action(fact):
        decision = original(fact)
        if repeat_missing and fact["kind"] == "relative_activity":
            decision["action"] = decision["action"].replace("·메모리 요구", "")
        return decision

    with patch.object(module, "writing_decision", side_effect=code_action):
        await module.interpret_report(result, llm)
    assert result["topics"] == before
    if repeat_missing:
        assert llm.complete.call_count == 0
        assert result["quality"]["report"]["reason"] == "invalid_code_advice"
        assert result["narrative_status"] == "failed"
    else:
        assert llm.complete.call_count == 1 and result["narrative_status"] == "complete"
        relative = next(
            a
            for a in result["narrative"][0]["advice"]
            if a["kind"] == "relative_activity"
        )
        assert "메모리 요구를 확인한 뒤" in relative["summary"]


def test_relative_memory_check_does_not_bypass_existing_reference_validation():
    from ops_agent.report_interpretation import validate_written_advice

    fact = next(
        f
        for f in candidates(pattern_topic([70, 80, 20, 25]))
        if f["kind"] == "relative_activity"
    )
    raw = {
        "advice": [
            {
                "fact_id": fact["fact_id"],
                "summary": "마감·예약·가용 GPU를 확인한 뒤 작업 일부의 시작 시각 조정 시범 실행을 검토하세요. {{memory}}",
            }
        ]
    }
    with pytest.raises(ValueError, match="namespace_summary_tokens_required"):
        validate_written_advice(raw, {"findings": [fact]})
