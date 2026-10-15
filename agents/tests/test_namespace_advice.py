"""Conditional Ops proposals must retain the existing numeric report unchanged."""

from copy import deepcopy
from unittest.mock import AsyncMock
import json
import pytest
from ops_agent.namespace_advice import (
    candidates,
    select_candidates,
    summary_context,
    validate_advice,
    SYSTEM,
)
from ops_agent.report_interpretation import interpret_report, payload_for
from agent_common.llm import LLM
from agent_common.settings import Settings


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


def section(facts):
    checks = {
        "capacity_review": "현재 할당량과 보장량·스케줄러 기록을 대조한 뒤 확대 여부를 검토하세요.",
        "schedule_candidate": "작업 마감·예약 일정과 대기 상태를 확인한 뒤 이 시간대 배치 작업 실행을 검토하세요.",
        "queue_review": "스케줄러 이벤트와 배치 제약을 먼저 대조하세요.",
        "resident_memory": "상주 서빙과 캐시 유지 여부를 확인하세요.",
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
                summary="{{target}} · {{period}}: "
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
    llm.complete.return_value = {"sections": [section(p["topics"][0]["findings"])]}
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
    assert values["{{completed}}"] == "2건"
    assert values["{{elapsed}}"] == "1200~3600초"
    assert values["{{pending_change}}"] == "2개 → 0개"
    assert len(fact["completed_jobs"]) == 2
    assert "일부" in fact["conditions"]
    assert t == before


def batch_section(fact):
    return {
        "advice": [
            {
                "fact_id": fact["fact_id"],
                "summary": "{{target}} · {{period}}: 시간대별 최대 대기 Pod 수는 {{pending_change}}이며 완료 표본은 {{completed}}, 대기·준비 포함 Job 경과시간은 {{elapsed}}입니다. 다음 배치의 제출 시점과 작업 규모를 기록과 대조하여 제출 간격을 검토하세요.",
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


def test_batch_summary_must_be_selected_and_duplicate_queue_checks_are_rejected():
    facts = candidates(completed_topic())
    queue = next(f for f in facts if f["kind"] == "queue_review")
    with pytest.raises(ValueError, match="batch_progress_summary_required"):
        validate_advice(section([queue]), {"findings": facts})


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
    assert audit["eligible_count"] == 100 and audit["omitted_count"] == 88
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
    assert len(wire["topics"][0]["findings"]) == 12
    assert all(
        "source_hours" not in f and "conditions" not in f and "observation" not in f
        for f in wire["topics"][0]["findings"]
    )
    assert wire["topics"][0]["selection"]["omitted_count"] == 88


@pytest.mark.parametrize(
    "suffix", ["{{completed}}건", "{{elapsed}}초", "{{pending}}개"]
)
def test_summary_cannot_duplicate_units_from_verified_tokens(suffix):
    fact = next(
        f for f in candidates(completed_topic()) if f["kind"] == "batch_progress"
    )
    reply = batch_section(fact)
    reply["advice"][0]["summary"] += suffix
    with pytest.raises(ValueError):
        validate_advice(reply, {"findings": [fact]})


def test_job_reference_may_precede_its_elapsed_label_in_actual_model_prose():
    fact = next(
        f for f in candidates(completed_topic()) if f["kind"] == "batch_progress"
    )
    reply = batch_section(fact)
    reply["advice"][0]["summary"] = (
        "{{target}} · {{period}}: Job {{completed}}가 완료됐고 경과시간은 {{elapsed}}이며 최대 대기 Pod 수는 {{pending_change}}로 변했습니다. 다음 배치의 제출 시점과 작업 규모를 기록과 대조하여 제출 간격을 검토하세요."
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
                "summary": "{{target}} · {{period}}: {{completed}} 작업이 완료되었고 {{elapsed}} 경과되었으며 {{pending_change}} 대기 변화가 있었습니다. 다음 배치 제출 시점을 기록과 대조하여 나눠 제출 검토하세요.",
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
