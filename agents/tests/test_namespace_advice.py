"""Conditional Ops proposals must retain the existing numeric report unchanged."""

from copy import deepcopy
from unittest.mock import AsyncMock
import json
import pytest
from ops_agent.namespace_advice import (
    candidates,
    present_advice,
    decision_context,
    elapsed_range,
    select_candidates,
    writing_candidates,
    summary_context,
    validate_advice,
    SYSTEM,
    WRITING_FOCUS,
    VALUE_MEANINGS,
)
from ops_agent.report_interpretation import (
    interpret_report,
    payload_for,
    writing_context,
    advice_with_evidence,
    validate_reasoned_advice,
)
from agent_common.llm import LLM
from agent_common.settings import Settings


@pytest.mark.parametrize("origin", ["schedule", "manual"])
@pytest.mark.parametrize("problem", ["period", "duplicate", "unavailable"])
async def test_reference_failure_details_do_not_store_model_text(origin, problem):
    result = dict(
        topics=[topic(pending=2)], quality={}, time_range={}, report_origin=origin
    )
    before = deepcopy(result["topics"])
    reply = {"sections": [writer_section(payload_for(result)["topics"][0]["findings"])]}
    item = reply["sections"][0]["advice"][0]
    expected = {"missing": [], "duplicate": [], "unavailable_count": 0}
    if problem == "period":
        item["summary"] += " {{period}}"
        expected["duplicate"] = ["period"]
    elif problem == "duplicate":
        item["summary"] += " {{pending}}"
        expected["duplicate"] = ["pending"]
    else:
        item["summary"] += " {{private_response}}"
        expected["unavailable_count"] = 1
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [reply, {"advice": [item]}]
    await interpret_report(result, llm)
    repair = llm.complete.call_args.args[1]
    example = repair["response_shape"]["advice"][0]["summary"]
    context = repair["summary_repair"][0]
    assert example == ""
    assert "option" not in context["decision"]
    assert "summary_start" not in context
    assert "required_summary_tokens" not in context
    assert context["observed_values"]["pending"] == "2개"
    assert result["quality"]["report"]["failures"] == [
        {
            "attempt": attempt,
            "reason": "namespace_summary_tokens_required",
            "reference_errors": expected,
        }
        for attempt in (1, 2)
    ]
    assert result["narrative_status"] == "failed"
    assert result["topics"] == before
    assert "private_response" not in json.dumps(result)


def topic(activity=1, pending=0, memory=10, samples=240):
    hours = []
    work = []
    mem = []
    metrics = []
    for i in range(3):
        p = dict(start=f"2026-10-14T0{i}:00:00Z", end=f"2026-10-14T0{i + 1}:00:00Z")
        hours.append(
            dict(
                **p,
                activity_percent=activity,
                sample_count=240,
                gpu_ids=["g"],
                reasons=[],
            )
        )
        work.append(dict(**p, pending_peak=pending, pending_samples=samples))
        mem.append(dict(**p, used_gib_per_gpu=memory, free_gib_per_gpu=100 - memory))
        metrics.append(
            dict(
                id=f"namespace_usage.hourly_activity.{i}",
                value=activity,
                target={
                    "cluster_id": "cpc-1",
                    "namespace": "research",
                    "model": "A100",
                },
                period=p,
                unit="percent",
                quality={},
            )
        )
    return dict(
        topic_id="namespace_usage",
        status="ready",
        missing_inputs=[],
        findings=[],
        metrics=metrics,
        rows=[
            dict(
                cluster_id="cpc-1",
                namespace="research",
                gpu_model="A100",
                hours=hours,
                evidence_refs=["a"],
                gpu_memory={"hours": mem, "evidence_refs": ["m"]},
            )
        ],
        workloads=[
            dict(
                cluster_id="cpc-1",
                namespace="research",
                hours=work,
                evidence_refs=["w"],
            )
        ],
    )


def writer_section(facts):
    """Model fixture for the reason-only writing contract, not an LLM result."""
    observations = {
        "capacity_review": "연결 GPU 활동률이 높았고 실행을 기다리는 Pod도 관측됐습니다.",
        "schedule_candidate": "연결 GPU 활동률이 낮았던 구간입니다.",
        "queue_review": "대기 Pod가 관측됐으며 기록만으로 원인은 확인되지 않았습니다.",
        "resident_memory": "연결 GPU 활동률은 낮았지만 메모리 점유는 높았습니다.",
        "repeated_activity": "서로 떨어진 여러 구간에 높은 연결 GPU 활동률과 대기가 관측됐습니다.",
        "relative_activity": "비교 구간보다 연결 GPU 활동률이 낮았습니다.",
        "batch_progress": "완료가 확인된 Job 일부의 경과 기록이 있습니다.",
    }
    return {
        "topic_id": "namespace_usage",
        "advice": [
            {"fact_id": f["fact_id"], "summary": observations[f["kind"]]}
            for f in facts[:5]
        ],
    }


def prose_section(facts):
    checks = {
        "capacity_review": "스케줄러 사유와 GPU 요청·실제 할당을 대조해 자원 부족 여부를 확인하고 보장량·가용 GPU·운영정책을 확인한 뒤 추가 할당을 검토하세요.",
        "schedule_candidate": "작업 마감·예약·대기·가용 GPU를 확인한 뒤 일부 작업의 시작 시각 조정과 시범 실행을 검토하세요.",
        "queue_review": "대기 Pod의 상태·스케줄러 이벤트를 대조해 노드 배정 전인지 준비 단계인지 확인하세요.",
        "resident_memory": "상주 서빙과 캐시 유지 목적을 확인하세요.",
        "repeated_activity": "관측 구간의 대기 작업에 필요한 GPU 요청·실제 할당과 스케줄러 이벤트를 대조하세요.",
        "relative_activity": "마감·예약·가용 GPU·메모리 요구를 확인한 뒤 시작 시각 조정이 가능한 작업 일부의 시범 실행을 검토하세요.",
        "batch_progress": "완료 Job 일부의 작업 유형과 실제 Pod 시작·완료 기록을 대조하세요.",
    }
    return {
        "topic_id": "namespace_usage",
        "advice": [
            {"fact_id": f["fact_id"], "summary": checks[f["kind"]]} for f in facts[:5]
        ],
    }


def section(facts):
    checks = {
        "capacity_review": "현재 할당량과 보장량·스케줄러 기록을 대조한 뒤 확대 여부를 검토하세요.",
        "schedule_candidate": "작업 마감·예약 일정과 대기 상태를 확인한 뒤 이 시간대 배치 작업 실행을 검토하세요.",
        "queue_review": "스케줄러 이벤트와 배치 제약을 먼저 대조하세요.",
        "resident_memory": "상주 서빙과 캐시 유지 여부를 확인하세요.",
        "repeated_activity": "여러 시간의 고활동과 대기가 관측된 이 대상의 GPU 요청·할당과 스케줄러 이벤트를 대조하세요.",
        "relative_activity": "마감·예약·가용 GPU·메모리 요구를 확인한 뒤 조정 가능한 작업 일부를 후보 시간으로 옮겨 시범 실행할지 검토하세요.",
    }
    facts = list(
        {
            (
                f.get("target", {}).get("cluster_id")
                or f["summary_tokens"]["{{target}}"].split(" / ")[0],
                f["kind"],
            ): f
            for f in reversed(facts)
        }.values()
    )
    facts.sort(key=lambda f: f["kind"] != "batch_progress")
    if facts and facts[0]["kind"] == "batch_progress":
        batch_targets = [
            f.get("summary_tokens", {}).get("{{target}}") or str(f.get("target"))
            for f in facts
            if f["kind"] == "batch_progress"
        ]
        advice = []
        for f in facts[:5]:
            if (
                f["kind"] == "queue_review"
                and (
                    f.get("summary_tokens", {}).get("{{target}}")
                    or str(f.get("target"))
                )
                in batch_targets
            ):
                continue
            if f["kind"] == "batch_progress":
                tokens = f.get("summary_tokens") or summary_context(f)["summary_tokens"]
                text = "{{target}} · {{period}}: 완료 표본은 {{completed}}, 대기·준비 포함 Job 경과시간은 {{elapsed}}입니다. "
                if "{{pending_change}}" in tokens:
                    text += "시간대별 최대 대기 Pod 수는 {{pending_change}}입니다. "
                advice.append(
                    dict(
                        fact_id=f["fact_id"],
                        summary=text
                        + "다음 배치의 제출 시점과 작업 규모를 기록과 대조하여 제출 간격을 검토하세요.",
                    )
                )
            else:
                advice.extend(section([f])["advice"])
        return dict(topic_id="namespace_usage", advice=advice)
    return dict(
        topic_id="namespace_usage",
        advice=[
            dict(
                fact_id=f["fact_id"],
                summary=(
                    checks[f["kind"]]
                    + " "
                    + (f.get("summary_start") or summary_context(f)["summary_start"])
                )
                if f["kind"] in ("repeated_activity", "relative_activity")
                else "{{target}} · {{period}}: "
                + (
                    "GPU 활동률은 {{activity}}입니다. "
                    if (
                        "{{activity}}" in f["summary_tokens"]
                        if "summary_tokens" in f
                        else "활동률 연결 근거 부족" not in f["observation"]
                    )
                    else "GPU 활동률은 미확인입니다. "
                )
                + (
                    "대기 Pod 수는 최대 {{pending}}입니다. "
                    if f["kind"] in ("queue_review", "capacity_review")
                    else ""
                )
                + (
                    "메모리 사용 비율은 {{memory}}입니다. "
                    if f["kind"] == "resident_memory"
                    else ""
                )
                + checks[f["kind"]],
            )
            for f in facts[:5]
        ],
    )


def test_pressure_only_from_same_hour_full_activity_and_queue():
    t = topic(activity=90, pending=2)
    before = deepcopy(t)
    p = candidates(t)
    assert p[0]["kind"] == "capacity_review"
    assert "90.00" in p[0]["observation"]
    assert t == before
    assert "추가 수량은 산정하지" in p[0]["conditions"]


@pytest.mark.parametrize(
    "problem",
    [
        "other_hour",
        "partial_workload",
        "partial_activity",
        "model_missing",
        "identity_invalid",
    ],
)
def test_pressure_not_inferred_from_misaligned_or_incomplete_observations(problem):
    t = topic(activity=90, pending=2)
    if problem == "other_hour":
        t["workloads"][0]["hours"] = [
            dict(
                start="2026-10-15T00:00:00Z",
                end="2026-10-15T01:00:00Z",
                pending_peak=2,
                pending_samples=240,
            )
        ]
    if problem == "partial_workload":
        for h in t["workloads"][0]["hours"]:
            h["pending_samples"] = 20
    if problem == "partial_activity":
        for h in t["rows"][0]["hours"]:
            h["sample_count"] = 10
    if problem == "model_missing":
        other = deepcopy(t["rows"][0])
        other["gpu_model"] = "V100"
        for h in other["hours"]:
            h["activity_percent"] = None
        t["rows"].append(other)
    if problem == "identity_invalid":
        for h in t["rows"][0]["hours"]:
            h["reasons"] = ["overlap"]
    p = candidates(t)
    assert p[0]["kind"] == "queue_review"


def test_low_activity_becomes_conditional_time_candidate_not_free_capacity():
    t = topic()
    p = candidates(t)
    assert p[0]["kind"] == "schedule_candidate"
    assert p[0]["period"] == dict(
        start="2026-10-14T00:00:00Z", end="2026-10-14T03:00:00Z"
    )
    assert "가용성을 보장하지" in p[0]["conditions"]
    t["workloads"] = []
    p = candidates(t)
    assert p[0]["kind"] == "schedule_candidate"
    assert "대기 관측은 미확인" in p[0]["observation"]


def test_high_memory_blocks_time_recommendation():
    t = topic(memory=98)
    p = candidates(t)
    assert p[0]["kind"] == "resident_memory"
    t["rows"][0]["gpu_memory"]["hours"] = []
    assert candidates(t)[0]["kind"] == "schedule_candidate"
    assert "메모리 근거는" in candidates(t)[0]["observation"]


@pytest.mark.parametrize(
    "problem", ["gap", "short", "identity_change", "null", "nan", "bool"]
)
def test_quiet_windows_require_complete_contiguous_stable_activity(problem):
    t = topic()
    hs = t["rows"][0]["hours"]
    if problem == "gap":
        t["rows"][0]["hours"] = [hs[0], hs[2]]
    if problem == "short":
        t["rows"][0]["hours"] = [hs[0]]
    if problem == "identity_change":
        for i, h in enumerate(hs):
            h["gpu_ids"] = [f"g{i}"]
    if problem in ("null", "nan", "bool"):
        for h in hs:
            h["activity_percent"] = {"null": None, "nan": float("nan"), "bool": True}[
                problem
            ]
    assert candidates(t) == []


def test_pending_low_activity_gets_scheduler_check_not_capacity():
    p = candidates(topic(activity=1, pending=4))
    assert p[0]["kind"] == "queue_review"
    assert "할당 확대를 추천하지" in p[0]["conditions"]


@pytest.mark.parametrize(
    "problem",
    [
        "unknown_id",
        "duplicate",
        "number",
        "cause",
        "duration",
        "recurrence",
        "unsupported_capacity",
        "generic_check",
        "writer_instruction",
    ],
)
def test_model_prose_cannot_expand_permission_or_invent_observations(problem):
    p = candidates(topic())
    s = section(p)
    item = s["advice"][0]
    if problem == "unknown_id":
        item["fact_id"] = "other"
    if problem == "duplicate":
        s["advice"] *= 2
    if problem == "number":
        item["summary"] += "GPU를 2개 더 주세요."
    if problem == "cause":
        item["summary"] += "GPU 부족이 원인입니다."
    if problem == "duration":
        item["summary"] += "대기 시간이 감소했습니다."
    if problem == "recurrence":
        item["summary"] += "매일 반복되는 패턴입니다."
    if problem == "unsupported_capacity":
        item["summary"] += "할당 확대를 검토하세요."
    if problem == "writer_instruction":
        item["summary"] += "다음 배치의 실행 시간 후보로 검토하도록 쓰세요."
    if problem == "generic_check":
        item["summary"] = (
            "{{target}} · {{period}}: 활동률은 {{activity}}입니다. 자료를 확인하세요."
        )
    with pytest.raises(ValueError):
        validate_advice(s, dict(findings=p))


def test_more_than_five_advice_items_gets_actionable_repair_feedback():
    facts = candidates(topic())
    reply = section(facts)
    reply["advice"] *= 6
    with pytest.raises(ValueError, match="1~5개"):
        validate_advice(reply, dict(findings=facts))


def test_job_elapsed_summary_uses_readable_exact_duration():
    assert elapsed_range([10809, 21617]) == "3시간 9초~6시간 17초"
    assert elapsed_range([0]) == "0초"
    assert elapsed_range([1209]) == "20분 9초"


async def test_new_interpretation_preserves_all_original_calculations_and_fallback():
    t = topic(activity=90, pending=2)
    r = dict(
        topics=[t],
        time_range={"start": "2026-10-13T15:00:00Z", "end": "2026-10-14T15:00:00Z"},
        quality={},
        limitations=[],
    )
    before = deepcopy(r)
    p = payload_for(r)
    assert p["topics"][0]["advice_mode"]
    llm = AsyncMock(configured=True)
    llm.complete.return_value = {
        "sections": [writer_section(p["topics"][0]["findings"])]
    }
    await interpret_report(r, llm)
    assert r["narrative_status"] == "complete"
    assert r["topics"] == before["topics"]
    assert r["time_range"] == before["time_range"]
    assert r["narrative"][0]["advice"][0]["recommendation"] == "GPU 할당 확대 검토"
    r = deepcopy(before)
    llm.complete.return_value = {"sections": []}
    await interpret_report(r, llm)
    assert r["narrative_status"] == "failed"
    assert r["topics"] == before["topics"]


def test_bounded_payload_fits_existing_attempt_budget():
    p = candidates(topic())
    wire = {
        "topics": [
            {
                "topic_id": "namespace_usage",
                "findings": [
                    {
                        k: v
                        for k, v in p[0].items()
                        if k
                        in (
                            "fact_id",
                            "kind",
                            "target",
                            "period",
                            "observation",
                            "conditions",
                            "recommendation",
                        )
                    }
                ],
            }
        ]
    }
    budget = LLM(Settings(kind="report"), 0, 32768, lambda state: None).request_budget(
        SYSTEM, wire, "synthesis"
    )
    assert budget["output_token_cap"] > 4096
    assert len(json.dumps(wire, ensure_ascii=False).encode()) < 32000


def test_unknown_activity_and_resident_memory_cannot_be_rewritten_as_capacity():
    t = topic(pending=2)
    for h in t["rows"][0]["hours"]:
        h["activity_percent"] = None
    p = candidates(t)
    reply = section(p)
    reply["advice"][0]["summary"] += (
        "연산 활동이 낮아서 자원 부족을 판단하기 어렵습니다."
    )
    with pytest.raises(ValueError, match="unobserved_activity_claim"):
        validate_advice(reply, dict(findings=p))
    p = candidates(topic(memory=98))
    reply = section(p)
    reply["advice"][0]["summary"] += (
        "상주 서빙을 점검한 뒤 메모리 추가 할당을 검토하세요."
    )
    with pytest.raises(ValueError, match="unsupported_capacity"):
        validate_advice(reply, dict(findings=p))


def test_each_offered_cluster_must_be_represented():
    t = topic()
    second = deepcopy(t["rows"][0])
    second["cluster_id"] = "cpc-2"
    t["rows"].append(second)
    p = candidates(t)
    reply = section(p)
    validate_advice(reply, dict(findings=p))
    reply["advice"] = reply["advice"][:1]
    with pytest.raises(ValueError):
        validate_advice(reply, dict(findings=p))


def test_unknown_queue_cannot_prefer_a_placement_cause():
    t = topic(pending=2)
    for h in t["rows"][0]["hours"]:
        h["activity_percent"] = None
    p = candidates(t)
    reply = section(p)
    reply["advice"][0]["summary"] += "자원 부족보다는 배치 제약을 의심할 수 있습니다."
    with pytest.raises(ValueError, match="unsupported_queue_cause"):
        validate_advice(reply, dict(findings=p))


async def test_advice_with_a_metricless_other_topic_keeps_the_fallback():
    r = dict(
        topics=[
            topic(),
            dict(
                topic_id="incident_summary",
                status="blocked",
                findings=[
                    dict(
                        id="no-metric",
                        text="자료 확인이 필요합니다.",
                        target={},
                        evidence_refs=[],
                        value_refs=[],
                    )
                ],
                metrics=[],
            ),
        ],
        time_range={},
        quality={},
        limitations=[],
    )
    before = deepcopy(r["topics"])
    llm = AsyncMock(configured=True)
    llm.complete.return_value = {"sections": []}
    await interpret_report(r, llm)
    assert r["narrative_status"] == "failed"
    assert r["topics"] == before


def test_unknown_activity_does_not_reject_direct_relationship_wording():
    t = topic(pending=2)
    for h in t["rows"][0]["hours"]:
        h["activity_percent"] = None
    p = candidates(t)
    reply = section(p)
    reply["advice"][0]["summary"] += (
        "대기 중인 Pod가 관측되었으나 활동률과 직접적인 연관 자료가 부족합니다."
    )
    validate_advice(reply, dict(findings=p))


def test_summary_is_the_model_sentence_with_only_verified_token_substitution():
    p = candidates(topic(activity=0.74, pending=0))
    reply = section(p)
    raw = reply["advice"][0]["summary"]
    out = validate_advice(reply, dict(findings=p))["advice"][0]
    assert out["summary_source"] == "llm"
    assert "cpc-1 / research" in out["summary"]
    assert "10/14 09:00~10/14 12:00 KST" in out["summary"]
    assert "0.74%" in out["summary"]
    assert out["summary"].endswith(raw.split("}}: ")[1].split("}}", 1)[-1])
    assert "{{" not in out["summary"]


@pytest.mark.parametrize(
    "problem",
    [
        "missing_summary",
        "missing_period",
        "invented_value",
        "unknown_token",
        "long",
        "newline",
        "absent_jobs",
        "absent_activity",
        "generic_action",
    ],
)
def test_summary_cannot_hide_unsupported_claims_or_omit_its_context(problem):
    p = candidates(topic())
    reply = section(p)
    item = reply["advice"][0]
    if problem == "missing_summary":
        item.pop("summary")
    elif problem == "missing_period":
        item["summary"] = item["summary"].replace("{{period}}", "")
    elif problem == "invented_value":
        item["summary"] += " 활동률은 0%입니다."
    elif problem == "unknown_token":
        item["summary"] += " {{invented}}"
    elif problem == "long":
        item["summary"] += "길게 " * 100
    elif problem == "newline":
        item["summary"] += "\n"
    elif problem == "absent_jobs":
        item["summary"] += " 작업이 없었습니다."
    elif problem == "absent_activity":
        item["summary"] += " 활동이 없었습니다."
    elif problem == "generic_action":
        item["summary"] = (
            "{{target}} · {{period}}: 활동률은 {{activity}}입니다. 확인하세요."
        )
    with pytest.raises(ValueError):
        validate_advice(reply, dict(findings=p))


def test_unknown_pending_remains_in_conditions_without_a_false_zero_in_summary():
    p = candidates(topic(pending=None))
    reply = section(p)
    reply["advice"][0]["summary"] = reply["advice"][0]["summary"].replace(
        "과 대기 상태", ""
    )
    output = validate_advice(reply, dict(findings=p))["advice"][0]
    assert "미확인" in output["observation"]
    assert "대기 상태 확인" in output["conditions"]
    assert "0개" not in output["summary"]


def test_asking_to_check_a_pending_cause_is_not_a_cause_diagnosis():
    p = candidates(topic(pending=2))
    reply = section(p)
    reply["advice"][0]["summary"] += " 스케줄러에서 대기 원인을 확인하세요."
    reply["advice"][0]["summary"] += "스케줄러 이벤트에서 대기 원인을 확인하세요."
    validate_advice(reply, dict(findings=p))


def test_queue_evidence_alone_cannot_recommend_a_work_time():
    p = candidates(topic(pending=2))
    reply = section(p)
    reply["advice"][0]["summary"] += " 이 시간대 배치 실행을 검토하세요."
    with pytest.raises(ValueError, match="queue_is_not_a_scheduling_candidate"):
        validate_advice(reply, dict(findings=p))


@pytest.mark.parametrize("short_period", [False, True])
def test_exact_literal_summary_stays_identical_to_actual_model_prose(short_period):
    p = candidates(topic(activity=0.74, pending=0))
    raw = "cpc-1 / research는 10/14 09:00~10/14 12:00 KST에 GPU 활동률이 0.74%로 낮았습니다. 예약·대기와 사용 가능한 GPU를 확인한 뒤 이 시간대 배치 작업 실행을 검토하세요."
    if short_period:
        raw = raw.replace("~10/14 12:00", "~12:00")
    result = validate_advice(
        {"advice": [{"fact_id": p[0]["fact_id"], "summary": raw}]}, {"findings": p}
    )
    assert result["advice"][0]["summary"] == raw
    assert result["advice"][0]["summary_source"] == "llm"


@pytest.mark.parametrize("replacement", ["research-other", "xresearch", "research2"])
def test_literal_namespace_cannot_match_only_a_prefix(replacement):
    p = candidates(topic())
    raw = "cpc-1 / research · 10/14 09:00~12:00 KST: GPU 활동률은 1.00%입니다. 예약 일정을 확인한 뒤 작업 배치를 검토하세요."
    raw = raw.replace("research", replacement)
    with pytest.raises(ValueError):
        validate_advice(
            {"advice": [{"fact_id": p[0]["fact_id"], "summary": raw}]}, {"findings": p}
        )


@pytest.mark.parametrize(
    "replacement", ["0.75%", "0.74~1.00%", "10/14 08:00~12:00 KST"]
)
def test_literal_summary_must_match_the_exact_stored_value_and_period(replacement):
    p = candidates(topic(activity=0.74))
    raw = "cpc-1 / research · 10/14 09:00~12:00 KST: GPU 활동률은 0.74%입니다. 예약·대기와 사용 가능한 GPU를 확인한 뒤 작업 배치를 검토하세요."
    raw = (
        raw.replace("0.74%", replacement)
        if "%" in replacement
        else raw.replace("10/14 09:00~12:00 KST", replacement)
    )
    with pytest.raises(ValueError):
        validate_advice(
            {"advice": [{"fact_id": p[0]["fact_id"], "summary": raw}]}, {"findings": p}
        )


def test_summary_may_select_fewer_proposals_instead_of_filling_all_slots():
    t = topic()
    duplicate = deepcopy(t["rows"][0])
    duplicate["namespace"] = "another-project"
    t["rows"].append(duplicate)
    p = candidates(t)
    assert len(p) == 2
    reply = section(p)
    reply["advice"] = reply["advice"][:1]
    assert len(validate_advice(reply, dict(findings=p))["advice"]) == 1


def test_one_pending_hour_does_not_hide_another_quiet_window():
    t = topic()
    t["workloads"][0]["hours"][2]["pending_peak"] = 2
    before = deepcopy(t)
    facts = candidates(t)
    assert {f["kind"] for f in facts} == {"queue_review", "schedule_candidate"}
    assert t == before


def test_capacity_review_requires_two_adjacent_complete_hours():
    t = topic(activity=90, pending=2)
    t["workloads"][0]["hours"][1]["pending_peak"] = 0
    assert not any(f["kind"] == "capacity_review" for f in candidates(t))
    t["workloads"][0]["hours"][1]["pending_peak"] = 2
    assert any(f["kind"] == "capacity_review" for f in candidates(t))


def test_global_candidate_budget_keeps_other_cluster_and_larger_queue():
    t = topic(pending=1)
    t["rows"], t["workloads"], t["metrics"] = [], [], []
    for cluster, count in (("cpc-1", 20), ("cpc-2", 2)):
        for i in range(count):
            item = topic(pending=1 if cluster == "cpc-1" else 50)
            for field in ("rows", "workloads"):
                item[field][0].update(cluster_id=cluster, namespace=f"ns-{i:02}")
                t[field].extend(item[field])
    selected, audit = select_candidates(candidates(t))
    assert len(selected) == 12
    assert {f["target"]["cluster_id"] for f in selected} == {"cpc-1", "cpc-2"}
    assert selected[0]["selection_basis"]["pending_peak"] == 50
    assert (audit["eligible_count"], audit["omitted_count"]) == (22, 10)


def completed_topic():
    t = topic(activity=30, pending=2)
    t["workloads"][0]["hours"][0]["pending_samples"] = 212
    t["workloads"][0]["hours"][2]["pending_peak"] = 0
    t["workloads"][0]["completed_jobs"] = [
        dict(
            job_name="batch-a",
            started_at="2026-10-14T00:10:00Z",
            completed_at="2026-10-14T00:30:00Z",
            elapsed_seconds=1200,
        ),
        dict(
            job_name="batch-b",
            started_at="2026-10-14T00:10:00Z",
            completed_at="2026-10-14T01:10:00Z",
            elapsed_seconds=3600,
        ),
        dict(
            job_name="outside",
            started_at="2026-10-13T21:00:00Z",
            completed_at="2026-10-13T22:00:00Z",
            elapsed_seconds=3600,
        ),
    ]
    return t


def test_batch_window_uses_exact_completion_samples_not_report_average():
    t = completed_topic()
    before = deepcopy(t)
    fact = next(f for f in candidates(t) if f["kind"] == "batch_progress")
    values = summary_context(fact)["summary_tokens"]
    assert values["{{completed}}"] == "1건"
    assert values["{{elapsed}}"] == "1시간"
    assert values["{{pending_change}}"] == "2개 → 0개"
    assert len(fact["completed_jobs"]) == 1
    assert fact["selection_basis"]["pending_complete"]
    assert t == before


def batch_section(fact):
    return {
        "advice": [
            {
                "fact_id": fact["fact_id"],
                "summary": "{{target}} · {{period}}: 시간대별 최대 대기 Pod 수는 {{pending_change}}이며 완료 표본은 {{completed}}, 대기·준비 포함 Job 경과시간은 {{elapsed}}입니다. 스케줄러 대기 사유와 완료 Job의 작업 유형을 확인하세요.",
            }
        ]
    }


def test_batch_summary_is_model_prose_and_cannot_claim_waiting_time_or_throughput():
    fact = next(
        f for f in candidates(completed_topic()) if f["kind"] == "batch_progress"
    )
    reply = batch_section(fact)
    out = validate_advice(reply, {"findings": [fact]})
    assert "2개 → 0개" in out["advice"][0]["summary"]
    for claim in (
        "대기 시간이 줄었습니다.",
        "모든 작업이 완료됐습니다.",
        "처리량이 개선됐습니다.",
    ):
        broken = deepcopy(reply)
        broken["advice"][0]["summary"] += claim
        with pytest.raises(ValueError):
            validate_advice(broken, {"findings": [fact]})


def test_batch_source_gaps_or_unobserved_final_queue_do_not_become_zero():
    t = completed_topic()
    t["workloads"][0]["hours"][2]["pending_samples"] = 100
    t["workloads"][0]["hours"][2]["pending_peak"] = None
    facts = candidates(t)
    fact = next(f for f in facts if f["kind"] == "batch_progress")
    assert fact["pending_change"] is None or fact["pending_change"][1] != 0
    assert (
        "{{pending_change}}" not in summary_context(fact)["summary_tokens"]
        or summary_context(fact)["summary_tokens"]["{{pending_change}}"] != "2개 → 0개"
    )


def test_completed_only_hour_does_not_attach_jobs_outside_its_reported_period():
    t = completed_topic()
    for h in t["workloads"][0]["hours"]:
        h["pending_peak"] = 0
    fact = next(f for f in candidates(t) if f["kind"] == "batch_progress")
    assert all(
        fact["period"]["start"] <= j["completed_at"] < fact["period"]["end"]
        for j in fact["completed_jobs"]
    )


def test_batch_summary_must_be_selected_and_duplicate_queue_checks_are_folded():
    t = completed_topic()
    t["workloads"][0]["hours"][0]["pending_samples"] = 240
    facts = candidates(t)
    queue = next(f for f in facts if f["kind"] == "queue_review")
    batch = next(f for f in facts if f["kind"] == "batch_progress")
    with pytest.raises(ValueError, match="batch_progress_summary_required"):
        validate_advice(section([queue]), {"findings": facts})
    reply = {"advice": batch_section(batch)["advice"] + section([queue])["advice"]}
    out = validate_advice(reply, {"findings": facts})
    assert [item["fact_id"] for item in out["advice"]] == [batch["fact_id"]]
    assert out["source_fact_ids"] == [batch["fact_id"]]


def test_incomplete_batch_is_not_offered_as_joined_operational_advice():
    t = completed_topic()
    t["workloads"][0]["hours"][1]["pending_samples"] = 100
    facts = candidates(t)
    selected, audit = select_candidates(facts)
    assert all(f["kind"] != "batch_progress" for f in selected)
    assert audit["required_batch_fact_id"] is None
    assert any(f["kind"] == "queue_review" for f in selected)


def test_complete_batch_remains_available_and_mandatory():
    t = completed_topic()
    t["workloads"][0]["hours"][0]["pending_samples"] = 240
    facts = candidates(t)
    selected, audit = select_candidates(facts)
    batch = next(f for f in selected if f["kind"] == "batch_progress")
    assert audit["required_batch_fact_id"] == batch["fact_id"]


def test_complete_queue_and_jobs_remain_eligible_when_gpu_activity_has_gaps():
    t = completed_topic()
    t["rows"][0]["hours"][1]["reasons"] = ["unobserved_hour"]
    selected, audit = select_candidates(candidates(t))
    batch = next(f for f in selected if f["kind"] == "batch_progress")
    assert not batch["selection_basis"]["activity_aligned"]
    assert batch["selection_basis"]["pending_complete"]
    assert "{{activity}}" not in summary_context(batch)["summary_tokens"]
    assert audit["required_batch_fact_id"] == batch["fact_id"]


def test_batch_summary_rejects_unsupported_submission_change():
    fact = next(
        f for f in candidates(completed_topic()) if f["kind"] == "batch_progress"
    )
    reply = batch_section(fact)
    reply["advice"][0]["summary"] += " 다음 배치의 제출 간격을 검토하세요."
    with pytest.raises(ValueError, match="unsupported_submission_change"):
        validate_advice(reply, {"findings": [fact]})


@pytest.mark.parametrize("particle, expected", [("가", "이"), ("와", "과")])
def test_batch_summary_normalizes_completed_count_particle(particle, expected):
    fact = next(
        f for f in candidates(completed_topic()) if f["kind"] == "batch_progress"
    )
    reply = batch_section(fact)
    reply["advice"][0]["summary"] = reply["advice"][0]["summary"].replace(
        "완료 표본은 {{completed}}", f"{{{{completed}}}}{particle} 완료"
    )
    result = validate_advice(reply, {"findings": [fact]})
    assert f"1건{expected} 완료" in result["advice"][0]["summary"]


def test_four_cluster_weekly_candidate_selection_preserves_each_cluster_and_kind():
    from datetime import datetime, timedelta, timezone

    t = topic()
    t["rows"], t["workloads"], t["metrics"] = [], [], []
    for i in range(100):
        source = topic(
            activity=90 if i % 3 == 0 else 1,
            pending=2 if i % 3 == 0 else 0,
            memory=98 if i % 3 == 1 else 1,
        )
        for field in ("rows", "workloads"):
            row = source[field][0]
            row.update(cluster_id=f"cpc-{i % 4 + 1}", namespace=f"ns-{i:03}")
            seed = row["hours"][0]
            row["hours"] = []
            for hour in range(168):
                at = datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(hours=hour)
                row["hours"].append(
                    {
                        **deepcopy(seed),
                        "start": at.isoformat().replace("+00:00", "Z"),
                        "end": (at + timedelta(hours=1))
                        .isoformat()
                        .replace("+00:00", "Z"),
                    }
                )
            if field == "rows":
                row["gpu_memory"]["hours"] = [
                    {
                        **h,
                        "used_gib_per_gpu": 98 if i % 3 == 1 else 1,
                        "free_gib_per_gpu": 2 if i % 3 == 1 else 99,
                    }
                    for h in row["hours"]
                ]
            t[field].append(row)
    before = deepcopy(t)
    selected, audit = select_candidates(candidates(t))
    assert len(selected) == 12
    assert len({f["target"]["cluster_id"] for f in selected}) == 4
    assert {f["kind"] for f in selected} == {
        "capacity_review",
        "resident_memory",
        "schedule_candidate",
    }
    assert audit["eligible_count"] == 800 and audit["omitted_count"] == 788
    # Seven UTC days span eight KST dates; each valid daily window survives.
    assert len({f["period"]["start"] for f in candidates(t)}) == 8
    assert t == before


@pytest.mark.parametrize(
    "activity,pending,memory,expected",
    [
        (80, 1, 1, "capacity_review"),
        (79.99, 1, 1, "queue_review"),
        (4.99, 0, 79.99, "schedule_candidate"),
        (4.99, 0, 80, "resident_memory"),
        (5, 0, 1, None),
    ],
)
def test_review_criteria_boundaries_are_not_left_to_the_model(
    activity, pending, memory, expected
):
    facts = candidates(topic(activity=activity, pending=pending, memory=memory))
    assert [f["kind"] for f in facts] == ([expected] if expected else [])


async def test_compact_max_candidate_input_keeps_room_for_actual_model_output():
    t = topic(pending=2)
    t["rows"], t["workloads"], t["metrics"] = [], [], []
    for i in range(100):
        item = topic(pending=i + 1)
        for key in ("rows", "workloads"):
            item[key][0].update(
                cluster_id=f"cpc-{i % 4 + 1}", namespace=f"namespace-{i:03}-" + "x" * 45
            )
            t[key].extend(item[key])
    r = dict(topics=[t], time_range={}, quality={}, limitations=[])
    llm = AsyncMock(configured=True)
    llm.complete.return_value = None
    await interpret_report(r, llm)
    system, wire = llm.complete.call_args.args
    budget = LLM(Settings(kind="report"), 0, 32768, lambda state: None).request_budget(
        system, wire, "synthesis"
    )
    assert budget["output_token_cap"] >= 8192
    assert len(wire["topics"][0]["findings"]) == 4
    assert all(
        "source_hours" not in f and "conditions" not in f and "observation" not in f
        for f in wire["topics"][0]["findings"]
    )
    assert wire["topics"][0]["selection"]["omitted_count"] == 96
    examples = wire["response_shape"]["sections"][0]["advice"]
    assert [item["fact_id"] for item in examples] == [
        f["fact_id"] for f in wire["topics"][0]["findings"]
    ]
    for example, fact in zip(examples, wire["topics"][0]["findings"], strict=True):
        assert example["summary"] == ""
        assert "summary_start" not in fact
        assert {"target", "period"} <= fact["observed_values"].keys()
        assert "option" not in fact["decision"]
    assert "정상 항목은 바꾸지 말고" in system
    assert {
        f["observed_values"]["target"].split(" / ")[0]
        for f in wire["topics"][0]["findings"]
    } == {"cpc-1", "cpc-2", "cpc-3", "cpc-4"}


@pytest.mark.parametrize("token,unit", [("completed", "건"), ("elapsed", "초")])
def test_summary_normalizes_matching_repeated_units_from_verified_tokens(token, unit):
    fact = next(
        f for f in candidates(completed_topic()) if f["kind"] == "batch_progress"
    )
    reply = batch_section(fact)
    reply["advice"][0]["summary"] = reply["advice"][0]["summary"].replace(
        "{{" + token + "}}", "{{" + token + "}}" + unit
    )
    summary = validate_advice(reply, {"findings": [fact]})["advice"][0]["summary"]
    assert summary.count(unit + unit) == 0


def test_summary_still_rejects_wrong_or_ambiguous_token_units():
    fact = next(
        f for f in candidates(completed_topic()) if f["kind"] == "batch_progress"
    )
    for token, unit in (("completed", "개"), ("pending_change", "개")):
        reply = batch_section(fact)
        reply["advice"][0]["summary"] = reply["advice"][0]["summary"].replace(
            "{{" + token + "}}", "{{" + token + "}}" + unit
        )
        with pytest.raises(ValueError, match="duplicate_summary_unit"):
            validate_advice(reply, {"findings": [fact]})


def test_device_memory_observation_cannot_recommend_allocation_optimization():
    fact = next(
        f
        for f in candidates(topic(activity=1, memory=98))
        if f["kind"] == "resident_memory"
    )
    reply = section([fact])
    reply["advice"][0]["summary"] += " 메모리 할당 최적화를 검토하세요."
    with pytest.raises(ValueError, match="unsupported_capacity_recommendation"):
        validate_advice(reply, {"findings": [fact]})


def test_job_reference_may_precede_its_elapsed_label_in_actual_model_prose():
    fact = next(
        f for f in candidates(completed_topic()) if f["kind"] == "batch_progress"
    )
    reply = batch_section(fact)
    reply["advice"][0]["summary"] = (
        "{{target}} · {{period}}: Job {{completed}}이 완료됐고 경과시간은 {{elapsed}}이며 최대 대기 Pod 수는 {{pending_change}}로 변했습니다. 스케줄러 대기 사유와 완료 Job의 작업 유형을 확인하세요."
    )
    assert (
        validate_advice(reply, {"findings": [fact]})["advice"][0]["summary_source"]
        == "llm"
    )


def test_elapsed_wording_can_use_natural_inflection_without_requiring_a_template():
    fact = next(
        f for f in candidates(completed_topic()) if f["kind"] == "batch_progress"
    )
    reply = {
        "advice": [
            {
                "fact_id": fact["fact_id"],
                "summary": "{{target}} · {{period}}: {{completed}} 작업이 완료되었고 {{elapsed}} 경과되었으며 {{pending_change}} 대기 변화가 있었습니다. 스케줄러 대기 사유와 작업 유형을 기록과 대조하세요.",
            }
        ]
    }
    assert (
        validate_advice(reply, {"findings": [fact]})["advice"][0]["summary_source"]
        == "llm"
    )
    reply["advice"][0]["summary"] += " 순수 실행시간입니다."
    with pytest.raises(ValueError):
        validate_advice(reply, {"findings": [fact]})


def test_partial_positive_pending_cannot_be_offered_as_a_quiet_work_window():
    t = topic(activity=1, pending=2, samples=20)
    assert {f["kind"] for f in candidates(t)} == {"queue_review"}
    t["workloads"][0]["hours"][0]["pending_peak"] = 0
    t["workloads"][0]["hours"][1]["pending_peak"] = 0
    quiet = next(f for f in candidates(t) if f["kind"] == "schedule_candidate")
    assert quiet["period"]["end"] == "2026-10-14T02:00:00Z"


@pytest.mark.parametrize(
    "old,new,code",
    [
        ("Job 경과시간", "경과시간", "batch_job_elapsed_required"),
        ("입니다.", "이며 순수 실행입니다.", "batch_elapsed_is_not_execution_time"),
        ("입니다.", "이며 실행 시간입니다.", "batch_elapsed_is_not_execution_time"),
        (
            "입니다.",
            "이며 모든 작업이 완료됐습니다.",
            "batch_samples_do_not_prove_throughput_or_queue_resolution",
        ),
        (
            "입니다.",
            "이며 처리량이 개선됐습니다.",
            "batch_samples_do_not_prove_throughput_or_queue_resolution",
        ),
        (
            "입니다.",
            "이며 대기가 해소됐습니다.",
            "batch_samples_do_not_prove_throughput_or_queue_resolution",
        ),
    ],
)
def test_batch_rejections_keep_rules_and_identify_specific_failure(old, new, code):
    fact = next(
        f for f in candidates(completed_topic()) if f["kind"] == "batch_progress"
    )
    reply = batch_section(fact)
    before = deepcopy(fact)
    validate_advice(reply, {"findings": [fact]})
    reply["advice"][0]["summary"] = reply["advice"][0]["summary"].replace(old, new)
    with pytest.raises(ValueError, match="^" + code + ":") as error:
        validate_advice(reply, {"findings": [fact]})
    assert fact["fact_id"] + ".summary" in str(error.value)
    assert fact == before


@pytest.mark.parametrize("origin", ["schedule", "manual"])
@pytest.mark.parametrize(
    "claim,code",
    [
        ("Job 경과시간은 순수 실행 시간입니다.", "batch_elapsed_is_not_execution_time"),
        (
            "완료로 대기가 해소됐습니다.",
            "batch_samples_do_not_prove_throughput_or_queue_resolution",
        ),
    ],
)
async def test_batch_repair_targets_failure_in_both_origins(origin, claim, code):
    result = {
        "topics": [completed_topic()],
        "quality": {},
        "time_range": {},
        "report_origin": origin,
    }
    before = deepcopy(result)
    payload = payload_for(result)
    batch = next(
        f for f in payload["topics"][0]["findings"] if f["kind"] == "batch_progress"
    )
    valid = {"sections": [{"topic_id": "namespace_usage", **writer_section([batch])}]}
    invalid = deepcopy(valid)
    fact = next(a for a in invalid["sections"][0]["advice"])
    fact["summary"] += " " + claim
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [
        invalid,
        {"advice": [valid["sections"][0]["advice"][0]]},
    ]
    await interpret_report(result, llm)
    assert llm.complete.await_count == 2
    feedback = {
        "error": llm.complete.call_args_list[1].args[1]["summary_repair"][0][
            "validation_error"
        ],
        "instruction": llm.complete.call_args_list[1].args[1]["instruction"],
    }
    assert feedback["error"].startswith(code + ":")
    assert fact["fact_id"] + ".summary" in feedback["error"]
    assert "summary_repair" in llm.complete.call_args_list[1].args[1]
    assert "topics" not in llm.complete.call_args_list[1].args[1]
    assert "hourly_pair" not in feedback["instruction"]
    assert result["quality"]["report"]["failures"] == [{"attempt": 1, "reason": code}]
    assert result["quality"]["report"]["reason"] == "repaired"
    assert result["narrative_status"] == "complete"
    assert result["topics"] == before["topics"]
    assert result["report_origin"] == origin


@pytest.mark.parametrize("origin", ["schedule", "manual"])
@pytest.mark.parametrize(
    "problem", ["duplicate_target", "missing_check", "oversize_previous"]
)
async def test_summary_repair_preserves_previous_answer_within_input_limit(
    origin, problem
):
    result = dict(
        topics=[topic(pending=2)], quality={}, time_range={}, report_origin=origin
    )
    before = deepcopy(result)
    facts = payload_for(result)["topics"][0]["findings"]
    valid = {"sections": [writer_section(facts)]}
    invalid = deepcopy(valid)
    item = invalid["sections"][0]["advice"][0]
    if problem == "duplicate_target":
        item["summary"] = item["summary"] + " {{target}}"
        code = "namespace_summary_tokens_required"
    else:
        item["summary"] = ""
        code = "invalid_namespace_advice_text"
    if problem == "oversize_previous":
        invalid["unused"] = "x" * 32_000
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [
        invalid,
        {"advice": [valid["sections"][0]["advice"][0]]},
    ]
    await interpret_report(result, llm)
    first, second = [c.args[1] for c in llm.complete.call_args_list]
    assert first["value_meanings"] == second["value_meanings"] == VALUE_MEANINGS
    feedback = {
        "error": second["summary_repair"][0]["validation_error"],
        "instruction": second["instruction"],
    }
    assert feedback["error"].startswith(code + ":")
    assert feedback["error"]
    assert "hourly_pair" not in feedback["instruction"]
    assert second["summary_repair"][0]["previous_summary"] == item["summary"]
    assert second["summary_repair"][0]["fact_id"] == item["fact_id"]
    assert "previous_response" not in feedback
    # Includes the same candidate-specific reference example as the first request.
    assert len(json.dumps(second, ensure_ascii=False).encode()) < 4500
    assert first["topics"][0]["topic_id"] == "namespace_usage"
    assert result["narrative_status"] == "complete"
    assert result["topics"] == before["topics"]
    assert "previous_response" not in json.dumps(result)
    assert llm.complete.await_count == 2


def test_writing_focus_keeps_evidence_requirements_and_historical_semantics():
    fact = candidates(topic(activity=1, memory=98))[0]
    before = deepcopy(fact)
    context = summary_context(fact)
    assert "메모리를 어떤 작업이 차지하는지" in WRITING_FOCUS[fact["kind"]]
    assert "새 GPU 작업을 배치할 수 있을지" in context["writing_focus"]
    assert "독점 사용량이나 GPU 여유를 확정하지" in context["writing_focus"]
    assert set(context["required_summary_tokens"]) == {
        "{{target}}",
        "{{period}}",
        "{{activity}}",
        "{{memory}}",
    }
    assert fact == before
    assert "현재 대기" in SYSTEM and "시간대별 최대값" in SYSTEM
    assert "평균" in VALUE_MEANINGS["elapsed"]
    assert "처음 시간대 최대값" in VALUE_MEANINGS["pending_change"]
    assert "같은 순간" in VALUE_MEANINGS["activity"]


@pytest.mark.parametrize(
    "patch",
    [
        {"fact_id": "other", "summary": "wrong"},
        {"fact_id": "namespace-advice-0", "summary": None},
        {"fact_id": "namespace-advice-0", "summary": "wrong", "sections": []},
        {"fact_id": "namespace-advice-0", "summary": "대기 시간이 줄었습니다."},
    ],
)
async def test_summary_repair_cannot_change_scope_or_bypass_full_validation(patch):
    result = dict(topics=[topic(pending=2)], quality={}, time_range={})
    before = deepcopy(result)
    valid = {"sections": [writer_section(payload_for(result)["topics"][0]["findings"])]}
    invalid = deepcopy(valid)
    invalid["sections"][0]["advice"][0]["summary"] = (
        "{{target}} · {{period}}: 대기 Pod 수는 {{pending}}입니다."
    )
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [invalid, {"advice": [patch]}]
    await interpret_report(result, llm)
    assert result["narrative_status"] == "failed"
    assert result["topics"] == before["topics"]
    assert llm.complete.await_count == 2


async def test_summary_repair_preserves_other_valid_model_sentences():
    t = topic(pending=2)
    other = deepcopy(t)
    for k in ("rows", "workloads"):
        other[k][0]["cluster_id"] = "cpc-2"
        t[k].extend(other[k])
    result = dict(topics=[t], quality={}, time_range={})
    facts = payload_for(result)["topics"][0]["findings"]
    valid = {"sections": [writer_section(facts)]}
    invalid = deepcopy(valid)
    invalid["sections"][0]["advice"][0]["summary"] = invalid["sections"][0]["advice"][
        0
    ]["summary"].replace("이벤트", "{{target}} 이벤트")
    first = deepcopy(invalid)
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [
        invalid,
        {"advice": [valid["sections"][0]["advice"][0]]},
    ]
    await interpret_report(result, llm)
    assert result["narrative_status"] == "complete"
    expected = validate_reasoned_advice(
        valid["sections"][0], payload_for(result)["topics"][0]
    )
    present_advice([expected])
    assert result["narrative"][0]["advice"] == expected["advice"]
    assert invalid == first


async def test_all_invalid_sentences_repair_in_one_request_and_keep_valid_ones():
    t = topic(pending=2)
    other = deepcopy(t)
    for k in ("rows", "workloads"):
        other[k][0]["cluster_id"] = "cpc-2"
        t[k].extend(other[k])
    result = dict(topics=[t], quality={}, time_range={})
    valid = {"sections": [writer_section(payload_for(result)["topics"][0]["findings"])]}
    invalid = deepcopy(valid)
    for item in invalid["sections"][0]["advice"]:
        item["summary"] = item["summary"] + " {{target}}"
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [invalid, {"advice": valid["sections"][0]["advice"]}]
    await interpret_report(result, llm)
    assert len(llm.complete.call_args.args[1]["summary_repair"]) == 2
    assert result["narrative_status"] == "complete"
    assert llm.complete.await_count == 2


@pytest.mark.parametrize(
    "claim",
    [
        "GPU는 미사용입니다.",
        "GPU를 사용하지 않았습니다.",
        "GPU 사용이 없었습니다.",
        "활동이 없었습니다.",
    ],
)
def test_observed_zero_does_not_prove_nonuse(claim):
    t = topic(activity=0)
    before = deepcopy(t)
    facts = candidates(t)
    reply = section(facts)
    accepted = validate_advice(reply, dict(findings=facts))
    assert "0.00%" in accepted["advice"][0]["summary"]
    reply["advice"][0]["summary"] += " " + claim
    with pytest.raises(ValueError, match="observed_zero_is_not_proof_of_nonuse"):
        validate_advice(reply, dict(findings=facts))
    assert t == before


@pytest.mark.parametrize("origin", ["schedule", "manual"])
async def test_observed_zero_nonuse_claim_repairs_without_changing_metrics(origin):
    result = {
        "topics": [topic(activity=0)],
        "quality": {},
        "time_range": {},
        "report_origin": origin,
    }
    before = deepcopy(result)
    payload = payload_for(result)
    valid_section = writer_section(payload["topics"][0]["findings"])
    invalid = {"sections": [deepcopy(valid_section)]}
    invalid["sections"][0]["advice"][0]["summary"] += " GPU는 미사용입니다."
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [invalid, {"advice": valid_section["advice"]}]
    await interpret_report(result, llm)
    assert result["topics"][0]["metrics"] == before["topics"][0]["metrics"]
    assert result["quality"]["report"]["reason"] == "repaired"
    assert result["quality"]["report"]["failures"] == [
        {"attempt": 1, "reason": "observed_zero_is_not_proof_of_nonuse"}
    ]
    assert result["topics"] == before["topics"]
    assert "미사용" not in json.dumps(result["narrative"], ensure_ascii=False)


def test_separate_queue_window_survives_capacity_window_without_duplicate_hours():
    t = topic(activity=90, pending=2)
    t["rows"][0]["hours"][2]["activity_percent"] = 2
    before = deepcopy(t)
    facts = candidates(t)
    capacity = next(f for f in facts if f["kind"] == "capacity_review")
    queue = next(f for f in facts if f["kind"] == "queue_review")
    assert capacity["period"]["end"] == queue["period"]["start"]
    assert queue["source_hours"][0]["activity"] == [2]
    assert t == before


def test_all_qualified_windows_survive_before_bounded_selection():
    t = topic(activity=2, pending=0)
    hours = t["rows"][0]["hours"]
    hours[1]["sample_count"] = 0
    # Distinct positive queue windows remain even if one has a larger maximum.
    work = t["workloads"][0]["hours"]
    work[0]["pending_peak"], work[2]["pending_peak"] = 30, 3
    facts = candidates(t)
    queues = [f for f in facts if f["kind"] == "queue_review"]
    assert len(queues) == 2
    assert [f["source_hours"][0]["pending"] for f in queues] == [30, 3]
    reversed_topic = deepcopy(t)
    reversed_topic["rows"][0]["hours"].reverse()
    reversed_topic["workloads"][0]["hours"].reverse()
    assert candidates(reversed_topic) == facts


def test_resident_window_kept_and_separate_two_quiet_hours_recovered():
    t = topic(memory=20)
    t["rows"][0]["gpu_memory"]["hours"][0].update(
        used_gib_per_gpu=85, free_gib_per_gpu=15
    )
    facts = candidates(t)
    resident = next(f for f in facts if f["kind"] == "resident_memory")
    schedule = next(f for f in facts if f["kind"] == "schedule_candidate")
    assert len(resident["source_hours"]) == 3
    assert len(schedule["source_hours"]) == 2
    assert all(max(h["memory"]) < 80 for h in schedule["source_hours"])
    t["rows"][0]["hours"][2]["reasons"] = ["identity_uncertain"]
    assert all(f["kind"] != "schedule_candidate" for f in candidates(t))


@pytest.mark.parametrize(
    "peaks,samples,expected,has_token",
    [
        ([1, 0, 0], [240, 240, 240], "placement", True),
        ([1, None, 0], [20, 0, 240], "placement", False),
        ([0, 0, 0], [240, 240, 240], "preparation", True),
        ([0, 0, 0], [240, 20, 240], "unknown", True),
        ([None, None, None], [0, 0, 0], "unknown", False),
        ([3, 0, 0], [240, 240, 240], "unknown", False),
        ([True, 0, 0], [240, 240, 240], "unknown", False),
        ([0, 0, 0], [241, 240, 240], "unknown", False),
    ],
)
def test_unscheduled_context_is_aligned_and_missing_never_becomes_zero(
    peaks, samples, expected, has_token
):
    t = topic(activity=2, pending=2)
    for h, peak, count in zip(t["workloads"][0]["hours"], peaks, samples):
        h.update(unscheduled_peak=peak, unscheduled_samples=count)
    before = deepcopy(t)
    fact = candidates(t)[0]
    context = summary_context(fact)
    assert context["queue_context"]["check_first"] == expected
    assert ("{{unscheduled}}" in context["summary_tokens"]) == has_token
    assert "{{unscheduled}}" not in context["required_summary_tokens"]
    assert t == before
    # Existing output without the new optional reference must remain valid.
    assert validate_advice(section([fact]), {"findings": [fact]})["advice"]


def test_preparation_context_does_not_change_capacity_qualification_or_guards():
    t = topic(activity=90, pending=2)
    for h in t["workloads"][0]["hours"]:
        h.update(unscheduled_peak=0, unscheduled_samples=240)
    fact = candidates(t)[0]
    assert fact["kind"] == "capacity_review"
    assert summary_context(fact)["queue_context"]["check_first"] == "preparation"
    assert validate_advice(section([fact]), {"findings": [fact]})["advice"]


def test_preparation_event_check_uses_optional_evidence_with_existing_validator():
    t = topic(activity=2, pending=2)
    for h in t["workloads"][0]["hours"]:
        h.update(unscheduled_peak=0, unscheduled_samples=240)
    fact = candidates(t)[0]
    reply = {
        "advice": [
            {
                "fact_id": fact["fact_id"],
                "summary": "{{target}} · {{period}}: 활동률 {{activity}}, 최대 대기 {{pending}}, 최대 미배치 {{unscheduled}}가 관측됐습니다. 준비 단계 이벤트와 초기화 기록을 먼저 대조하세요.",
            }
        ]
    }
    out = validate_advice(reply, {"findings": [fact]})
    assert "최대 미배치 0개" in out["advice"][0]["summary"]
    assert out["advice"][0]["source_hours"] == fact["source_hours"]
    duplicate = deepcopy(reply)
    duplicate["advice"][0]["summary"] = duplicate["advice"][0]["summary"].replace(
        "{{unscheduled}}", "{{unscheduled}}개"
    )
    with pytest.raises(ValueError, match="duplicate_summary_unit"):
        validate_advice(duplicate, {"findings": [fact]})
    reply["advice"][0]["summary"] += " GPU 부족이 원인입니다."
    with pytest.raises(ValueError, match="unsupported_namespace_advice_claim"):
        validate_advice(reply, {"findings": [fact]})


def test_extra_queue_windows_do_not_crowd_out_other_target_questions():
    t = topic(pending=7)
    base = candidates(t)[0]
    facts = []
    for i in range(16):
        f = deepcopy(base)
        f["fact_id"] = f"queue-{i}"
        f["period"]["start"] = f"2026-10-{i + 1:02}T00:00:00Z"
        f["period"]["end"] = f"2026-10-{i + 1:02}T03:00:00Z"
        facts.append(f)
    other = deepcopy(base)
    other["fact_id"] = "other-namespace"
    other["target"]["namespace"] = "other"
    other["selection_basis"]["pending_peak"] = 1
    facts.append(other)
    selected, audit = select_candidates(facts)
    assert len(selected) == 12 and other in selected
    assert audit["omitted_count"] == 5
    assert select_candidates(list(reversed(facts))) == (selected, audit)


@pytest.mark.parametrize("origin", ["schedule", "manual"])
async def test_unscheduled_context_reaches_initial_repair_and_stored_narrative(origin):
    t = topic(pending=2)
    for h in t["workloads"][0]["hours"]:
        h.update(unscheduled_peak=0, unscheduled_samples=240)
    result = dict(topics=[t], quality={}, time_range={}, report_origin=origin)
    before = deepcopy(result)
    facts = payload_for(result)["topics"][0]["findings"]
    valid = writer_section(facts)
    valid["advice"][0]["summary"] = (
        "대기 Pod가 관측됐지만 노드 미배정은 관측되지 않았습니다."
    )
    invalid = deepcopy(valid)
    invalid["advice"][0]["summary"] = "{{target}} " + invalid["advice"][0]["summary"]
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [{"sections": [invalid]}, {"advice": valid["advice"]}]
    await interpret_report(result, llm)
    first, repair = [call.args[1] for call in llm.complete.call_args_list]
    assert (
        first["topics"][0]["findings"][0]["queue_context"]
        == repair["summary_repair"][0]["queue_context"]
        == {"check_first": "preparation", "unscheduled_complete": True}
    )
    assert (
        first["topics"][0]["findings"][0]["observed_values"]
        == repair["summary_repair"][0]["observed_values"]
    )
    assert result["quality"]["report"]["reason"] == "repaired"
    assert result["topics"] == before["topics"] and result["report_origin"] == origin
    narrative = next(
        n for n in result["narrative"] if n["topic_id"] == "namespace_usage"
    )
    assert narrative["advice"][0]["source_hours"][0]["unscheduled"] == 0
    assert "미배치 0개" in narrative["advice"][0]["summary"]
    assert narrative["advice"][0]["evidence_refs"] == facts[0]["evidence_refs"]


@pytest.mark.parametrize("unscheduled", [0, 2, None])
def test_summary_start_preserves_units_and_distinct_equal_value_references(unscheduled):
    t = topic(activity=2, pending=2)
    for h in t["workloads"][0]["hours"]:
        h.update(unscheduled_peak=unscheduled, unscheduled_samples=240)
    fact = candidates(t)[0]
    before = deepcopy(fact)
    start = summary_context(fact)["summary_start"]
    assert "{{pending}}" in start
    assert ("{{unscheduled}}" in start) == (unscheduled is not None)
    reply = {
        "advice": [
            {
                "fact_id": fact["fact_id"],
                "summary": start + " 준비 단계 이벤트와 초기화 기록을 먼저 대조하세요.",
            }
        ]
    }
    validated = validate_advice(reply, {"findings": [fact]})["advice"][0]
    assert "최대 대기 2개" in validated["summary"]
    if unscheduled is not None:
        assert f"최대 미배치 {unscheduled}개" in validated["summary"]
    assert fact == before


@pytest.mark.parametrize(
    "unscheduled,check",
    [
        (
            0,
            "미배치가 관측되지 않았으므로 노드 배정 이후 준비 단계 이벤트와 이미지·초기화 기록부터 대조하세요.",
        ),
        (
            2,
            "GPU 부족 여부를 판단하려면 관측된 미배치 Pod의 스케줄러 이벤트를 확인하세요.",
        ),
        (None, "배치·준비 단계 이벤트를 함께 대조해 대기 상태를 확인하세요."),
    ],
)
def test_prompt_observation_and_branch_check_pass_existing_guards(unscheduled, check):
    t = topic(pending=2)
    for h in t["workloads"][0]["hours"]:
        h.update(unscheduled_peak=unscheduled, unscheduled_samples=240)
    fact = candidates(t)[0]
    summary = summary_context(fact)["summary_start"] + " " + check
    assert validate_advice(
        {"advice": [{"fact_id": fact["fact_id"], "summary": summary}]},
        {"findings": [fact]},
    )["advice"]
    assert "시간대별 관측 최대 대기" not in SYSTEM
    assert "점검 목적·필수 확인 조건·운영 행동은 다시 작성하지 마세요" in SYSTEM
    assert "짧은 한 문장" in SYSTEM
    assert "같은 사실·판단을 반복" in SYSTEM
    assert "관측 현상" in SYSTEM
    if unscheduled == 2:
        focus = summary_context(fact)["writing_focus"]
        assert "GPU 요청이 충족되지 않았는지" in focus
        assert "GPU 부족을 단정" not in focus


def test_resident_focus_checks_gpu_memory_owner_before_placing_work():
    fact = next(
        f for f in candidates(topic(memory=98)) if f["kind"] == "resident_memory"
    )
    focus = summary_context(fact)["writing_focus"]
    assert "연결된 GPU의 메모리를 어떤 작업이 차지하는지" in focus
    assert "해당 Namespace의 독점 사용량" in focus
    choice = "새 GPU 작업의 배치 가능성을 판단하려면 연결된 GPU의 메모리 점유 주체와 상주 목적을 확인하세요."
    summary = choice + " " + summary_context(fact)["summary_start"]
    assert validate_advice(
        {"advice": [{"fact_id": fact["fact_id"], "summary": summary}]},
        {"findings": [fact]},
    )["advice"]


@pytest.mark.parametrize("missing", [False, True])
def test_contiguous_namespace_queue_does_not_split_on_gpu_identity(missing):
    t = topic(activity=2, pending=2)
    t["rows"][0]["hours"][1]["gpu_ids"] = ["other-gpu"]
    if missing:
        t["rows"][0]["hours"][1]["reasons"] = ["unobserved_hour"]
    before = deepcopy(t)
    queue = [f for f in candidates(t) if f["kind"] == "queue_review"]
    assert len(queue) == 1 and len(queue[0]["source_hours"]) == 3
    assert all(
        h["activity"] == [] and h["memory"] == [] for h in queue[0]["source_hours"]
    )
    assert "{{activity}}" not in summary_context(queue[0])["summary_tokens"]
    assert t == before


def test_namespace_queue_still_splits_at_gap_and_kst_midnight():
    t = topic(pending=2)
    for row in (
        t["rows"][0]["hours"],
        t["rows"][0]["gpu_memory"]["hours"],
        t["workloads"][0]["hours"],
    ):
        for h, hour in zip(row, (13, 14, 15)):
            h.update(
                start=f"2026-10-14T{hour}:00:00Z", end=f"2026-10-14T{hour + 1}:00:00Z"
            )
    assert [len(f["source_hours"]) for f in candidates(t)] == [2, 1]
    t["workloads"][0]["hours"][1]["pending_peak"] = 0
    assert [
        len(f["source_hours"]) for f in candidates(t) if f["kind"] == "queue_review"
    ] == [1, 1]


def test_selection_drops_folded_queue_and_optional_batch_but_keeps_cluster():
    t = completed_topic()
    t["workloads"][0]["hours"][0]["pending_samples"] = 240
    other = deepcopy(t)
    for row in other["rows"] + other["workloads"]:
        row["cluster_id"] = "cpc-2"
    t["rows"] += other["rows"]
    t["workloads"] += other["workloads"]
    facts = candidates(t)
    selected, audit = select_candidates(facts)
    batches = [f for f in selected if f["kind"] == "batch_progress"]
    assert (
        len(batches) == 1 and batches[0]["fact_id"] == audit["required_batch_fact_id"]
    )
    assert not any(
        f["kind"] == "queue_review" and f["target"] == batches[0]["target"]
        for f in selected
    )
    assert any(
        f["kind"] == "queue_review" and f["target"]["cluster_id"] == "cpc-2"
        for f in selected
    )
    assert select_candidates(list(reversed(facts))) == (selected, audit)
    only_batches = [f for f in facts if f["kind"] == "batch_progress"]
    assert len(select_candidates(only_batches)[0]) == 2


async def test_duplicate_reference_repair_preserves_check_and_equal_value_tokens():
    t = topic(pending=2)
    for h in t["workloads"][0]["hours"]:
        h.update(unscheduled_peak=2, unscheduled_samples=240)
    result = dict(topics=[t], quality={}, time_range={})
    fact = payload_for(result)["topics"][0]["findings"][0]
    start = summary_context(fact)["summary_start"]
    check = "대기 Pod가 미배치 상태로 관측됐으나 배치 제약의 원인은 미확인입니다."
    good = {"fact_id": fact["fact_id"], "summary": check}
    bad = {
        **good,
        "summary": "최대 미배치 {{unscheduled}}를 확인하고 " + check,
    }
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [
        {"sections": [{"topic_id": "namespace_usage", "advice": [bad]}]},
        {"advice": [good]},
    ]
    await interpret_report(result, llm)
    repair = llm.complete.call_args_list[1].args[1]
    assert "필수 확인 조건은 코드가 붙이므로" in repair["instruction"]
    assert repair["summary_repair"][0]["observed_values"]["pending"] == "2개"
    assert result["quality"]["report"]["reason"] == "repaired"
    narrative = result["narrative"][0]["advice"][0]["summary"]
    assert "최대 대기 2개" in narrative and "최대 미배치 2개" in narrative
    assert check in narrative
    # Literal equal values remain ambiguous under the unchanged validator.
    literal = (
        start.replace("{{pending}}", "2개").replace("{{unscheduled}}", "2개")
        + " "
        + check
    )
    with pytest.raises(ValueError, match="namespace_summary_tokens_required"):
        validate_advice(
            {"advice": [{**good, "summary": literal}]}, {"findings": [fact]}
        )


@pytest.mark.parametrize(
    "kind",
    ["capacity_review", "resident_memory", "schedule_candidate", "batch_progress"],
)
def test_summary_start_and_kind_check_keep_existing_validation(kind):
    t = {
        "capacity_review": lambda: topic(activity=90, pending=2),
        "resident_memory": lambda: topic(memory=95),
        "schedule_candidate": topic,
        "batch_progress": completed_topic,
    }[kind]()
    fact = next(f for f in candidates(t) if f["kind"] == kind)
    check = {
        "capacity_review": "현재 할당량과 보장량·스케줄러 사유를 확인한 뒤 확대 여부를 검토하세요.",
        "resident_memory": "낮은 연산 활동에도 메모리가 점유됐으므로 상주 서빙·캐시 목적부터 확인하세요.",
        "schedule_candidate": "예약과 대기·가용 GPU를 확인한 뒤 이 시간대 배치 작업 실행을 검토하세요.",
        "batch_progress": "완료 Job별 경과 차이에 배정 대기가 포함됐는지 스케줄러 이벤트와 작업 유형부터 대조하세요.",
    }[kind]
    start = summary_context(fact)["summary_start"]
    item = {"fact_id": fact["fact_id"], "summary": start + " " + check}
    assert validate_advice({"advice": [item]}, {"findings": [fact]})["advice"]
    with pytest.raises(ValueError, match="actionable_namespace_summary_required"):
        validate_advice({"advice": [{**item, "summary": start}]}, {"findings": [fact]})


@pytest.mark.parametrize(
    "kind,error",
    [
        ("schedule_candidate", "conditional_scheduling_review_required"),
        ("queue_review", "namespace_summary_tokens_required"),
    ],
)
async def test_code_scheduling_gate_and_model_unit_error_keep_existing_guards(
    kind, error
):
    from ops_agent.report_interpretation import validate_written_advice

    t = topic(pending=2 if kind == "queue_review" else 0)
    for h in t["workloads"][0]["hours"]:
        h.update(unscheduled_peak=0, unscheduled_samples=240)
    result = dict(topics=[t], quality={}, time_range={})
    fact = payload_for(result)["topics"][0]["findings"][0]
    good = writer_section([fact])["advice"][0]
    if kind == "schedule_candidate":
        bad = {
            "fact_id": fact["fact_id"],
            "summary": "작업 마감·예약·대기·가용 GPU를 확인하고 일부 작업의 시범 실행을 검토하세요.",
        }
        with pytest.raises(ValueError, match=error):
            validate_written_advice({"advice": [bad]}, {"findings": [fact]})
        llm = AsyncMock(configured=True)
        llm.complete.return_value = {
            "sections": [{"topic_id": "namespace_usage", "advice": [good]}]
        }
        await interpret_report(result, llm)
        assert llm.complete.call_count == 1
        assert "확인한 뒤" in result["narrative"][0]["advice"][0]["summary"]
    else:
        bad = {**good, "summary": good["summary"] + " {{unscheduled}}개"}
        llm = AsyncMock(configured=True)
        llm.complete.side_effect = [
            {"sections": [{"topic_id": "namespace_usage", "advice": [bad]}]},
            {"advice": [good]},
        ]
        await interpret_report(result, llm)
        assert llm.complete.call_count == 2
        repair = llm.complete.call_args.args[1]["summary_repair"][0]
        assert repair["validation_error"].startswith(error)
    assert result["narrative_status"] == "complete"


async def test_actual_unrecognized_check_verb_repairs_intent_not_invalid_wording():
    t = topic(pending=2)
    result = dict(topics=[t], quality={}, time_range={})
    fact = payload_for(result)["topics"][0]["findings"][0]
    bad = {"fact_id": fact["fact_id"], "summary": "Pod의 GPU 활동률이 낮았습니다."}
    good = writer_section([fact])["advice"][0]
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [
        {"sections": [{"topic_id": "namespace_usage", "advice": [bad]}]},
        {"advice": [good]},
    ]
    await interpret_report(result, llm)
    repair = llm.complete.call_args_list[1].args[1]
    assert "관측 현상과 판단 이유만 보완" in repair["instruction"]
    assert "코드가 붙이므로 다시 작성하지 마세요" in repair["instruction"]
    assert result["quality"]["report"]["reason"] == "repaired"
    assert (
        result["quality"]["report"]["failures"][0]["reason"]
        == "unsupported_workload_activity_attribution"
    )


@pytest.mark.parametrize(
    "kind",
    ["capacity_review", "resident_memory", "schedule_candidate", "batch_progress"],
)
def test_decision_first_summaries_preserve_original_evidence_and_guards(kind):
    t = {
        "capacity_review": lambda: topic(activity=90, pending=2),
        "resident_memory": lambda: topic(memory=95),
        "schedule_candidate": topic,
        "batch_progress": completed_topic,
    }[kind]()
    fact = next(f for f in candidates(t) if f["kind"] == kind)
    before = deepcopy(fact)
    choice = {
        "capacity_review": "현재 할당량·스케줄러 사유를 확인한 뒤 높은 활동과 대기를 근거로 할당 확대 여부를 검토하세요.",
        "resident_memory": "작업 수용 여력을 판단하기 전에 상주 작업의 메모리 유지 필요성을 확인하세요.",
        "schedule_candidate": "예약·대기·가용 GPU를 확인한 뒤 낮은 활동 구간의 배치 작업 시범 실행을 검토하세요.",
        "batch_progress": "완료 Job의 경과를 비교하기 전에 작업 유형과 스케줄러 기록을 대조하세요.",
    }[kind]
    item = {
        "fact_id": fact["fact_id"],
        "summary": choice + " " + summary_context(fact)["summary_start"],
    }
    accepted = validate_advice({"advice": [item]}, {"findings": [fact]})
    assert accepted["advice"][0]["summary"].startswith(choice)
    assert "선택:" not in summary_context(fact)["writing_focus"]
    assert "이유:" not in summary_context(fact)["writing_focus"]
    assert fact == before
    with pytest.raises(ValueError, match="namespace_summary_tokens_required"):
        validate_advice(
            {
                "advice": [
                    {**item, "summary": item["summary"].replace("{{period}}", "")}
                ]
            },
            {"findings": [fact]},
        )


@pytest.mark.parametrize("origin", ["schedule", "manual"])
async def test_decision_first_context_survives_repair_and_report_storage(origin):
    t = topic(pending=2)
    for h in t["workloads"][0]["hours"]:
        h.update(unscheduled_peak=0, unscheduled_samples=240)
    result = dict(topics=[t], quality={}, time_range={}, report_origin=origin)
    original = deepcopy(result)
    fact = payload_for(result)["topics"][0]["findings"][0]
    choice = "대기 Pod가 관측됐지만 노드 미배정은 관측되지 않았으며 기동 지연 여부는 미확인입니다."
    good = {
        "fact_id": fact["fact_id"],
        "summary": choice,
    }
    bad = {**good, "summary": "{{period}} " + good["summary"]}
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [
        {"sections": [{"topic_id": "namespace_usage", "advice": [bad]}]},
        {"advice": [good]},
    ]
    await interpret_report(result, llm)
    first, repair = [call.args[1] for call in llm.complete.call_args_list]
    assert "writing_focus" not in first
    assert "writing_focus" not in first["topics"][0]["findings"][0]
    assert "writing_focus" not in repair["summary_repair"][0]
    assert (
        first["topics"][0]["findings"][0]["writing_checks"]
        == repair["summary_repair"][0]["writing_checks"]
    )
    assert result["narrative"][0]["advice"][0]["summary"].startswith(choice)
    assert result["narrative_status"] == "complete"
    assert result["quality"]["report"]["reason"] == "repaired"
    assert result["topics"] == original["topics"] and result["report_origin"] == origin


def test_writing_selection_preserves_required_batch_clusters_and_distinct_choices():
    facts = []
    for make in [
        lambda: completed_topic(),
        lambda: topic(pending=2),
        lambda: topic(memory=95),
        topic,
    ]:
        facts.extend(candidates(make()))
    for i, f in enumerate(facts):
        f["fact_id"] = f"choice-{i}"
    extra = deepcopy(next(f for f in facts if f["kind"] == "queue_review"))
    extra["target"]["cluster_id"] = "cpc-2"
    extra["fact_id"] = "other-cluster"
    facts.append(extra)
    before = deepcopy(facts)
    selected, audit = writing_candidates(facts)
    assert {f["kind"] for f in selected} == {
        "batch_progress",
        "queue_review",
        "resident_memory",
        "schedule_candidate",
    }
    assert {f["target"]["cluster_id"] for f in selected} == {"cpc-1", "cpc-2"}
    assert audit["required_batch_fact_id"] in {f["fact_id"] for f in selected}
    assert len(selected) <= 5 and audit["offered_count"] == len(selected)
    assert audit["omitted_count"] == len(facts) - len(selected)
    assert sum(audit["omitted_by_kind"].values()) == audit["omitted_count"]
    assert writing_candidates(list(reversed(facts))) == (selected, audit)
    assert facts == before


def test_writing_selection_keeps_existing_large_cluster_behavior():
    facts = []
    for i in range(6):
        f = candidates(topic(pending=2))[0]
        f["target"]["cluster_id"] = f"cluster-{i}"
        f["fact_id"] = f"fact-{i}"
        facts.append(f)
    assert writing_candidates(facts) == select_candidates(facts)


@pytest.mark.parametrize("cluster_count", [1, 4, 5])
def test_writing_selection_never_spends_a_required_cluster_slot_on_extra_questions(
    cluster_count,
):
    facts = candidates(completed_topic())
    for i in range(1, cluster_count):
        fact = candidates(topic(pending=2))[0]
        fact["target"]["cluster_id"] = f"other-{i}"
        fact["fact_id"] = f"queue-{i}"
        facts.append(fact)
    for extra in [topic(memory=95), topic()]:
        for fact in candidates(extra):
            fact["fact_id"] = f"extra-{fact['kind']}"
            facts.append(fact)
    selected, audit = writing_candidates(facts)
    assert len(selected) <= 5
    assert {f["target"]["cluster_id"] for f in selected} == {
        f["target"]["cluster_id"] for f in facts
    }
    assert audit["required_batch_fact_id"] in {f["fact_id"] for f in selected}
    assert len({(f["target"]["cluster_id"], f["kind"]) for f in selected}) == len(
        selected
    )


async def test_queue_cause_rejection_repairs_only_invalid_item_without_rewriting_other_choices():
    t = topic(pending=2)
    for h in t["workloads"][0]["hours"]:
        h.update(unscheduled_peak=2, unscheduled_samples=240)
    result = dict(topics=[t], quality={}, time_range={})
    original = deepcopy(result)
    fact = payload_for(result)["topics"][0]["findings"][0]
    bad = {
        "fact_id": fact["fact_id"],
        "summary": "미배치 때문에 대기하는 것으로 보입니다.",
    }
    good = {
        **bad,
        "summary": "미배치가 관측됐지만 대기 원인은 미확인입니다.",
    }
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [
        {"sections": [{"topic_id": "namespace_usage", "advice": [bad]}]},
        {"advice": [good]},
    ]
    await interpret_report(result, llm)
    assert llm.complete.call_count == 2
    repair = llm.complete.call_args.args[1]
    assert "topics" not in repair and len(repair["summary_repair"]) == 1
    assert repair["summary_repair"][0]["validation_error"].startswith(
        "unsupported_queue_cause"
    )
    assert result["quality"]["report"]["reason"] == "repaired"
    assert result["topics"] == original["topics"]


def test_batch_writing_focus_identifies_observed_pending_pods_and_stage():
    fact = next(
        f for f in candidates(completed_topic()) if f["kind"] == "batch_progress"
    )
    original = deepcopy(fact)
    fact["pending_change"] = [8, 5]
    context = summary_context(fact)
    assert "마지막 시간대에도 대기 Pod" in context["writing_focus"]
    assert (
        "이 Namespace에서 관측된 대기 Pod의 상태와 이벤트" in context["writing_focus"]
    )
    assert "노드 배정 전인지 기동 준비 중인지" in context["writing_focus"]
    assert "다음 작업" not in context["writing_focus"]
    assert "소요시간" not in context["writing_focus"]
    fact["source_hours"][-1]["unscheduled"] = 5
    assert "노드가 배정되지 않은 대기 Pod" in summary_context(fact)["writing_focus"]
    assert "배치되지 않은 사유" in summary_context(fact)["writing_focus"]
    fact["source_hours"] = original["source_hours"]
    fact["pending_change"] = [8, 0]
    assert summary_context(fact)["writing_focus"] == WRITING_FOCUS["batch_progress"]
    fact.pop("pending_change")
    assert summary_context(fact)["writing_focus"] == WRITING_FOCUS["batch_progress"]
    assert fact["source_hours"] == original["source_hours"]


async def test_more_than_five_clusters_keeps_selection_guidance_instead_of_oversized_writing_plan():
    t = topic(pending=2)
    t["rows"], t["workloads"] = [], []
    for i in range(6):
        item = topic(pending=2)
        for key in ("rows", "workloads"):
            item[key][0]["cluster_id"] = f"cluster-{i}"
            t[key].extend(item[key])
    result = dict(topics=[t], quality={}, time_range={})
    llm = AsyncMock(configured=True)
    llm.complete.return_value = None
    await interpret_report(result, llm)
    wire = llm.complete.call_args.args[1]
    assert len(wire["topics"][0]["findings"]) > 5
    assert wire["response_shape"]["sections"][0]["advice"] == [
        {
            "fact_id": "선택한 후보의 fact_id",
            "summary": "수치·참조 없는 관측 현상과 판단 이유",
        }
    ]


async def test_namespace_writing_list_does_not_replace_incident_section_contract():
    from test_aggregate_report import concentration_report, concentration_records

    incident = concentration_report(concentration_records()[:1])["topics"][0]
    result = dict(topics=[topic(), incident], quality={}, time_range={})
    llm = AsyncMock(configured=True)
    llm.complete.return_value = None
    await interpret_report(result, llm)
    system, wire = llm.complete.call_args.args
    ns, inc = wire["response_shape"]["sections"]
    assert [a["fact_id"] for a in ns["advice"]] == [
        f["fact_id"] for f in wire["topics"][0]["findings"]
    ]
    from ops_agent.incident_findings import INCIDENT_RULES
    from ops_agent.report_interpretation import INCIDENT_EXAMPLE

    assert set(inc) == {"topic_id", "fact_ids", "observation", "meaning", "next_check"}
    assert {key: inc[key] for key in INCIDENT_EXAMPLE} == INCIDENT_EXAMPLE
    assert INCIDENT_RULES in system
    assert inc["observation"] == ""
    assert "fact_ids도 코드가 정하므로 응답 값은 쓰이지 않습니다" in system
    assert "다른 주제의 필드를 Namespace summary에 복사하지" in system
    assert "점검 목적·필수 확인 조건·운영 행동은 다시 작성하지 마세요" in system
    assert "수치와 참조는 코드가 붙입니다" in system
    assert "기존 fact_ids와 수치·대상·기간 참조 규칙" in system


def test_queue_preserves_full_span_and_offers_only_valid_contiguous_subwindows():
    t = topic(activity=50, pending=4, memory=20)
    t["rows"][0]["hours"][0]["reasons"] = ["identity_uncertain"]
    before = deepcopy(t)
    facts = candidates(t)
    queues = [f for f in facts if f["kind"] == "queue_review"]
    assert len(queues) == 2
    broad = next(f for f in queues if len(f["source_hours"]) == 3)
    joined = next(f for f in queues if len(f["source_hours"]) == 2)
    assert all(not h["activity"] and not h["memory"] for h in broad["source_hours"])
    assert all(
        h["activity"] == [50] and h["memory"] == [20] for h in joined["source_hours"]
    )
    assert joined["period"]["start"] == t["rows"][0]["hours"][1]["start"]
    selected, _ = writing_candidates(facts)
    assert selected == [joined]
    assert t == before
    # A different GPU in the second valid hour must not be joined.
    t["rows"][0]["hours"][2]["gpu_ids"] = ["another"]
    assert len(candidates(t)) == 1


def test_elapsed_float_seconds_keep_precision_without_integer_decimal_suffix():
    assert elapsed_range([10810.0, 21618.0]) == "3시간 10초~6시간 18초"
    assert elapsed_range([0.0]) == "0초"
    assert elapsed_range([60.25]) == "1분 0.25초"


def test_presentation_preserves_entire_accepted_prose_and_safe_boundary():
    fact = candidates(topic(memory=98))[0]
    context = summary_context(fact)
    summary = "다른 작업을 넣기 전에 상주 작업의 메모리 유지 필요성을 확인하세요. {{target}} · {{period}}: 활동률 {{activity}}, 장치 메모리 {{memory}}입니다."
    narrative = [
        validate_advice(
            {"advice": [{"fact_id": fact["fact_id"], "summary": summary}]},
            {"findings": [fact]},
        )
    ]
    before = deepcopy(narrative)
    present_advice(narrative)
    item = narrative[0]["advice"][0]
    parts = item.pop("summary_parts")
    assert parts["decision"] + " " + parts["evidence"] == item["summary"]
    assert narrative == before
    assert context["summary_tokens"]["{{target}}"] in parts["evidence"]
    item["summary"] = item["summary"].replace(
        ". " + parts["evidence"], "." + parts["evidence"]
    )
    present_advice(narrative)
    assert (
        item["summary_parts"]["decision"] + item["summary_parts"]["evidence"]
        == item["summary"]
    )
    item["summary"] = "대상부터 쓰는 과거 문장은 임의로 분리하지 않습니다."
    present_advice(narrative)
    assert "summary_parts" not in item


def test_choice_support_ranks_conditional_trial_before_generic_queue_check():
    trial = candidates(topic())[0]
    queue = candidates(topic(pending=100, samples=12))[0]
    queue["fact_id"] = "queue"
    queue["target"]["namespace"] = "queue"
    selected, _ = select_candidates([queue, trial])
    assert selected[0] == trial
    assert decision_context(trial)["scope"] == "conditional_option"
    assert decision_context(queue)["specific_evidence"] is False
    # Missing queue observations weaken the scheduling choice without removing its evidence.
    for h in trial["source_hours"]:
        h["pending_samples"] = 12
    trial["selection_basis"]["pending_complete"] = False
    assert decision_context(trial)["scope"] == "targeted_check"


def test_partial_positive_placement_evidence_can_narrow_a_complete_unknown_queue():
    unknown = candidates(topic(pending=3))[0]
    placed = deepcopy(unknown)
    placed["fact_id"] = "placement"
    placed["selection_basis"]["pending_complete"] = False
    placed["source_hours"][0].update(unscheduled=1, unscheduled_samples=12)
    before = deepcopy([unknown, placed])
    selected, _ = select_candidates([unknown, placed])
    assert selected[0] == placed
    assert decision_context(placed)["choice"] == "placement_review"
    assert [unknown, placed] == before


def test_cluster_diversity_does_not_replace_specific_evidence_with_generic_check():
    batch = next(
        f for f in candidates(completed_topic()) if f["kind"] == "batch_progress"
    )
    batch["source_hours"][-1].update(unscheduled=2, unscheduled_samples=240)
    batch["pending_change"] = [2, 2]
    batch["selection_basis"]["pending_complete"] = True
    queues = []
    for i, unscheduled in enumerate((2, None)):
        q = candidates(topic(pending=2))[0]
        q["fact_id"] = f"other-{i}"
        q["target"]["cluster_id"] = "cpc-2"
        for h in q["source_hours"]:
            h.update(unscheduled=unscheduled, unscheduled_samples=240)
        queues.append(q)
    selected, audit = writing_candidates([batch, *queues])
    assert queues[0] in selected and queues[1] not in selected
    assert audit["required_batch_fact_id"] == batch["fact_id"]
    assert {f["target"]["cluster_id"] for f in selected} == {"cpc-1", "cpc-2"}


def test_completion_only_is_not_an_optional_operating_change():
    batch = next(
        f for f in candidates(completed_topic()) if f["kind"] == "batch_progress"
    )
    assert decision_context(batch)["scope"] == "observation_only"
    assert "기록" in decision_context(batch)["needed"]
    selected, audit = writing_candidates([batch, candidates(topic())[0]])
    assert batch in selected  # Existing required-completion contract is preserved.
    assert next(d for d in audit["decisions"] if d["fact_id"] == batch["fact_id"])[
        "required_batch"
    ]


async def test_operating_choice_reaches_llm_and_stored_result_without_changing_topics():
    t = topic()
    original = deepcopy(t)
    result = dict(topics=[t], quality={}, time_range={})
    fact = payload_for(result)["topics"][0]["findings"][0]
    summary = "연결 GPU 활동률이 낮았고 후보 구간에 대기 Pod가 관측되지 않았습니다."
    llm = AsyncMock(configured=True)
    llm.complete.return_value = {
        "sections": [
            {
                "topic_id": "namespace_usage",
                "advice": [{"fact_id": fact["fact_id"], "summary": summary}],
            }
        ]
    }
    await interpret_report(result, llm)
    sent = llm.complete.call_args.args[1]["topics"][0]["findings"][0]["decision"]
    saved = result["narrative"][0]["advice"][0]["decision"]
    assert sent == {
        **{key: value for key, value in saved.items() if key != "option"},
        "reason": "연결 GPU 활동률이 낮았고 후보 구간에 대기 Pod가 관측되지 않았습니다.",
    }
    assert saved == decision_context(fact)
    assert result["topics"] == [original]
    assert result["narrative_status"] == "complete"


def test_required_completion_is_covered_without_forcing_it_to_the_first_bullet():
    batch = next(
        f for f in candidates(completed_topic()) if f["kind"] == "batch_progress"
    )
    trial = candidates(topic())[0]
    trial["fact_id"] = "trial"
    selected, audit = writing_candidates([batch, trial])
    assert selected[0] == trial
    assert batch in selected
    assert audit["required_batch_fact_id"] == batch["fact_id"]


@pytest.mark.parametrize("phase", ["placement", "preparation", "unknown"])
def test_completed_job_writing_example_remains_valid_with_each_pending_stage(phase):
    t = completed_topic()
    for hour in t["workloads"][0]["hours"]:
        hour.update(pending_peak=2, pending_samples=240)
        if phase != "unknown":
            hour.update(
                unscheduled_peak=2 if phase == "placement" else 0,
                unscheduled_samples=240,
            )
    before = deepcopy(t)
    fact = next(f for f in candidates(t) if f["kind"] == "batch_progress")
    item = {
        "fact_id": fact["fact_id"],
        "summary": decision_context(fact)["option"]
        + " "
        + summary_context(fact)["summary_start"],
    }
    assert "작업 유형" in item["summary"]
    assert validate_advice({"advice": [item]}, {"findings": [fact]})["advice"]
    assert t == before


def test_partial_queue_writing_example_starts_with_the_missing_evidence():
    fact = next(
        f for f in candidates(topic(samples=200)) if f["kind"] == "schedule_candidate"
    )
    context = decision_context(fact)
    assert context["scope"] == "targeted_check"
    assert "대기 상태는 미확인" in context["option"]
    assert "확인한 뒤" in context["option"]
    summary = context["option"] + " " + summary_context(fact)["summary_start"]
    assert validate_advice(
        {"advice": [{"fact_id": fact["fact_id"], "summary": summary}]},
        {"findings": [fact]},
    )["advice"]


@pytest.mark.parametrize(
    "prose",
    [
        "예약·대기·가용 GPU를 확인하고 일부 작업의 시범 실행을 검토하세요.",
        "예약·대기·가용 GPU를 확인한 뒤 일부 작업을 시범 실행하세요.",
    ],
)
async def test_repeated_scheduling_condition_failure_keeps_calculated_report(prose):
    result = dict(topics=[topic()], quality={}, time_range={})
    original = deepcopy(result["topics"])
    fact = payload_for(result)["topics"][0]["findings"][0]
    item = {
        "fact_id": fact["fact_id"],
        "summary": prose,
    }
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [
        {"sections": [{"topic_id": "namespace_usage", "advice": [item]}]},
        {"advice": [item]},
    ]
    await interpret_report(result, llm)
    assert llm.complete.call_count == 2
    assert result["topics"] == original
    assert result["narrative_status"] == "failed"
    diagnostic = result["quality"]["report"]
    assert diagnostic["method"] == "deterministic_fallback"
    assert diagnostic["failures"] == [
        {"attempt": n, "reason": "reason_only_namespace_summary_required"}
        for n in (1, 2)
    ]
    repair = llm.complete.call_args_list[1].args[1]["summary_repair"][0]
    assert repair["fact_id"] == fact["fact_id"]
    assert "조건은 코드가 붙" in repair["validation_error"]
    assert "관측 현상과 판단 이유만" in repair["validation_error"]
    assert "summary" not in diagnostic["failures"][0]


def test_related_observations_keep_target_period_and_choice_boundaries():
    fact = candidates(topic(activity=90, pending=2))[0]
    peer = candidates(topic(pending=2))[0]
    peer["period"] = {"start": "2026-10-15T00:00:00Z", "end": "2026-10-15T03:00:00Z"}
    peer["fact_id"] = "later-queue"
    other_cluster = deepcopy(peer)
    other_cluster["fact_id"] = "other-cluster"
    other_cluster["target"]["cluster_id"] = "cpc-2"
    other_namespace = deepcopy(peer)
    other_namespace["fact_id"] = "other-namespace"
    other_namespace["target"]["namespace"] = "another"
    facts = [fact, peer, other_cluster, other_namespace]
    before = deepcopy(facts)
    context = writing_context(fact, facts)
    related = context.pop("related_observations")
    assert context == writing_context(fact)
    assert [item["fact_id"] for item in related] == ["later-queue"]
    assert related[0]["period"] == peer["period"] != fact["period"]
    assert related[0]["decision"]["choice"] == "pending_stage_review"
    assert context["decision"]["choice"] == "allocation_review"
    assert "option" not in related[0]["decision"]
    assert "summary_tokens" not in related[0]
    assert facts == before
    assert writing_context(fact, reversed(facts)) == writing_context(fact, facts)


@pytest.mark.parametrize("missing", ["cluster_id", "namespace"])
def test_missing_target_does_not_link_related_observations(missing):
    fact = candidates(topic(pending=2))[0]
    peer = deepcopy(fact)
    peer["fact_id"] = "peer"
    fact["target"][missing] = ""
    assert "related_observations" not in writing_context(fact, [peer])


@pytest.mark.parametrize(
    "peak,samples,choice",
    [
        (2, 240, "placement_review"),
        (0, 240, "startup_review"),
        (0, 238, "pending_stage_review"),
    ],
)
def test_related_context_does_not_override_evidence_sensitive_queue_choice(
    peak, samples, choice
):
    current = topic(pending=2)
    for hour in current["workloads"][0]["hours"]:
        hour.update(unscheduled_peak=peak, unscheduled_samples=samples)
    fact = candidates(current)[0]
    peer = candidates(topic(activity=90, pending=2))[0]
    peer["fact_id"] = "capacity-peer"
    context = writing_context(fact, [fact, peer])
    assert context["decision"]["choice"] == choice
    assert (
        context["related_observations"][0]["decision"]["choice"] == "allocation_review"
    )
    expected = {k[2:-2]: v for k, v in summary_context(fact)["summary_tokens"].items()}
    if samples != 240 and peak == 0:
        assert context["observed_values"]["unscheduled"].startswith(
            expected.pop("unscheduled")
        )
        assert "미확인" in context["observed_values"]["unscheduled"]
    assert all(context["observed_values"][k] == v for k, v in expected.items())


@pytest.mark.parametrize("origin", ["schedule", "manual"])
async def test_related_evidence_survives_partial_repair_without_rewriting_valid_item(
    origin,
):
    combined = topic(activity=90, pending=2)
    combined["workloads"][0]["completed_jobs"] = completed_topic()["workloads"][0][
        "completed_jobs"
    ]
    result = dict(topics=[combined], quality={}, time_range={}, report_origin=origin)
    before = deepcopy(result)
    facts = payload_for(result)["topics"][0]["findings"]
    assert len(facts) == 2
    good = writer_section(facts)
    invalid = deepcopy(good)
    invalid["advice"][0]["summary"] += " {{period}}"
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [
        {"sections": [invalid]},
        {"advice": [good["advice"][0]]},
    ]
    await interpret_report(result, llm)
    first, repair = [call.args[1] for call in llm.complete.call_args_list]
    repaired = repair["summary_repair"][0]
    initial = next(
        f for f in first["topics"][0]["findings"] if f["fact_id"] == repaired["fact_id"]
    )
    assert repaired["related_observations"] == initial["related_observations"]
    assert len(repaired["related_observations"]) == 1
    assert result["quality"]["report"]["reason"] == "repaired"
    expected = validate_reasoned_advice(good, {"findings": facts})["advice"]
    assert [a["summary"] for a in result["narrative"][0]["advice"]] == [
        a["summary"] for a in expected
    ]
    assert result["topics"] == before["topics"]
    assert "related_observations" not in json.dumps(result)


@pytest.mark.parametrize(
    "kind",
    [
        "capacity_review",
        "schedule_candidate",
        "queue_review",
        "resident_memory",
        "batch_progress",
        "repeated_activity",
        "relative_activity",
    ],
)
def test_code_assembly_preserves_prose_and_exact_existing_validation(kind):
    inputs = [
        topic(activity=90, pending=2),
        topic(),
        topic(pending=2),
        topic(memory=95),
        completed_topic(),
    ]
    high = topic(activity=90, pending=2)
    high["rows"][0]["hours"][1]["activity_percent"] = 10
    inputs.append(high)
    from test_namespace_comparison_patterns import pattern_topic

    inputs.append(pattern_topic([80, 80, 20, 20]))
    fact = next(f for t in inputs for f in candidates(t) if f["kind"] == kind)
    source = prose_section([fact])
    before = deepcopy(source)
    topic_data = {"findings": [fact]}
    composed = advice_with_evidence(source, topic_data)
    expected = deepcopy(source)
    expected["advice"][0]["summary"] += " " + summary_context(fact)["summary_start"]
    assert composed == expected and source == before
    assert advice_with_evidence(source, topic_data) == composed
    result = validate_advice(composed, topic_data)
    assert result == validate_advice(expected, topic_data)
    present_advice([result])
    item = result["advice"][0]
    assert item["summary_parts"]["decision"] == source["advice"][0]["summary"]
    assert (
        item["summary"]
        == item["summary_parts"]["decision"] + " " + item["summary_parts"]["evidence"]
    )
    assert item["evidence_refs"] == fact["evidence_refs"]


@pytest.mark.parametrize(
    "bad",
    [
        "",
        " ",
        "확인하세요.",
        "대기 Pod는 9개입니다. 스케줄러 이벤트를 확인하세요.",
        "스케줄러 이벤트를 확인하세요. {{private_token}}",
        "스케줄러 이벤트를 확인하세요. {{pending}}",
        "스케줄러 이벤트를 확인하세요.\n기록을 대조하세요.",
        "스케줄러 이벤트를 확인하세요." * 40,
    ],
)
def test_code_assembly_does_not_hide_invalid_prose(bad):
    fact = candidates(topic(pending=2))[0]
    source = {"advice": [{"fact_id": fact["fact_id"], "summary": bad}]}
    before = deepcopy(source)
    with pytest.raises(ValueError):
        validate_advice(
            advice_with_evidence(source, {"findings": [fact]}), {"findings": [fact]}
        )
    assert source == before


@pytest.mark.parametrize(
    "item",
    [
        {"fact_id": "unknown", "summary": "스케줄러 이벤트를 확인하세요."},
        {"fact_id": [], "summary": "확인하세요."},
        {"fact_id": "namespace-advice-0", "summary": None},
        None,
    ],
)
def test_code_assembly_does_not_repair_invalid_identity_or_shape(item):
    fact = candidates(topic(pending=2))[0]
    source = {"advice": [item]}
    assert advice_with_evidence(source, {"findings": [fact]}) == source
    with pytest.raises((ValueError, TypeError)):
        validate_advice(
            advice_with_evidence(source, {"findings": [fact]}), {"findings": [fact]}
        )


def test_code_assembly_rejects_model_copying_evidence_instead_of_silently_stripping_it():
    fact = candidates(topic(pending=2))[0]
    source = section([fact])
    with pytest.raises(ValueError, match="namespace_summary_tokens_required"):
        validate_advice(
            advice_with_evidence(source, {"findings": [fact]}), {"findings": [fact]}
        )


@pytest.mark.parametrize("origin", ["schedule", "manual"])
async def test_prose_only_response_gets_exact_evidence_once_without_mutating_model_reply(
    origin,
):
    result = dict(
        topics=[topic(pending=2)], quality={}, time_range={}, report_origin=origin
    )
    original = deepcopy(result)
    facts = payload_for(result)["topics"][0]["findings"]
    reply = {"sections": [writer_section(facts)]}
    raw = deepcopy(reply)
    llm = AsyncMock(configured=True)
    llm.complete.return_value = reply
    await interpret_report(result, llm)
    assert reply == raw
    assert result["quality"]["report"]["reason"] == "complete"
    assert llm.complete.call_count == 1
    assert result["topics"] == original["topics"]
    sent = llm.complete.call_args.args[1]["topics"][0]["findings"][0]
    assert (
        not {"summary_start", "summary_tokens", "required_summary_tokens"} & sent.keys()
    )
    assert sent["observed_values"]["pending"] == "2개"
    assert (
        result["narrative"][0]["advice"][0]["summary_parts"]["decision"]
        == raw["sections"][0]["advice"][0]["summary"]
        + " "
        + summary_context(facts[0])["decision"]["action"]
    )


@pytest.mark.parametrize("origin", ["schedule", "manual"])
async def test_trial_reasons_and_separate_conditions_survive_partial_repair(origin):
    from test_namespace_comparison_patterns import pattern_topic
    from ops_agent.namespace_advice import writing_decision
    from ops_agent.report_interpretation import validate_reasoned_advice

    result = dict(
        topics=[pattern_topic([80, 80, 20, 20, 1, 1])],
        quality={},
        time_range={},
        report_origin=origin,
    )
    before = deepcopy(result["topics"])
    facts = payload_for(result)["topics"][0]["findings"]
    assert {f["kind"] for f in facts} == {"schedule_candidate", "relative_activity"}
    good = writer_section(facts)
    relative = next(f for f in facts if f["kind"] == "relative_activity")
    fixed = next(a for a in good["advice"] if a["fact_id"] == relative["fact_id"])
    invalid = deepcopy(good)
    next(a for a in invalid["advice"] if a["fact_id"] == relative["fact_id"])[
        "summary"
    ] += " {{target}}"
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [{"sections": [invalid]}, {"advice": [fixed]}]
    await interpret_report(result, llm)
    first, repair = [call.args[1] for call in llm.complete.call_args_list]
    patch = repair["summary_repair"]
    assert [a["fact_id"] for a in patch] == [relative["fact_id"]]
    sent = next(
        f for f in first["topics"][0]["findings"] if f["fact_id"] == relative["fact_id"]
    )
    assert patch[0]["related_observations"] == sent["related_observations"]
    assert "required_checks" not in sent and "required_prose_terms" not in patch[0]
    expected = validate_reasoned_advice(good, {"findings": facts})
    assert [a["summary"] for a in result["narrative"][0]["advice"]] == [
        a["summary"] for a in expected["advice"]
    ]
    assert result["topics"] == before
    for item in result["narrative"][0]["advice"]:
        fact = next(f for f in facts if f["fact_id"] == item["fact_id"])
        assert writing_decision(fact)["action"] in item["summary"]


def test_capacity_check_purpose_preserves_all_prerequisites_and_reference_guards():
    from ops_agent.report_interpretation import validate_written_advice

    fact = next(
        f
        for f in candidates(topic(activity=90, pending=2))
        if f["kind"] == "capacity_review"
    )
    before = deepcopy(fact)
    item = {
        "fact_id": fact["fact_id"],
        "summary": "스케줄러 사유에서 GPU 부족 여부를 확인하고, GPU 요청·실제 할당·보장량·가용 GPU·운영정책을 대조한 뒤 추가 할당을 검토하세요.",
    }
    assert validate_written_advice({"advice": [item]}, {"findings": [fact]})
    item["summary"] = item["summary"].replace("·보장량", "")
    with pytest.raises(ValueError, match="namespace_prerequisites_required"):
        validate_written_advice({"advice": [item]}, {"findings": [fact]})
    item["summary"] += " {{pending}}"
    with pytest.raises(ValueError, match="namespace_summary_tokens_required"):
        validate_written_advice({"advice": [item]}, {"findings": [fact]})
    assert fact == before


@pytest.mark.parametrize("samples", [240, 238])
def test_schedule_writing_reason_preserves_partial_observation_and_stored_decision(
    samples,
):
    fact = next(
        f
        for f in candidates(topic(samples=samples))
        if f["kind"] == "schedule_candidate"
    )
    before = deepcopy(fact)
    saved = decision_context(fact)
    writing = summary_context(fact)["decision"]
    assert {
        k: v for k, v in writing.items() if k not in {"option", "action", "reason"}
    } == {k: v for k, v in saved.items() if k not in {"option", "reason"}}
    if samples == 240:
        assert (
            writing["reason"]
            == "연결 GPU 활동률이 낮았고 후보 구간에 대기 Pod가 관측되지 않았습니다."
        )
    else:
        assert writing["reason"] == saved["reason"]
        assert (
            "미확인" in writing["reason"]
            and "관측되지 않았습니다" not in writing["reason"]
        )
    assert "마감" in writing["action"] and "시범 실행" in writing["action"]
    assert decision_context(fact) == saved and fact == before
