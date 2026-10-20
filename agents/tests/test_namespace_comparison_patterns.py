"""New candidate evidence is separate from existing metrics and advice gates."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock

import pytest
from test_namespace_advice import completed_topic, topic
from ops_agent.namespace_advice import candidates, summary_context, validate_advice
from ops_agent.report_interpretation import interpret_report, payload_for

NEW = {"repeated_activity", "relative_activity"}


def pattern_topic(values, pending=0):
    t = topic()
    for rows, key in [
        (t["rows"], "hours"),
        (t["workloads"], "hours"),
        ([t["rows"][0]["gpu_memory"]], "hours"),
    ]:
        prototype = rows[0][key][0]
        rows[0][key] = []
        for i, value in enumerate(values):
            at = datetime(2026, 10, 19, tzinfo=timezone.utc) + timedelta(hours=i)
            h = {
                **deepcopy(prototype),
                "start": at.isoformat().replace("+00:00", "Z"),
                "end": (at + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            }
            if "activity_percent" in h:
                h["activity_percent"] = value
            if "pending_peak" in h:
                h["pending_peak"] = pending
            rows[0][key].append(h)
    return t


def new(t, kind):
    return [f for f in candidates(t) if f["kind"] == kind]


def reply(fact):
    action = {
        "repeated_activity": "여러 시간의 고활동과 대기가 관측된 이 대상의 GPU 요청·할당과 스케줄러 이벤트를 대조하세요.",
        "relative_activity": "마감·예약·가용 GPU·메모리 요구를 확인한 뒤 조정 가능한 작업 일부를 후보 시간으로 옮겨 시범 실행할지 검토하세요.",
        "queue_review": "스케줄러 이벤트를 확인하세요.",
    }[fact["kind"]]
    return {
        "fact_id": fact["fact_id"],
        "summary": action + " " + summary_context(fact)["summary_start"],
    }


def test_repeated_hours_remain_separate_and_preserve_input():
    t = pattern_topic([85, 20, 90], 2)
    before = deepcopy(t)
    f = new(t, "repeated_activity")[0]
    assert len(f["observed_periods"]) == 2 and len(f["source_hours"]) == 2
    assert len(f["intervening_hours"]) == 1
    assert " / " in summary_context(f)["summary_tokens"]["{{period}}"]
    assert t == before
    t["rows"][0]["hours"][1]["reasons"] = ["duplicate_or_changed_gpu_identity"]
    f = new(t, "repeated_activity")[0]
    assert f["excluded_hours"][0]["reasons"] == ["duplicate_or_changed_gpu_identity"]
    assert len(f["source_hours"]) == 2


@pytest.mark.parametrize(
    "change", ["single", "consecutive", "partial", "zero", "identity", "model", "day"]
)
def test_repeated_rejects_weak_or_already_owned_patterns(change):
    t = pattern_topic([85, 20, 90], 2)
    if change == "single":
        t["rows"][0]["hours"][2]["activity_percent"] = 79.99
    if change == "consecutive":
        t["rows"][0]["hours"][1]["activity_percent"] = 85
    if change == "partial":
        t["workloads"][0]["hours"][2]["pending_samples"] = 239
    if change == "zero":
        t["workloads"][0]["hours"][2]["pending_peak"] = 0
    if change == "identity":
        t["rows"][0]["hours"][2]["gpu_ids"] = ["other"]
    if change == "model":
        r = deepcopy(t["rows"][0])
        r["gpu_model"] = "other"
        r["hours"][2]["activity_percent"] = 79
        t["rows"].append(r)
    if change == "day":
        for rows in [t["rows"], t["workloads"]]:
            rows[0]["hours"][2].update(
                start="2026-10-20T02:00:00Z", end="2026-10-20T03:00:00Z"
            )
    assert not new(t, "repeated_activity")


@pytest.mark.parametrize("ratio_value,eligible", [(40, True), (40.001, False)])
def test_relative_boundary_and_preserved_reference(ratio_value, eligible):
    t = pattern_topic([80, 80, ratio_value, 20])
    fs = new(t, "relative_activity")
    assert bool(fs) == eligible
    if fs:
        f = fs[0]
        assert f["period"] != f["reference_period"]
        assert f["reference_hours"][0]["activity"] == [80]
        assert f["criteria_revision"] == "ops-pattern-comparison-v7"
        assert "{{reference_period}}" in summary_context(f)["required_summary_tokens"]
        assert "{{memory}}" in summary_context(f)["required_summary_tokens"]


@pytest.mark.parametrize(
    "change",
    [
        "pending",
        "partial",
        "unknown",
        "memory",
        "missing_memory",
        "reference_pending",
        "reference_partial",
        "identity",
        "model",
        "day",
        "q3",
        "missing_activity",
    ],
)
def test_relative_rejects_missing_or_contrary_evidence(change):
    t = pattern_topic([80, 80, 20, 20])
    h = t["workloads"][0]["hours"]
    if change == "pending":
        h[3]["pending_peak"] = 1
    if change == "partial":
        h[3]["pending_samples"] = 239
    if change == "unknown":
        h[3]["pending_peak"] = None
    if change == "reference_pending":
        h[0]["pending_peak"] = 1
    if change == "reference_partial":
        h[0]["pending_samples"] = 239
    if change == "memory":
        t["rows"][0]["gpu_memory"]["hours"][3].update(
            used_gib_per_gpu=80, free_gib_per_gpu=20
        )
    if change == "missing_memory":
        t["rows"][0]["gpu_memory"]["hours"].pop()
    if change == "identity":
        t["rows"][0]["hours"][3]["gpu_ids"] = ["other"]
    if change == "model":
        r = deepcopy(t["rows"][0])
        r["gpu_model"] = "other"
        r["hours"][3]["activity_percent"] = 60
        t["rows"].append(r)
    if change == "day":
        for rows in [t["rows"], t["workloads"]]:
            rows[0]["hours"][3].update(
                start="2026-10-20T03:00:00Z", end="2026-10-20T04:00:00Z"
            )
    if change == "q3":
        for x in t["rows"][0]["hours"][2:]:
            x["activity_percent"] = 2
    if change == "missing_activity":
        t["rows"][0]["hours"][3]["sample_count"] = 0
    assert not new(t, "relative_activity")


def test_relative_overlap_is_deterministic_and_disjoint():
    t = pattern_topic([80, 80, 40, 20, 20])
    fs = new(t, "relative_activity")
    assert len(fs) == 1
    assert fs[0]["source_hours"][0]["activity"] == [20]
    shuffled = deepcopy(t)
    for r in shuffled["rows"]:
        r["hours"].reverse()
        r["gpu_memory"]["hours"].reverse()
    shuffled["workloads"][0]["hours"].reverse()
    assert new(shuffled, "relative_activity") == fs


@pytest.mark.parametrize(
    "kind,values,pending",
    [
        ("repeated_activity", [85, 20, 90], 2),
        ("relative_activity", [80, 80, 20, 20], 0),
    ],
)
@pytest.mark.parametrize("origin", ["manual", "schedule"])
async def test_new_evidence_reaches_initial_repair_and_saved_narrative(
    kind, values, pending, origin
):
    t = pattern_topic(values, pending)
    result = dict(topics=[t], quality={}, time_range={}, report_origin=origin)
    original = deepcopy(result)
    facts = payload_for(result)["topics"][0]["findings"]
    valid = [reply(f) for f in facts]
    bad = deepcopy(valid)
    selected = next(i for i, f in enumerate(facts) if f["kind"] == kind)
    bad[selected]["summary"] = bad[selected]["summary"].replace("{{activity}}", "")
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [
        {"sections": [{"topic_id": "namespace_usage", "advice": bad}]},
        {"advice": [valid[selected]]},
    ]
    await interpret_report(result, llm)
    assert result["narrative_status"] == "complete"
    assert result["quality"]["report"]["reason"] == "repaired"
    first, repair = [call.args[1] for call in llm.complete.call_args_list]
    a = next(f for f in first["topics"][0]["findings"] if f["kind"] == kind)
    assert a["pattern_evidence"] == repair["summary_repair"][0]["pattern_evidence"]
    saved = next(f for f in result["narrative"][0]["advice"] if f["kind"] == kind)
    assert saved["observed_periods"] == facts[selected]["observed_periods"]
    assert saved["source_hours"] == facts[selected]["source_hours"]
    if kind == "relative_activity":
        assert saved["reference_hours"] == facts[selected]["reference_hours"]
    assert saved["summary_parts"]["evidence"] in saved["summary"]
    assert json.loads(json.dumps(result))["narrative"] == result["narrative"]
    assert result["topics"] == original["topics"] and result["report_origin"] == origin


@pytest.mark.parametrize(
    "kind,phrase,code",
    [
        ("repeated_activity", "연속 포화이므로 점검하세요.", "separate_observations"),
        ("repeated_activity", "할당 확대를 검토하세요.", "unsupported_capacity"),
        ("relative_activity", "성능 개선을 검토하세요.", "conditional_relative"),
        ("relative_activity", "매일 실행하세요.", "unsupported_recurring"),
    ],
)
def test_new_candidates_cannot_evade_existing_or_new_claim_checks(kind, phrase, code):
    t = (
        pattern_topic([85, 20, 90], 2)
        if kind == "repeated_activity"
        else pattern_topic([80, 80, 20, 20])
    )
    f = new(t, kind)[0]
    v = reply(f)
    v["summary"] = phrase + v["summary"]
    with pytest.raises(ValueError, match=code):
        validate_advice({"advice": [v]}, {"findings": [f]})


def test_absent_middle_hour_is_stored_as_unknown_not_zero():
    t = pattern_topic([85, 20, 90], 2)
    removed = t["rows"][0]["hours"].pop(1)
    f = new(t, "repeated_activity")[0]
    assert f["excluded_hours"] == [
        {
            "start": removed["start"],
            "end": removed["end"],
            "reasons": ["incomplete_activity_hour"],
        }
    ]
    assert len(f["observed_periods"]) == 2


@pytest.mark.parametrize(
    "token", ["reference_period", "reference_activity", "memory", "pending"]
)
def test_relative_comparison_cannot_drop_either_side_or_safety_evidence(token):
    f = new(pattern_topic([80, 80, 20, 20]), "relative_activity")[0]
    v = reply(f)
    v["summary"] = v["summary"].replace("{{" + token + "}}", "")
    with pytest.raises(ValueError, match="namespace_summary_tokens_required"):
        validate_advice({"advice": [v]}, {"findings": [f]})


@pytest.mark.parametrize(
    "kind,values,pending,choice",
    [
        (
            "repeated_activity",
            [85, 20, 90],
            2,
            "GPU 활동률이 높은 여러 시간에 실행을 기다리는 Pod도 관측돼, 요청한 GPU와 실제 배정받은 GPU를 스케줄러 이벤트와 대조하세요.",
        ),
        (
            "relative_activity",
            [80, 80, 20, 20],
            0,
            "작업 마감·예약·가용 GPU·메모리 요구를 확인한 뒤 같은 Namespace에서 시간 조정이 가능한 작업 일부를 후보 시간대에 시범 실행할지 검토하세요.",
        ),
    ],
)
def test_plain_language_choices_keep_existing_evidence_and_claim_checks(
    kind, values, pending, choice
):
    fact = new(pattern_topic(values, pending), kind)[0]
    item = reply(fact)
    item["summary"] = choice + " " + summary_context(fact)["summary_start"]
    saved = validate_advice({"advice": [item]}, {"findings": [fact]})["advice"][0]
    assert saved["summary"].startswith(choice)
    assert saved["source_hours"] == fact["source_hours"]
    if kind == "relative_activity":
        item["summary"] = item["summary"].replace(
            "메모리 요구를 확인한 뒤", "메모리 요구와"
        )
        with pytest.raises(
            ValueError, match="conditional_relative_window_trial_required"
        ):
            validate_advice({"advice": [item]}, {"findings": [fact]})


@pytest.mark.parametrize(
    "source",
    [
        lambda: pattern_topic([85, 20, 90], 2),
        lambda: pattern_topic([80, 80, 20, 20]),
        lambda: topic(activity=90, pending=2),
        lambda: topic(activity=1, memory=98),
        lambda: topic(activity=1),
        lambda: topic(pending=2),
        completed_topic,
    ],
)
def test_reason_bearing_response_examples_pass_unchanged_guards(source):
    for fact in candidates(source()):
        context = summary_context(fact)
        first = context["decision"]["option"]
        item = {
            "fact_id": fact["fact_id"],
            "summary": first + " " + context["summary_start"],
        }
        result = validate_advice({"advice": [item]}, {"findings": [fact]})
        assert result["advice"][0]["summary"].startswith(first)
        assert first.endswith("세요.")
        assert not any(word in first for word in ("양수", "고활동", "기동", "있었음"))
