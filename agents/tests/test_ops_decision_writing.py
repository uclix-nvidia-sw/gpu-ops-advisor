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

    combined = "가" * sent["prose_max_chars"] + " " + context["summary_start"]
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
        summary = ""
        if problem == "overlong" and len(requests) == 1:
            summary = "관측 " * 49 + summary
        if len(requests) == 2:
            summary = (
                "활동률이 낮았던 구간에 작업 일부의 시작 시간을 조정할지, "
                "마감·예약·가용 GPU·메모리 요구를 확인한 뒤 시범 실행을 검토하세요. "
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
        assert "required_summary_tokens" not in item and "summary_start" not in item
        assert item["observed_values"] == {
            k[2:-2]: v for k, v in context["summary_tokens"].items()
        }
        assert context["decision"]["option"] not in str(item)
    assert requests[0]["response_shape"]["sections"][0]["advice"][0]["summary"] == ""
    assert requests[1]["response_shape"]["advice"][0]["summary"] == ""
    assert "설명을 비워서는 안 됩니다" in requests[1]["instruction"]
    assert "필수 확인 조건은 보존" in requests[1]["instruction"]
    assert (
        "시작 시각을 조정할 수 있는 작업 일부의 시범 실행 여부"
        in requests[1]["instruction"]
    )
    assert (
        "시작 시각을 조정할 수 있는 작업 일부의 시범 실행 여부"
        in llm.complete.call_args.args[0]
    )
    assert "조정해 시범 실행할지 검토" not in requests[1]["instruction"]
    assert result["quality"]["report"]["failures"][0]["reason"] == (
        "invalid_namespace_advice_text"
        if problem == "overlong"
        else "actionable_namespace_summary_required"
    )
    assert result["quality"]["report"]["reason"] == "repaired"
    assert result["topics"] == before["topics"]


@pytest.mark.parametrize("phase", ["placement", "preparation", "unknown"])
def test_writer_check_matches_queue_stage_without_inventing_coverage(phase):
    from ops_agent.report_interpretation import writing_context

    source = topic(pending=2)
    for hour in source["workloads"][0]["hours"]:
        hour.update(
            unscheduled_peak=2 if phase == "placement" else 0,
            unscheduled_samples=240 if phase != "unknown" else 1,
        )
    fact = next(f for f in candidates(source) if f["kind"] == "queue_review")
    before = deepcopy(fact)
    sent = writing_context(fact)
    assert sent["queue_context"]["check_first"] == phase
    checks = " ".join(sent["writing_checks"])
    assert "확인·대조·검토·점검" in checks
    if phase == "placement":
        assert "스케줄러 이벤트·GPU 요청·노드 선택 조건" in checks
    elif phase == "preparation":
        assert "이미지 다운로드·초기화 이벤트" in checks
        assert "스케줄러 이벤트" not in checks
    else:
        assert "일부 미배치 영을 배정 완료로 바꾸지 않음" in checks
        assert "writing_focus" not in sent
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
    checks = " ".join(sent["writing_checks"])
    assert "이 후보의 완료 Job에 테스트 유형이 연결됨" in sent["decision"]["known"]
    assert "유형 확인·재수집 요청 대신 확인된 테스트 작업으로 현상을 설명" in checks
    assert "실제 Pod 시작·완료 기록" in checks
    assert "남은 대기" not in checks
    assert "미확인 유형만 확인" not in checks
    assert fact == before


async def test_missing_check_verb_is_repaired_without_relaxing_guard():
    from unittest.mock import AsyncMock
    from ops_agent.report_interpretation import interpret_report, payload_for
    from test_namespace_advice import writer_section

    result = dict(topics=[topic(pending=2)], quality={}, time_range={})
    before = deepcopy(result["topics"])
    facts = payload_for(result)["topics"][0]["findings"]
    valid = writer_section(facts)
    invalid = deepcopy(valid)
    invalid["advice"][0]["summary"] = (
        "노드 배정 자료는 일부입니다. 대기 Pod 상태·이벤트에서 노드를 기다리는지 컨테이너 시작을 준비 중인지 구분하세요."
    )
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [{"sections": [invalid]}, {"advice": valid["advice"]}]
    await interpret_report(result, llm)
    first, repair = [c.args[1] for c in llm.complete.call_args_list]
    for context in (first["topics"][0]["findings"][0], repair["summary_repair"][0]):
        assert "확인·대조·검토·점검" in " ".join(context["writing_checks"])
        assert "writing_focus" not in context
    assert "행동 동사를 직접" in repair["instruction"]
    assert (
        result["quality"]["report"]["failures"][0]["reason"]
        == "actionable_namespace_summary_required"
    )
    assert result["quality"]["report"]["reason"] == "repaired"
    assert result["topics"] == before


@pytest.mark.parametrize(
    "problem,code",
    [
        ("partial_zero", "partial_placement_is_not_absence"),
        ("absent_target", "unobserved_pending_target"),
        ("missing_policy", "namespace_prerequisites_required"),
        ("change_first", "review_before_schedule_change"),
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
        "partial_zero": "대기 Pod가 관측됐으나 노드 미배정은 없었으므로, Pod 상태·이벤트를 점검해 대기 단계를 구분하세요.",
        "absent_target": "낮은 GPU 활동과 대기 없음이 관측된 이 네임스페이스의 대기 Pod 일부에 대해, 마감·예약·대기·가용 GPU를 확인한 뒤 작업 일부의 시범 실행을 검토하세요.",
        "missing_policy": "높은 GPU 활동과 대기가 관측돼 스케줄러 사유와 GPU 요청·실제 할당·보장량·가용 GPU를 확인한 뒤 추가 할당을 검토하세요.",
        "change_first": "마감·예약·가용 GPU·메모리 요구를 확인한 뒤 일부 작업의 시작 시각을 조정해 시범 실행을 검토하세요.",
    }[problem]
    target = {"findings": [next(f for f in facts if f["fact_id"] == item["fact_id"])]}
    from ops_agent.report_interpretation import advice_with_evidence

    # The existing validator accepts this captured failure class; keep its gates unchanged.
    assert validate_advice(advice_with_evidence({"advice": [item]}, target), target)
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
    text = "GPU 활동과 대기가 관측돼, 스케줄러 사유·GPU 요청·실제 할당·보장량·가용 GPU·운영정책·작업 기록을 확인한 뒤 추가 할당을 검토하세요."
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
    invalid["advice"][0]["summary"] = (
        "대기 Pod 일부의 시작 시간을 조정할지 마감·예약·대기·가용 GPU를 확인한 뒤 일부 작업의 시범 실행을 검토하세요."
    )
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
    from ops_agent.report_interpretation import partial_repair, validate_written_advice
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
    kept = validate_written_advice(section, offered)
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
        "추가 할당을 검토하려면 GPU 요청·실제 할당·보장량·가용 GPU·스케줄러 사유·운영정책을 확인·대조한 뒤에만 변경 여부를 판단하세요.",
        "추가 할당을 조건부 검토하되 GPU 요청·실제 할당·보장량·가용 GPU·스케줄러 사유·운영정책을 확인한 뒤에만 판단하세요.",
        "GPU 요청·실제 할당·보장량·가용 GPU·스케줄러 사유를 확인·대조한 뒤 운영정책을 점검하고 추가 할당을 검토하세요.",
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
    assert "기존 조건을 옮기거나 삭제하지 말고" in str(error.value)


@pytest.mark.parametrize("origin", ["schedule", "manual"])
async def test_all_prerequisites_reach_initial_and_repair_input(origin):
    from unittest.mock import AsyncMock
    from ops_agent.namespace_advice import SYSTEM
    from ops_agent.report_interpretation import interpret_report, payload_for
    from test_namespace_advice import writer_section

    result = dict(
        topics=[topic(activity=90, pending=2)],
        quality={},
        time_range={},
        report_origin=origin,
    )
    before = deepcopy(result["topics"])
    valid = writer_section(payload_for(result)["topics"][0]["findings"])
    invalid = deepcopy(valid)
    invalid["advice"][0]["summary"] = invalid["advice"][0]["summary"].replace(
        "·운영정책", ""
    )
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [{"sections": [invalid]}, {"advice": valid["advice"]}]
    await interpret_report(result, llm)
    first, repair = [c.args[1] for c in llm.complete.call_args_list]
    required = [
        "스케줄러 사유",
        "GPU 요청",
        "실제 할당",
        "보장량",
        "가용 GPU",
        "운영정책",
    ]
    for context in (first["topics"][0]["findings"][0], repair["summary_repair"][0]):
        assert context["required_checks"] == required
    assert all(
        word in repair["summary_repair"][0]["validation_error"] for word in required
    )
    assert "모든 항목을 확인·대조·점검한 뒤" in SYSTEM
    assert "활동률 문장의 주어는 연결 GPU" in SYSTEM
    assert "정상 항목은 바꾸지 말고" in SYSTEM
    assert result["narrative_status"] == "complete"
    assert result["topics"] == before


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
