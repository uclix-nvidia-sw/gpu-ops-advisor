"""Editorial contract: immutable calculations, grounded tokens and honest fallback."""

from copy import deepcopy
from unittest.mock import AsyncMock
import asyncio
import pytest
from agent_common.llm import RemoteUncertain
from ops_agent.report_interpretation import (
    interpret_report,
    payload_for,
    reference_feedback,
    validate_sections,
)


INCIDENT_LIMIT = "저장 알림 기록이며 시험 알림이 섞일 수 있고 원인·같은 GPU 반복·복구는 확정하지 않습니다."


@pytest.fixture
def result():
    def topic(name, value, unit):
        return {
            "topic_id": name,
            "status": "ready",
            "missing_inputs": [],
            **({"summary": {"count": value}} if name == "incident_summary" else {}),
            "metrics": [
                {
                    "id": name + ".value",
                    "value": value,
                    "unit": unit,
                    "period": {},
                    "target": {},
                    "quality": {},
                }
            ],
            "findings": [
                {
                    "id": name + "-fact",
                    "text": "계산된 자료입니다.",
                    "target": {"cluster": "cpc-1"},
                    "value_refs": [name + ".value"],
                    "evidence_refs": [name + "-evidence"],
                }
            ],
        }

    incident = topic("incident_summary", 1, "events")
    incident["metrics"][0].update(
        id="incident_summary.count.0",
        period={"start": "2026-10-12T15:00:00Z", "end": "2026-10-13T15:00:00Z"},
    )
    incident["metrics"].append(
        {
            **incident["metrics"][0],
            "id": "incident_summary.previous_count.1",
            "value": 0,
        }
    )
    incident["findings"][0].update(
        id="incident-period-summary", value_refs=[m["id"] for m in incident["metrics"]]
    )
    return {
        "topics": [topic("namespace_usage", 60, "percent"), incident],
        "time_range": {},
        "quality": {},
        "limitations": ["알림 상태는 보고서 작성 당시 기준입니다."],
    }


def reply_for(payload):
    sections = []
    for t in payload["topics"]:
        if t.get("advice_mode"):
            from test_namespace_advice import writer_section

            sections.append(writer_section(t["findings"]))
            continue
        if t["topic_id"] == "incident_summary":
            context = t.get("focus", {}).get("check_context")
            check = "노드 식별 정보를 확인하세요."
            if context:
                check = (
                    "공개된 RCA 결과와 점검 기록을 대조하세요."
                    if context["rca_count"]
                    else "RCA 결과 유무와 작업 생성 여부·상태를 확인하세요."
                )
                if context["firing"]:
                    check += " 작성 이후 해제 여부를 확인하세요."
                if context["other_alert_fact_ids"]:
                    check += " 같은 노드의 다른 알림과 선후 관계를 확인하세요."
            sections.append(
                {
                    "topic_id": "incident_summary",
                    "fact_ids": [],
                    "observation": "",
                    "meaning": "알림 종류와 노드 분포는 저장된 관측이며 같은 원인을 뜻하지 않습니다.",
                    "next_check": check,
                }
            )
            continue
        f = t["findings"][0]
        pair = f.get("hourly_pair", [])
        section = {
            "topic_id": t["topic_id"],
            "fact_ids": [f["fact_id"]],
            "observation": "관측 결과는 {{value:"
            + f["values"][0]["metric_id"]
            + "}}입니다.",
            "meaning": "확인된 범위의 관측이며 전체 상태를 뜻하지 않습니다.",
            "next_check": "작업 일정 또는 기존 조사 기록과 대조해 보세요.",
        }
        if pair:
            target = "{{target:" + f["fact_id"] + "}}"
            periods = ["{{period:" + i + "}}" for i in pair]
            values = ["{{value:" + i + "}}" for i in pair]
            section["observation"] = (
                f"{target}는 {periods[0]}의 {values[0]}에서 {periods[1]}의 {values[1]}로 바뀌었습니다."
            )
            section["next_check"] = (
                f"{target}의 {periods[1]}에 작업이 시작됐는지 실행 기록과 대조해 보세요."
            )
        if f.get("memory_refs"):
            used, free = f["memory_refs"]
            section["meaning"] = (
                "{{target:"
                + f["fact_id"]
                + "}}의 {{period:"
                + used
                + "}} GPU당 사용 메모리는 {{value:"
                + used
                + "}}, 여유 메모리는 {{value:"
                + free
                + "}}입니다. 활동률과 메모리 점유를 함께 확인하세요."
            )
        if f.get("related_workload_fact_id"):
            section["fact_ids"].append(f["related_workload_fact_id"])
            section["meaning"] += (
                " 대기 Pod 상태는 별도의 관측이며 같은 시각의 원인으로 단정할 수 없습니다."
            )
            section["next_check"] += " Pod 배치 기록을 대조하세요."
        sections.append(section)
    return {"sections": sections}


@pytest.mark.parametrize("partial", [False, True])
@pytest.mark.parametrize("kind", ["target", "value"])
async def test_reference_feedback_reaches_repair_without_changing_guards(
    result, partial, kind
):
    if partial:
        from test_namespace_advice import topic

        result["topics"][0] = topic(activity=90, pending=2)
    before = deepcopy(result["topics"])
    payload = payload_for(result)
    good = reply_for(payload)
    bad = deepcopy(good)
    section = next(s for s in bad["sections"] if s["topic_id"] == "incident_summary")
    code = f"invalid_{kind}_reference"
    if kind == "target":
        section["next_check"] = "{{target:incident-missing}}의 기존 기록을 대조하세요."
        allowed = "incident-period-summary"
    else:
        section["meaning"] = "{{value:incident_summary.missing}}의 저장 관측입니다."
        allowed = "incident_summary.count.0"
    llm = AsyncMock(configured=True)
    repaired = (
        {
            "sections": [
                s for s in good["sections"] if s["topic_id"] == "incident_summary"
            ]
        }
        if partial
        else good
    )
    llm.complete.side_effect = [bad, repaired]
    await interpret_report(result, llm)
    repair = llm.complete.call_args_list[1].args[1]
    feedback = (
        repair["section_repair"][0]["validation_error"]
        if partial
        else repair["validation_feedback"]["error"]
    )
    assert feedback.startswith(code + ":")
    assert allowed in feedback and "allowed_ids" in feedback
    assert "namespace_usage.value" not in feedback
    assert len(feedback.encode()) < 2048
    assert result["quality"]["report"]["failures"] == [
        {
            "attempt": 1,
            "reason": code,
            "topic_failures": [{"topic_id": "incident_summary", "reason": code}],
        }
    ]
    assert result["narrative_status"] == "complete"
    assert result["topics"] == before


def test_reference_feedback_bounds_identifiers_without_echoing_prose():
    text = reference_feedback(
        "invalid_target_reference",
        "PRIVATE_RESPONSE\n" + "x" * 10000,
        [f"incident-{i}-" + "x" * 100 for i in range(50)],
    )
    assert "PRIVATE_RESPONSE" not in text
    assert '"invalid_key": "[omitted]"' in text
    assert '"allowed_count": 50' in text and '"list_truncated": true' in text
    assert len(text.encode()) < 2048


async def test_both_topics_are_interpreted_without_changing_facts(result):
    before = deepcopy(result)
    llm = AsyncMock(configured=True)
    llm.complete.return_value = reply_for(payload_for(result))
    await interpret_report(result, llm)
    assert result["topics"] == before["topics"]
    assert result["time_range"] == before["time_range"]
    assert result["limitations"] == before["limitations"]
    assert result["quality"]["report"]["method"] == "llm_interpreted"
    assert len(result["narrative"]) == 2
    assert "60.00%" in result["narrative"][0]["observation"]
    assert "1건" in result["narrative"][1]["observation"]
    for section, topic in zip(result["narrative"], result["topics"]):
        assert section["evidence_refs"] == topic["findings"][0]["evidence_refs"]
        assert section["value_refs"] == topic["findings"][0]["value_refs"]
    assert "작성 당시" in result["narrative"][1]["text"]
    assert "독점 사용량" in result["narrative"][0]["text"]


@pytest.mark.parametrize(
    "problem",
    [
        "number",
        "unknown_fact",
        "other_topic",
        "unknown_value",
        "null",
        "duplicate",
        "missing_topic",
        "empty",
        "policy",
        "cause",
        "markup",
        "too_long",
        "english",
        "double_unit",
    ],
)
def test_untrusted_responses_rejected(result, problem):
    payload = payload_for(result)
    reply = reply_for(payload)
    s = reply["sections"][0]
    if problem == "number":
        s["observation"] = "활동률은 99%입니다."
    if problem == "unknown_fact":
        s["fact_ids"] = ["missing"]
    if problem == "other_topic":
        s["fact_ids"] = ["incident-period-summary"]
    if problem == "unknown_value":
        s["observation"] = "{{value:incident_summary.count.0}}"
    if problem == "null":
        payload["topics"][0]["findings"][0]["values"][0]["value"] = None
    if problem == "duplicate":
        s["fact_ids"] *= 2
    if problem == "missing_topic":
        reply["sections"].pop()
    if problem == "empty":
        s["meaning"] = ""
    if problem == "policy":
        s["next_check"] = "GPU를 회수하세요."
    if problem == "cause":
        s["meaning"] = "배포가 원인입니다."
    if problem == "markup":
        s["meaning"] = "<script>test</script>"
    if problem == "too_long":
        s["meaning"] = "글" * 451
    if problem == "english":
        s["meaning"] = "The period is incomplete."
    if problem == "double_unit":
        s["observation"] = "{{value:namespace_usage.value}}건입니다."
    with pytest.raises(ValueError):
        validate_sections(reply, payload, result)


async def test_one_repair_and_partial_limits(result):
    result["topics"][0]["status"] = "partial"
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [{"sections": []}, reply_for(payload_for(result))]
    await interpret_report(result, llm)
    assert llm.complete.await_count == 2
    assert result["quality"]["report"]["reason"] == "repaired"
    assert "일부 자료" in result["narrative"][0]["interpretation_limit"]


@pytest.mark.parametrize(
    "mode", ["unconfigured", "invalid", "unavailable", "empty", "oversized"]
)
async def test_fallback_preserves_result(result, mode):
    if mode == "empty":
        result["topics"][0]["findings"] = []
    if mode == "oversized":
        result["topics"][0]["findings"][0]["text"] = "글" * 12000
    before = deepcopy(result["topics"])
    llm = AsyncMock(configured=mode != "unconfigured")
    llm.complete.return_value = None if mode == "unavailable" else {}
    await interpret_report(result, llm)
    assert result["topics"] == before
    assert result["quality"]["report"]["method"] == "deterministic_fallback"
    assert result["narrative_status"] != "complete"
    assert llm.complete.await_count <= 2
    assert all("observation" not in n for n in result["narrative"])


@pytest.mark.parametrize(
    "error", [RemoteUncertain("unknown"), asyncio.CancelledError()]
)
async def test_uncertain_remote_or_cancellation_still_propagates(result, error):
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = error
    with pytest.raises(type(error)):
        await interpret_report(result, llm)


async def test_real_calculated_contract_and_csv_are_unchanged():
    from uuid import uuid4
    from test_aggregate_report import DATA, fixture
    from agent_common.artifacts import render
    from agent_common.contracts import validate_result
    from ops_agent.aggregate_report import build_result
    from ops_agent.report_contract import VERSION, previous_period

    context = {
        "data_cutoff_at": DATA["time_range"]["end"],
        "incidents": [],
        "previous_incidents": [],
    }
    evidence = fixture() + fixture(previous_period(DATA))
    evidence.append(
        {
            **deepcopy(evidence[0]),
            "id": str(uuid4()),
            "query_id": "report_incident_snapshot",
            "snapshot": context,
        }
    )
    result = build_result(
        {
            "job_id": str(uuid4()),
            "kind": "report",
            "input": DATA,
            "versions": {"criteria": VERSION},
        },
        context,
        evidence,
    )
    before = deepcopy(result)
    csv = render(result)["csv"]
    llm = AsyncMock(configured=True)
    llm.complete.return_value = reply_for(payload_for(result))
    await interpret_report(result, llm)
    validate_result(result, evidence)
    assert render(result)["csv"] == csv
    assert "눈에 띄는 변화" in render(result)["html"].decode()
    for key in set(before) - {"narrative", "narrative_status", "quality"}:
        assert result[key] == before[key], key


def test_exact_repeated_unit_and_scope_target_are_rendered_once(result):
    result["topics"][1]["findings"][0]["target"] = {}
    payload = payload_for(result)
    reply = reply_for(payload)
    reply["sections"][0]["observation"] = "{{value:namespace_usage.value}}%입니다."
    reply["sections"][1]["observation"] = (
        "{{target:incident-period-summary}}의 사건은 {{value:incident_summary.count.0}}건입니다."
    )
    sections = validate_sections(reply, payload, result)
    assert sections[0]["observation"] == "60.00%입니다."
    assert (
        sections[1]["observation"]
        == "선택한 보고서 범위 · 10/13 00:00~10/14 00:00 KST: 저장 사건 1건(이전 비교기간 0건)."
    )


@pytest.fixture
def hourly_result(result):
    t = result["topics"][0]
    target = {"cluster_id": "cpc-1", "namespace": "research", "model": "A100"}
    t["findings"][0]["target"] = target
    hours = []
    for i, value in enumerate((0, 75, 50)):
        period = {
            "start": f"2026-10-13T0{i}:00:00Z",
            "end": f"2026-10-13T0{i + 1}:00:00Z",
        }
        hours.append(
            {**period, "activity_percent": value, "gpu_ids": ["gpu-a"], "reasons": []}
        )
        t["metrics"].append(
            {
                "id": f"namespace_usage.hourly_activity.{i}",
                "target": target,
                "period": period,
                "value": value,
                "unit": "percent",
                "quality": {},
            }
        )
    t["rows"] = [
        {
            "cluster_id": "cpc-1",
            "namespace": "research",
            "gpu_model": "A100",
            "hours": hours,
            "comparison_status": "previous_not_observed",
        }
    ]
    return result


def test_existing_hourly_values_and_kst_periods_are_grounded(hourly_result):
    before = deepcopy(hourly_result)
    payload = payload_for(hourly_result)
    f = payload["topics"][0]["findings"][0]
    assert f["hourly_pair"] == [
        "namespace_usage.hourly_activity.0",
        "namespace_usage.hourly_activity.1",
    ]
    section = validate_sections(reply_for(payload), payload, hourly_result)[0]
    assert "10/13 09:00~10/13 10:00 KST" in section["observation"]
    assert "10/13 10:00~10/13 11:00 KST" in section["next_check"]
    assert "cpc-1 / research / A100" in section["next_check"]
    assert "75.00%" in section["observation"]
    assert set(f["hourly_pair"]) <= set(section["value_refs"])
    assert hourly_result == before


@pytest.mark.parametrize(
    "problem", ["gap", "null", "identity", "reason", "metric_mismatch", "unattributed"]
)
def test_unsafe_hour_pairs_are_not_offered(hourly_result, problem):
    t = hourly_result["topics"][0]
    t["rows"][0]["hours"] = t["rows"][0]["hours"][:2]
    h = t["rows"][0]["hours"][1]
    if problem == "gap":
        h["start"] = "2026-10-13T01:15:00Z"
    if problem == "null":
        h["activity_percent"] = None
    if problem == "identity":
        h["gpu_ids"] = ["gpu-b"]
    if problem == "reason":
        h["reasons"] = ["incomplete_hour_or_sampling_interval"]
    if problem == "metric_mismatch":
        h["activity_percent"] = 90
    if problem == "unattributed":
        t["findings"][0]["target"]["namespace"] = ""
    assert payload_for(hourly_result)["topics"][0]["findings"][0]["hourly_pair"] == []


@pytest.mark.parametrize(
    "problem", ["generic_check", "missing_time", "other_period", "missing_target"]
)
def test_hourly_interpretation_must_name_target_and_period(hourly_result, problem):
    payload = payload_for(hourly_result)
    reply = reply_for(payload)
    section = reply["sections"][0]
    if problem == "generic_check":
        section["next_check"] = "일정을 확인하세요."
    if problem == "missing_time":
        section["observation"] = "값이 변화했습니다."
    if problem == "other_period":
        section["observation"] += "{{period:namespace_usage.value}}"
    if problem == "missing_target":
        section["next_check"] = (
            "{{period:namespace_usage.hourly_activity.1}} 확인하세요."
        )
    with pytest.raises(ValueError):
        validate_sections(reply, payload, hourly_result)


def test_blocked_previous_comparison_cannot_supply_previous_values(hourly_result):
    t = hourly_result["topics"][0]
    t["metrics"].append(
        {
            **t["metrics"][0],
            "id": "namespace_usage.previous_activity_percent.99",
            "value": 60,
        }
    )
    t["findings"][0]["value_refs"].append(
        "namespace_usage.previous_activity_percent.99"
    )
    values = payload_for(hourly_result)["topics"][0]["findings"][0]["values"]
    assert all("previous_activity_percent" not in m["metric_id"] for m in values)


def test_unchanged_hours_remain_zero_change_not_missing(hourly_result):
    t = hourly_result["topics"][0]
    for m in t["metrics"][1:]:
        m["value"] = 0
    for h in t["rows"][0]["hours"]:
        h["activity_percent"] = 0
    f = payload_for(hourly_result)["topics"][0]["findings"][0]
    assert len(f["hourly_pair"]) == 2
    assert all(
        m["value"] == 0 for m in f["values"] if m["metric_id"] in f["hourly_pair"]
    )


def test_fact_and_metric_ids_are_distinct_and_incident_period_is_grounded(result):
    topic = result["topics"][1]
    topic["metrics"][0]["period"] = {
        "start": "2026-10-12T15:00:00Z",
        "end": "2026-10-13T15:00:00Z",
    }
    payload = payload_for(result)
    fact = payload["topics"][1]["findings"][0]
    assert "comparison_status" not in fact and "hourly_pair" not in fact
    assert fact["fact_id"] == "incident-period-summary"
    assert fact["values"][0]["metric_id"] == "incident_summary.count.0"
    reply = reply_for(payload)
    reply["sections"][1]["observation"] = (
        "{{period:incident_summary.count.0}}의 저장 사건은 {{value:incident_summary.count.0}}입니다."
    )
    rendered = validate_sections(reply, payload, result)
    assert "10/13 00:00~10/14 00:00 KST" in rendered[1]["observation"]
    reply["sections"][1]["fact_ids"] = ["incident_summary.count.0"]
    assert validate_sections(reply, payload, result)[1] == rendered[1]


async def test_repair_identifies_rejected_field_and_literal(result):
    payload = payload_for(result)
    bad = reply_for(payload)
    bad["sections"][0]["meaning"] = "회수 가능량은 아닙니다."
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [bad, reply_for(payload)]
    await interpret_report(result, llm)
    feedback = llm.complete.call_args_list[1].args[1]["validation_feedback"]
    assert "namespace_usage.meaning" in feedback["error"]
    assert "회수" in feedback["error"]
    assert result["quality"]["report"]["reason"] == "repaired"


@pytest.mark.parametrize(
    "field,text",
    [
        ("meaning", "예측 대기 시간이 줄어들면서 작업이 완료되었습니다."),
        (
            "observation",
            "대기 시간은 {{value:namespace_usage.workload_pending_peak.0}}입니다.",
        ),
        (
            "observation",
            "실행 시간은 {{value:namespace_usage.workload_mean_elapsed_seconds.1}}입니다.",
        ),
        ("meaning", "대기 Pod 수가 감소했습니다."),
    ],
)
def test_workload_counts_do_not_prove_duration_or_trend(field, text):
    from ops_agent.report_interpretation import validate_workload_wording

    values = {"namespace_usage.workload_pending_peak.0": {"unit": "pods"}}
    with pytest.raises(ValueError, match="unsupported_.*"):
        validate_workload_wording(text, field, values)


def test_workload_duration_check_is_not_a_measurement_claim():
    from ops_agent.report_interpretation import validate_workload_wording

    values = {"namespace_usage.workload_pending_peak.0": {"unit": "pods"}}
    validate_workload_wording(
        "대기 시간과 실행 시간을 Pod 기록에서 확인하세요.", "next_check", values
    )
    validate_workload_wording(
        "Job 경과시간에는 대기·준비가 포함될 수 있습니다.", "meaning", values
    )


def test_related_workload_is_attached_and_values_are_unchanged(result):
    topic = result["topics"][0]
    target = {"cluster_id": "cpc-2", "namespace": "forecast"}
    topic["findings"][0]["target"] = target
    mid = "namespace_usage.workload_pending_peak.0"
    topic["metrics"].append(
        {
            "id": mid,
            "value": 2,
            "unit": "pods",
            "period": {"start": "2026-10-14T15:00:00Z", "end": "2026-10-15T15:00:00Z"},
            "target": target,
            "quality": {},
        }
    )
    topic["findings"].append(
        {
            "id": "namespace-workload-0",
            "text": "workload",
            "target": target,
            "value_refs": [mid],
            "evidence_refs": ["workload-evidence"],
        }
    )
    before = deepcopy(result)
    payload = payload_for(result)
    assert (
        payload["topics"][0]["findings"][0]["related_workload_fact_id"]
        == "namespace-workload-0"
    )
    reply = reply_for(payload)
    sections = validate_sections(reply, payload, result)
    assert "2개" in sections[0]["observation"]
    assert "workload-evidence" in sections[0]["evidence_refs"]
    assert result == before
    incomplete = deepcopy(reply)
    incomplete["sections"][0]["meaning"] = "메모리 점유를 확인하세요."
    with pytest.raises(ValueError, match="workload_interpretation_required"):
        validate_sections(incomplete, payload, result)
    reply["sections"][0]["fact_ids"].remove("namespace-workload-0")
    linked = validate_sections(reply, payload, result)
    assert "namespace-workload-0" in linked[0]["source_fact_ids"]
    assert "workload-evidence" in linked[0]["evidence_refs"]
    assert result == before


@pytest.mark.parametrize(
    "text", ["알림 상태는 현재 기준입니다.", "사건이 없으므로 확인할 필요가 없습니다."]
)
def test_incident_absence_is_not_current_health_or_no_check(result, text):
    payload = payload_for(result)
    reply = reply_for(payload)
    reply["sections"][1]["meaning"] = text
    with pytest.raises(ValueError, match="unsupported_incident_assurance"):
        validate_sections(reply, payload, result)


def test_incident_selection_preserves_candidate_order_without_recounting():
    from test_aggregate_report import concentration_report

    result = concentration_report()
    before = deepcopy(result)
    original = [
        f["id"]
        for f in result["topics"][0]["findings"]
        if f["id"].startswith("incident-node-")
    ]
    findings = payload_for(result)["topics"][0]["findings"]
    assert [f["fact_id"] for f in findings[: len(original)]] == original
    assert result == before


@pytest.mark.parametrize("origin", ["schedule", "manual"])
async def test_malformed_json_gets_one_bounded_repair_in_both_origins(
    result, origin, caplog
):
    import json
    import time
    import httpx
    from agent_common.llm import LLM
    from agent_common.settings import Settings

    result["report_origin"] = origin
    before = deepcopy(result)
    requests = []
    valid = reply_for(payload_for(result))

    def respond(request):
        wire = json.loads(request.content)
        assert wire["response_format"] == {"type": "json_object"}
        data = wire["messages"][1]["content"]
        requests.append(json.loads(data))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": '{"sections":'
                            if len(requests) == 1
                            else json.dumps(valid)
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 10,
                    "total_tokens": 30,
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        llm = LLM(
            Settings(
                kind="report",
                llm_base_url="http://fixture.invalid/v1",
                llm_model="fixture",
                llm_api_key="fixture-only",
            ),
            time.monotonic() + 60,
            32768,
            lambda state: None,
            http=client,
        )
        await interpret_report(result, llm)
    assert result["narrative_status"] == "complete"
    assert result["quality"]["report"]["reason"] == "repaired"
    assert result["quality"]["report"]["failures"] == [
        {"attempt": 1, "reason": "llm_invalid_output"}
    ]
    assert len(requests) == 2
    assert requests[1]["validation_feedback"]["error"] == "llm_invalid_output"
    assert result["topics"] == before["topics"]
    assert result["report_origin"] == origin
    assert "reason=llm_invalid_output" in caplog.text
    assert '"sections"' not in caplog.text


@pytest.mark.parametrize(
    "failure",
    [
        "llm_http_error",
        "llm_output_truncated",
        "llm_token_budget_exhausted",
        "llm_deadline_exhausted",
    ],
)
async def test_non_json_failures_are_recorded_without_extra_retry(result, failure):
    llm = AsyncMock(configured=True, last_failure=failure)
    llm.complete.return_value = None
    await interpret_report(result, llm)
    assert llm.complete.await_count == 1
    assert result["narrative_status"] == "failed"
    assert result["quality"]["report"]["failures"] == [
        {"attempt": 1, "reason": failure}
    ]


async def test_repair_transport_failure_preserves_initial_validation_reason(
    result, caplog
):
    llm = AsyncMock(configured=True, last_failure="llm_invalid_output")
    llm.complete.side_effect = [{"sections": []}, None]
    await interpret_report(result, llm)
    assert llm.complete.await_count == 2
    assert result["narrative_status"] == "failed"
    assert result["quality"]["report"]["failures"] == [
        {"attempt": 1, "reason": "topic_sections_required"},
        {"attempt": 2, "reason": "llm_invalid_output"},
    ]
    assert "reason=topic_sections_required" in caplog.text


async def test_repeated_malformed_json_remains_honest_fallback(result):
    before = deepcopy(result["topics"])
    llm = AsyncMock(configured=True, last_failure="llm_invalid_output")
    llm.complete.return_value = None
    await interpret_report(result, llm)
    assert llm.complete.await_count == 2
    assert result["narrative_status"] == "failed"
    assert result["topics"] == before
    assert result["quality"]["report"]["failures"] == [
        {"attempt": 1, "reason": "llm_invalid_output"},
        {"attempt": 2, "reason": "llm_invalid_output"},
    ]


@pytest.mark.parametrize(
    "status", [401, 429, 500, 502, 503, 504, None, "private-response"]
)
async def test_http_failure_keeps_only_numeric_status(result, status):
    before = deepcopy(result["topics"])
    llm = AsyncMock(
        configured=True, last_failure="llm_http_error", last_http_status=status
    )
    llm.complete.return_value = None
    await interpret_report(result, llm)
    failure = {"attempt": 1, "reason": "llm_http_error"}
    if type(status) is int:
        failure["http_status"] = status
    assert result["quality"]["report"]["failures"] == [failure]
    assert result["topics"] == before
    assert result["narrative_status"] == "failed"
    assert llm.complete.await_count == 1


@pytest.mark.parametrize("structure", ["duplicate", "order"])
@pytest.mark.parametrize("repeat_error", [False, True])
async def test_topic_structure_repair_uses_one_complete_shape(
    result, structure, repeat_error
):
    from test_namespace_advice import topic

    result["topics"][0] = topic()
    result["topics"].reverse()
    before = deepcopy(result["topics"])
    valid = reply_for(payload_for(result))
    invalid = deepcopy(valid)
    if structure == "duplicate":
        invalid["sections"].append(deepcopy(invalid["sections"][0]))
        code = "topic_sections_required"
    else:
        invalid["sections"].reverse()
        code = "topic_mismatch"
    original = deepcopy(invalid)
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [invalid, invalid if repeat_error else valid]
    await interpret_report(result, llm)
    first, repair = [call.args[1] for call in llm.complete.call_args_list]
    expected = [t["topic_id"] for t in first["topics"]]
    assert expected == ["incident_summary", "namespace_usage"]
    assert [t["topic_id"] for t in repair["response_shape"]["sections"]] == expected
    assert first["topics"] == repair["topics"]
    assert "summary_repair" not in repair
    assert repair["validation_feedback"]["error"].startswith(code)
    assert (
        "topic_id를 입력 순서대로 각 한 번만"
        in repair["validation_feedback"]["instruction"]
    )
    assert (
        "response_shape.sections만 전체 반환"
        in repair["validation_feedback"]["instruction"]
    )
    for call in llm.complete.call_args_list:
        system = call.args[0]
        assert "response_shape의 주제·항목 ID·순서" in system
        assert 'namespace_usage: {"topic_id"' not in system
        assert 'incident_summary: {"topic_id"' not in system
    assert result["quality"]["report"]["attempts"] == 2
    assert result["quality"]["report"]["failures"] == [
        {"attempt": i, "reason": code} for i in range(1, 3 if repeat_error else 2)
    ]
    assert result["narrative_status"] == ("failed" if repeat_error else "complete")
    assert result["topics"] == before and invalid == original


@pytest.fixture
def concentrated_result(result):
    from test_aggregate_report import concentration_report, concentration_records

    period = {"start": "2026-10-25T15:00:00Z", "end": "2026-10-26T15:00:00Z"}
    records = concentration_records()
    for record in records:
        record["occurred_at"] = period["start"]
    result["topics"][1] = concentration_report(records, period=period)["topics"][0]
    return result


def concentration_reply(payload):
    reply = reply_for(payload)
    incident = next(s for s in reply["sections"] if s["topic_id"] == "incident_summary")
    incident["meaning"] = (
        "같은 종류의 알림이 두 노드에서 기록됐고 이전 비교기간에는 이 종류의 기록이 없었습니다. 저장 알림이며 시험 알림이 섞일 수 있고 동일 GPU 반복 장애·원인·복구는 확정하지 않습니다."
    )
    return reply


def test_incident_payload_reserves_node_facts_and_renders_type_counts(
    concentrated_result,
):
    from ops_agent.incident_findings import INCIDENT_RULES
    from ops_agent.report_interpretation import SYSTEM

    payload = payload_for(concentrated_result)
    facts = payload["topics"][1]["findings"]
    assert [f["fact_id"] for f in facts[:5]] == [f"incident-node-{i}" for i in range(5)]
    assert not any(
        f["fact_id"].startswith(("incident-top-node-", "incident-second-node-"))
        for f in facts
    )
    assert INCIDENT_RULES in SYSTEM
    rendered = validate_sections(
        concentration_reply(payload), payload, concentrated_result
    )[1]
    assert rendered["observation"] == CALCULATED_INCIDENT_OBSERVATION
    assert "54.5%" not in rendered["observation"]
    assert "cpc-1 / dgx01 6건" not in rendered["observation"]
    assert "cpc-1 / dgx02 5건" not in rendered["observation"]
    assert rendered["check_target"] == CALCULATED_INCIDENT_CHECK_TARGET


@pytest.mark.parametrize(
    "count,status", [(0, "ready"), (11, "partial"), (None, "blocked")]
)
async def test_zero_or_unready_incidents_are_excluded_from_llm(
    concentrated_result, count, status
):
    incident = concentrated_result["topics"][1]
    incident["summary"]["count"] = count
    incident["status"] = status
    before = deepcopy(incident)
    payload = payload_for(concentrated_result)
    assert [t["topic_id"] for t in payload["topics"]] == ["namespace_usage"]
    llm = AsyncMock(configured=True)
    llm.complete.return_value = reply_for(payload)
    await interpret_report(concentrated_result, llm)
    assert concentrated_result["narrative_status"] == "complete"
    assert [s["topic_id"] for s in concentrated_result["narrative"]] == [
        "namespace_usage"
    ]
    assert incident == before and llm.complete.call_count == 1


@pytest.mark.parametrize("field", ["meaning", "next_check"])
@pytest.mark.parametrize("advice_mode", [False, True])
async def test_incident_template_echo_uses_one_repair(
    concentrated_result, field, advice_mode
):
    from ops_agent.incident_findings import INCIDENT_RULES
    from ops_agent.report_interpretation import INCIDENT_EXAMPLE
    from test_namespace_advice import topic

    if advice_mode:
        concentrated_result["topics"][0] = topic()
    payload = payload_for(concentrated_result)
    valid = concentration_reply(payload)
    invalid = deepcopy(valid)
    invalid["sections"][1][field] = INCIDENT_EXAMPLE[field]
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [
        invalid,
        {"sections": [valid["sections"][1]]} if advice_mode else valid,
    ]
    await interpret_report(concentrated_result, llm)
    assert concentrated_result["narrative_status"] == "complete"
    assert (
        concentrated_result["quality"]["report"]["failures"][0]["reason"]
        == "template_echo"
    )
    assert concentrated_result["quality"]["report"]["reason"] == "repaired"
    assert llm.complete.call_count == 2
    system, request = llm.complete.call_args_list[0].args
    assert INCIDENT_RULES in system
    if advice_mode:
        assert len(request["topics"][1]["findings"]) == 7
        assert [f["fact_id"] for f in request["topics"][1]["findings"][:3]] == [
            "incident-node-0",
            "incident-node-1",
            "incident-node-2",
        ]
        example = request["response_shape"]["sections"][1]
        assert {key: example[key] for key in INCIDENT_EXAMPLE} == dict.fromkeys(
            INCIDENT_EXAMPLE, ""
        )
        repair = llm.complete.call_args.args[1]
        example = repair["response_shape"]["sections"][0]
        assert {key: example[key] for key in INCIDENT_EXAMPLE} == dict.fromkeys(
            INCIDENT_EXAMPLE, ""
        )
        assert len(repair["section_repair"]) == 1


@pytest.mark.parametrize("advice_mode", [False, True])
async def test_empty_incident_report_preserves_calculated_change(result, advice_mode):
    from test_aggregate_report import concentration_report, concentration_records
    from test_namespace_advice import topic

    incident = concentration_report([], concentration_records())["topics"][0]
    if advice_mode:
        result["topics"][0] = topic()
    result["topics"][1] = incident
    before = deepcopy(result["topics"])
    assert (
        "기간 내 저장된 사건은 0건이며 직전 기간보다 -11건 변했습니다."
        in incident["findings"][0]["text"]
    )
    llm = AsyncMock(configured=True)
    llm.complete.return_value = reply_for(payload_for(result))
    await interpret_report(result, llm)
    assert result["narrative_status"] == "complete"
    assert [s["topic_id"] for s in result["narrative"]] == ["namespace_usage"]
    assert result["topics"] == before
    assert [t["topic_id"] for t in llm.complete.call_args.args[1]["topics"]] == [
        "namespace_usage"
    ]


CALCULATED_INCIDENT_OBSERVATION = (
    "cpc-1 / XID 79 · 10/26 00:00~10/27 00:00 KST: 클러스터 저장 사건 11건 중 8건(이전 비교기간 이 종류 0건). "
    "노드별: cpc-1 / dgx01 / XID 79 5건 · cpc-1 / dgx02 / XID 79 3건."
)
CALCULATED_INCIDENT_CHECK_TARGET = (
    "cpc-1 / dgx01 / XID 79 · 10/26 00:00~10/27 00:00 KST: 저장 사건 5건, 작성 당시 발생 중 1건, 공개 RCA 결과가 있는 사건 5건. "
    "같은 노드의 다른 알림: cpc-1 / dgx01 / XID 13 1건."
)


def test_incident_focus_renders_exact_calculated_observation_and_check(
    concentrated_result,
):
    from ops_agent.incident_findings import incident_focus

    payload = payload_for(concentrated_result)
    focus = incident_focus(payload["topics"][1]["findings"])
    assert payload["topics"][1]["focus"] == focus
    reply = concentration_reply(payload)
    before = deepcopy(reply)
    section = validate_sections(reply, payload, concentrated_result)[1]
    assert section["observation"] == CALCULATED_INCIDENT_OBSERVATION
    assert section["check_target"] == CALCULATED_INCIDENT_CHECK_TARGET
    assert section["observation_source"] == "calculated"
    assert (
        section["source_fact_ids"]
        == focus["ids"]
        == [
            "incident-top-type-cpc-1",
            "incident-node-0",
            "incident-node-1",
            "incident-node-2",
        ]
    )
    assert reply == before


@pytest.mark.parametrize(
    "ids,observation",
    [
        ([], ""),
        (["incident-period-summary"], "임의로 작성한 관측입니다."),
        (["not-offered", "not-offered"], "사건 999건 <script>"),
        (None, None),
    ],
)
def test_incident_model_selection_and_observation_do_not_change_calculation(
    concentrated_result, ids, observation
):
    payload = payload_for(concentrated_result)
    reply = concentration_reply(payload)
    reply["sections"][1].update(fact_ids=ids, observation=observation)
    section = validate_sections(reply, payload, concentrated_result)[1]
    assert section["observation"] == CALCULATED_INCIDENT_OBSERVATION
    assert section["check_target"] == CALCULATED_INCIDENT_CHECK_TARGET


@pytest.mark.parametrize(
    "meaning",
    [
        "비율에 근거해 알림이 한 종류에 몰렸는지 분산된지를 설명하며, 이는 저장된 알림 기록이고 시험 알림이 섞일 수 있고 같은 GPU의 반복 장애·원인·복구는 이 보고서로 확정하지 않으며 발생 중 건수는 작성 시점 기준입니다.",
        "알림 종류와 노드가 몰렸는지 분산된지를 설명하며 기록의 한계를 유지합니다.",
    ],
)
def test_incident_meaning_rejects_instruction_copy(concentrated_result, meaning):
    payload = payload_for(concentrated_result)
    reply = concentration_reply(payload)
    reply["sections"][1]["meaning"] = meaning
    with pytest.raises(ValueError, match="incident_meaning_required"):
        validate_sections(reply, payload, concentrated_result)


@pytest.mark.parametrize("known_node", [False, True])
def test_single_incident_calculated_observation_fallback(known_node):
    from test_aggregate_report import concentration_report, concentration_records

    record = concentration_records()[0]
    if not known_node:
        record["target"] = {}
    report = concentration_report([record])
    payload = payload_for(report)
    section = validate_sections(reply_for(payload), payload, report)[0]
    if known_node:
        assert (
            section["observation"]
            == "cpc-1 / dgx01 / XID 79 · 10/12 00:00~10/13 00:00 KST: 저장 사건 1건."
        )
        assert "저장 사건 1건, 작성 당시 발생 중 1건" in section["check_target"]
    else:
        assert (
            section["observation"]
            == "선택한 보고서 범위 · 10/12 00:00~10/13 00:00 KST: 저장 사건 1건(이전 비교기간 0건)."
        )
        assert section["next_check"] == reply_for(payload)["sections"][0]["next_check"]
    assert section["observation_source"] == "calculated"


@pytest.mark.parametrize("firing", [True, False])
def test_incident_check_prefers_first_firing_fact_then_first_node(firing):
    from ops_agent.incident_findings import incident_focus
    from test_aggregate_report import concentration_report, concentration_records

    records = concentration_records()
    for record in records:
        record["alarm_status"] = (
            "firing" if firing and record["id"] == "event-9" else "resolved"
        )
    payload = payload_for(concentration_report(records))
    facts = payload["topics"][0]["findings"]
    nodes = [f for f in facts if f["fact_id"].startswith("incident-node-")]
    focus = incident_focus([f for f in facts if f not in nodes] + list(reversed(nodes)))
    expected = (
        next((f for f in nodes if f["target"]["alert_type"] == "SXID 11001"), None)
        if firing
        else nodes[-1]
    )
    assert "{{target:" + expected["fact_id"] + "}}" in focus["check_target"]
    assert ("작성 당시 발생 중" in focus["check_target"]) == firing


def test_two_cluster_observations_keep_cluster_order_and_check_facts():
    from ops_agent.incident_findings import incident_focus
    from test_aggregate_report import concentration_report, concentration_records
    from test_namespace_advice import topic

    records = concentration_records()
    other = [
        {**r, "id": "other-" + r["id"], "cluster_id": "cpc-2"} for r in records[:7]
    ]
    report = concentration_report(other + records)
    report["topics"].insert(0, topic())
    payload = payload_for(report)
    facts = payload["topics"][1]["findings"]
    assert len(facts) == 9
    assert all(f["fact_id"].startswith("incident-node-") for f in facts[:6])
    assert any(f["fact_id"].startswith("incident-node-") for f in facts)
    section = validate_sections(concentration_reply(payload), payload, report)[1]
    assert section["observation"].index("cpc-1 / XID 79") < section[
        "observation"
    ].index("cpc-2 / XID 79")
    assert len(section["source_fact_ids"]) == len(incident_focus(facts)["ids"]) == 7


@pytest.mark.parametrize("check", ["", " ", "글" * 451, None])
def test_incident_model_check_keeps_original_text_limit(concentrated_result, check):
    payload = payload_for(concentrated_result)
    reply = concentration_reply(payload)
    reply["sections"][1]["next_check"] = check
    with pytest.raises(ValueError, match="invalid_section_text"):
        validate_sections(reply, payload, concentrated_result)


@pytest.mark.parametrize(
    "field,text",
    [
        ("meaning", "종류와 노드는 원인입니다."),
        ("next_check", "복구 완료를 확인하세요."),
        ("meaning", "종류와 노드는 {{value:unknown}}입니다."),
    ],
)
def test_calculated_incident_keeps_prose_and_reference_guards(
    concentrated_result, field, text
):
    payload = payload_for(concentrated_result)
    reply = concentration_reply(payload)
    reply["sections"][1][field] = text
    with pytest.raises(ValueError):
        validate_sections(reply, payload, concentrated_result)


async def test_incident_meaning_copy_uses_existing_partial_repair(concentrated_result):
    from test_namespace_advice import topic

    concentrated_result["topics"][0] = topic()
    payload = payload_for(concentrated_result)
    valid = concentration_reply(payload)
    invalid = deepcopy(valid)
    invalid["sections"][1]["meaning"] = (
        "알림 종류와 노드가 몰렸는지 분산된지를 설명하며 저장된 기록입니다."
    )
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [invalid, {"sections": [valid["sections"][1]]}]
    await interpret_report(concentrated_result, llm)
    assert concentrated_result["narrative_status"] == "complete"
    assert concentrated_result["quality"]["report"]["failures"] == [
        {
            "attempt": 1,
            "reason": "incident_meaning_required",
            "topic_failures": [
                {"topic_id": "incident_summary", "reason": "incident_meaning_required"}
            ],
        }
    ]
    assert (
        concentrated_result["quality"]["report"]["interpretation_version"]
        == "ops-interpretation-incident-check-v10"
    )
    section = next(
        s
        for s in concentrated_result["narrative"]
        if s["topic_id"] == "incident_summary"
    )
    assert section["observation"] == CALCULATED_INCIDENT_OBSERVATION
    assert section["check_target"] == CALCULATED_INCIDENT_CHECK_TARGET
    assert llm.complete.call_count == 2


def test_incident_check_target_does_not_consume_model_check_limit(concentrated_result):
    payload = payload_for(concentrated_result)
    reply = concentration_reply(payload)
    check = "기록을 대조하세요. " * 37
    assert len(check) <= 450
    reply["sections"][1]["next_check"] = check
    section = validate_sections(reply, payload, concentrated_result)[1]
    assert section["next_check"] == check.strip()
    assert section["check_target"] == CALCULATED_INCIDENT_CHECK_TARGET
    assert len(section["next_check"]) <= 450


def test_incident_source_labels_and_check_context_are_separate(concentrated_result):
    payload = payload_for(concentrated_result)
    focus = payload["topics"][1]["focus"]
    assert focus["check_context"] == {
        "fact_id": "incident-node-0",
        "count": 5,
        "firing": 1,
        "rca_count": 5,
        "same_type_fact_ids": ["incident-node-0", "incident-node-1"],
        "other_alert_fact_ids": ["incident-node-2"],
        "type_previous_count": 0,
    }
    reply = concentration_reply(payload)
    reply["sections"][1].update(
        fact_ids=[], observation="", check_target="モデル入力は使用しない"
    )
    section = validate_sections(reply, payload, concentrated_result)[1]
    assert section["next_check"] == reply["sections"][1]["next_check"]
    assert section["check_target"] == CALCULATED_INCIDENT_CHECK_TARGET
    labels = [
        "알림 집계(자동 집계)",
        "AI 운영 해석",
        "확인 대상(자동 선정)",
        "AI 확인 제안",
    ]
    positions = [section["text"].index(label) for label in labels]
    assert positions == sorted(positions)
    assert "눈에 띄는 변화:" not in section["text"]
    assert section["text"].count(CALCULATED_INCIDENT_CHECK_TARGET) == 1


@pytest.mark.parametrize("field", ["meaning", "next_check"])
@pytest.mark.parametrize(
    "claim",
    [
        "새로 나타난 종류입니다",
        "새로 발생했습니다",
        "새로운 장애입니다",
        "최초 발생입니다",
        "공통 원인은 미확인입니다",
        "동시에 발생했습니다",
    ],
)
def test_incident_overreach_is_rejected(concentrated_result, field, claim):
    payload = payload_for(concentrated_result)
    reply = concentration_reply(payload)
    reply["sections"][1][field] = claim
    with pytest.raises(ValueError, match="incident_overreach"):
        validate_sections(reply, payload, concentrated_result)


@pytest.mark.parametrize(
    "rca_count,check,valid",
    [
        (0, "RCA 결과와 대조하세요.", False),
        (0, "기존 rca 결과를 검토하세요.", False),
        (0, "RCA 분석 결과와 점검 기록을 비교하세요.", False),
        (0, "RCA 결과 유무와 작업 생성 여부·상태를 확인하세요.", True),
        (0, "RCA 결과가 있는지 확인하세요.", True),
        (0, "RCA 작업 상태와 작성 이후 해제됐는지 확인하세요.", True),
        (1, "공개된 RCA 결과만 점검 기록과 대조하세요.", True),
        (1, "모든 사건의 RCA 결과를 대조하세요.", False),
        (5, "모든 사건의 RCA 결과를 대조하세요.", True),
    ],
)
def test_incident_rca_reference_respects_selected_target(rca_count, check, valid):
    from test_aggregate_report import concentration_records, concentration_report

    records = concentration_records()
    for i, record in enumerate(records[:5]):
        record["result_id"] = f"published-{i}" if i < rca_count else None
    report = concentration_report(records)
    payload = payload_for(report)
    reply = reply_for(payload)
    reply["sections"][0]["next_check"] = check
    assert payload["topics"][0]["focus"]["check_context"]["rca_count"] == rca_count
    if valid:
        section = validate_sections(reply, payload, report)[0]
        assert section["next_check"] == check
        assert f"공개 RCA 결과가 있는 사건 {rca_count}건" in section["check_target"]
    else:
        with pytest.raises(ValueError, match="incident_rca_reference"):
            validate_sections(reply, payload, report)


def test_four_clusters_keep_check_target_through_advice_input_cap():
    from test_aggregate_report import concentration_records, concentration_report
    from test_namespace_advice import topic

    records = [
        {**r, "id": f"{cluster}-{r['id']}", "cluster_id": f"cpc-{cluster}"}
        for cluster in range(1, 5)
        for r in concentration_records()
    ]
    report = concentration_report(records)
    report["topics"].insert(0, topic())
    wire = payload_for(report)
    incident = wire["topics"][1]
    assert len(incident["findings"]) <= 12
    assert (
        sum(f["fact_id"].startswith("incident-node-") for f in incident["findings"])
        == 6
    )
    assert incident["focus"]["check_context"]["firing"] == 1
    assert incident["omitted_findings"] == 14
    section = validate_sections(reply_for(wire), wire, report)[1]
    assert "선정 한도로 일부 근거를 생략" in section["interpretation_limit"]
    assert "노드가 확인된 사건이 없어" not in section["text"]


@pytest.mark.parametrize("known_node", [True, False])
def test_selected_node_detail_is_not_presented_as_full_distribution(known_node):
    from test_aggregate_report import concentration_records, concentration_report

    base = concentration_records()[0]
    records = [
        {
            **base,
            "id": str(i),
            "alarm_status": "resolved",
            "target": {"node": f"node-{i}"} if known_node or i < 2 else {},
        }
        for i in range(8)
    ]
    report = concentration_report(records)
    wire = payload_for(report)
    section = validate_sections(reply_for(wire), wire, report)[0]
    assert "저장 사건 8건 중 8건" in section["observation"]
    assert "확인된 일부 노드 내역:" in section["observation"]
    assert (
        "나머지 사건의 노드별 내역은 이 해석에 포함하지 않았습니다."
        in section["observation"]
    )


def test_single_event_cluster_is_kept_beside_top_type_cluster():
    from test_aggregate_report import concentration_records, concentration_report

    records = concentration_records()
    records.append({**records[0], "id": "single", "cluster_id": "cpc-2"})
    report = concentration_report(records)
    wire = payload_for(report)
    section = validate_sections(reply_for(wire), wire, report)[0]
    assert "cpc-1 / XID 79" in section["observation"]
    assert "cpc-2 / dgx01 / XID 79" in section["observation"]


@pytest.mark.parametrize("known_node", [False, True])
def test_incident_meaning_does_not_require_literal_type_and_node_terms(known_node):
    from test_aggregate_report import concentration_records, concentration_report

    records = concentration_records()
    if not known_node:
        for record in records:
            record["target"] = {}
    report = concentration_report(records)
    wire = payload_for(report)
    reply = reply_for(wire)
    reply["sections"][0]["meaning"] = (
        "이전 비교기간에는 기록이 없었습니다. 시험 알림이 섞일 수 있으며 원인은 확정하지 않습니다."
    )
    section = validate_sections(reply, wire, report)[0]
    if not known_node:
        assert section["check_target"] == ""
        assert "노드가 확인된 사건이 없어 선정하지 않았습니다." in section["text"]


async def test_incident_rca_repair_preserves_focus_and_valid_namespace(
    concentrated_result,
):
    from test_namespace_advice import topic

    concentrated_result["topics"][0] = topic()
    for metric in concentrated_result["topics"][1]["metrics"]:
        if ".node_alert_rca." in metric["id"]:
            metric["value"] = 0
    wire = payload_for(concentrated_result)
    valid = reply_for(wire)
    baseline = deepcopy(concentrated_result)
    await interpret_report(
        baseline,
        AsyncMock(configured=True, complete=AsyncMock(return_value=deepcopy(valid))),
    )
    invalid = deepcopy(valid)
    invalid["sections"][1]["next_check"] = "RCA 결과를 검토하세요."
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [invalid, {"sections": [valid["sections"][1]]}]
    await interpret_report(concentrated_result, llm)
    first = llm.complete.call_args_list[0].args[1]
    repair = llm.complete.call_args_list[1].args[1]
    assert first["topics"][1]["focus"] == repair["section_repair"][0]["topic"]["focus"]
    assert concentrated_result["narrative"][0] == baseline["narrative"][0]
    assert concentrated_result["quality"]["report"]["failures"] == [
        {
            "attempt": 1,
            "reason": "incident_rca_reference",
            "topic_failures": [
                {"topic_id": "incident_summary", "reason": "incident_rca_reference"}
            ],
        }
    ]
    assert concentrated_result["narrative_status"] == "complete"


@pytest.mark.parametrize("field", ["meaning", "next_check"])
@pytest.mark.parametrize(
    "name",
    ["dgx01에서", "XID 79가", "cpc-1의", "dgx01·dgx02와", "(dgx01), XID 79."],
)
def test_incident_exact_target_names_allow_korean_particles(
    concentrated_result, field, name
):
    payload = payload_for(concentrated_result)
    reply = concentration_reply(payload)
    reply["sections"][1][field] += " " + name + " 저장된 범위를 확인하세요."
    before = deepcopy(reply)
    section = validate_sections(reply, payload, concentrated_result)[1]
    assert name in section[field]
    assert section["observation"] == CALCULATED_INCIDENT_OBSERVATION
    assert section["check_target"] == CALCULATED_INCIDENT_CHECK_TARGET
    assert reply == before


@pytest.mark.parametrize("field", ["meaning", "next_check"])
@pytest.mark.parametrize(
    "text",
    [
        "dgx010에서",
        "XID 790가",
        "xdgx01에서",
        "dgx01x에서",
        "xXID 79가",
        "dgx01１에서",
        "dgx03에서",
        "SXID 11001이",
        "CPC-1에서",
        "XID  79가",
        "dgx01에서 5건",
        "XID 79가 72.7%",
        "dgx01에서 10/26에",
    ],
)
def test_incident_names_do_not_exempt_other_numbers(concentrated_result, field, text):
    payload = payload_for(concentrated_result)
    reply = concentration_reply(payload)
    reply["sections"][1][field] += " " + text + " 저장된 범위를 확인하세요."
    with pytest.raises(ValueError, match="unsupported_prose") as caught:
        validate_sections(reply, payload, concentrated_result)
    assert caught.value.topic_id == "incident_summary"
    assert caught.value.field == field
    assert caught.value.violation_kind == "number"


@pytest.mark.parametrize("key", ["cluster_id", "cluster"])
def test_incident_cluster_target_name_is_grounded(concentrated_result, key):
    payload = payload_for(concentrated_result)
    payload["topics"][1]["findings"][0]["target"][key] = "lab-7"
    reply = concentration_reply(payload)
    reply["sections"][1]["meaning"] += " lab-7에서 기록됐습니다."
    section = validate_sections(reply, payload, concentrated_result)[1]
    assert "lab-7에서" in section["meaning"]


@pytest.mark.parametrize(
    "name,kind",
    [
        ("dgx.01", "number"),
        ("node-01%", "symbol"),
        ("때문에-01", "forbidden_expression"),
    ],
)
def test_incident_name_matching_is_literal_and_preserves_other_guards(
    concentrated_result, name, kind
):
    payload = payload_for(concentrated_result)
    payload["topics"][1]["findings"][0]["target"]["node"] = name
    reply = concentration_reply(payload)
    reply["sections"][1]["meaning"] += (
        " " + ("dgxX01" if kind == "number" else name) + "에서 기록됐습니다."
    )
    with pytest.raises(ValueError, match="unsupported_prose") as caught:
        validate_sections(reply, payload, concentrated_result)
    assert caught.value.violation_kind == kind


@pytest.mark.parametrize("field", ["meaning", "next_check"])
def test_namespace_literal_node_name_still_requires_token(result, field):
    result["topics"][0]["findings"][0]["target"]["node"] = "dgx01"
    payload = payload_for(result)
    reply = reply_for(payload)
    reply["sections"][0][field] += " dgx01에서 기록됐습니다."
    with pytest.raises(ValueError, match="unsupported_prose") as caught:
        validate_sections(reply, payload, result)
    assert caught.value.topic_id == "namespace_usage"
    assert caught.value.field == field
    assert caught.value.violation_kind == "number"


@pytest.mark.parametrize("advice_mode", [False, True])
async def test_incident_short_names_complete_without_repair(
    concentrated_result, advice_mode
):
    if advice_mode:
        from test_namespace_advice import topic

        concentrated_result["topics"][0] = topic()
    payload = payload_for(concentrated_result)
    reply = concentration_reply(payload)
    reply["sections"][1]["meaning"] = (
        "dgx01·dgx02에서 XID 79가 기록됐고 이전 비교기간에는 이 종류의 기록이 없었습니다. "
        "dgx01의 XID 13도 함께 확인할 대상입니다. 저장 알림이며 시험 알림이 섞일 수 있고 원인·복구는 확정하지 않습니다."
    )
    llm = AsyncMock(configured=True)
    llm.complete.return_value = reply
    await interpret_report(concentrated_result, llm)
    assert llm.complete.await_count == 1
    report = concentrated_result["quality"]["report"]
    assert concentrated_result["narrative_status"] == "complete"
    assert report["method"] == "llm_interpreted" and report["reason"] == "complete"
    assert not report.get("failures") and "topic_statuses" not in report
    system = llm.complete.call_args.args[0]
    assert "건수·발생 중 건수·공개 RCA 수는 반복하지 마세요" in system
    assert "실제 선택된 근거에 있는 이름만" in system
    assert "다른 주제의 이름 직접 작성 금지는 유지" in system


@pytest.mark.parametrize("previous_count", [0, 2])
@pytest.mark.parametrize(
    "scope", ["match", "other_type", "other_cluster", "single", "no_node"]
)
def test_incident_previous_context_has_exact_type_and_cluster_scope(
    previous_count, scope
):
    from ops_agent.incident_findings import incident_focus
    from test_aggregate_report import concentration_records, concentration_report

    records = concentration_records()
    if scope == "single":
        records = records[:1]
    if scope == "no_node":
        for record in records:
            record["target"] = {}
    report = concentration_report(records)
    facts = payload_for(report)["topics"][0]["findings"]
    original = deepcopy(facts)
    for fact in facts:
        if not fact["fact_id"].startswith("incident-top-type-"):
            continue
        for metric in fact["values"]:
            if ".top_type_previous_count." in metric["metric_id"]:
                metric["value"] = previous_count
        if scope == "other_type":
            fact["target"]["alert_type"] = "another-type"
        if scope == "other_cluster":
            fact["target"]["cluster_id"] = "another-cluster"
    before = deepcopy(facts)
    focus = incident_focus(facts)
    assert facts == before
    if scope == "no_node":
        assert focus["check_context"] is None
        assert focus["check_target"] == ""
    else:
        assert focus["check_context"]["type_previous_count"] == (
            previous_count if scope == "match" else None
        )
        assert focus["check_context"]["fact_id"] == "incident-node-0"
    # Previous counts do not participate in selection or alter tokenized observation.
    if scope == "match":
        baseline = incident_focus(original)
        for key in ("ids", "observation", "check_target"):
            assert focus[key] == baseline[key]


@pytest.mark.parametrize("field", ["meaning", "next_check"])
@pytest.mark.parametrize("rca_count", [0, 1, 5])
@pytest.mark.parametrize(
    "claim",
    [
        "공개 RCA 결과로 원인이 확인된 사건입니다.",
        "RCA 조사가 모두 완료된 대상입니다.",
        "RCA 본문에서 확인된 원인과 알림 시각을 대조하세요.",
    ],
)
def test_incident_rca_source_claims_are_rejected_for_any_coverage(
    field, rca_count, claim
):
    from test_aggregate_report import concentration_records, concentration_report

    records = concentration_records()
    for i, record in enumerate(records[:5]):
        record["result_id"] = f"published-{i}" if i < rca_count else None
    report = concentration_report(records)
    payload = payload_for(report)
    reply = reply_for(payload)
    reply["sections"][0][field] = claim
    with pytest.raises(ValueError, match="^incident_overreach:"):
        validate_sections(reply, payload, report)


@pytest.mark.parametrize("rca_count", [0, 1, 5])
@pytest.mark.parametrize(
    "field,text",
    [
        ("meaning", "원인은 확인되지 않았습니다."),
        ("meaning", "RCA 조사가 완료되지 않았는지는 별도 확인 사항입니다."),
        ("next_check", "RCA 작업이 완료됐는지 상태를 확인하세요."),
        ("next_check", "RCA 조사가 완료됐는지 상태를 확인하세요."),
        ("next_check", "원인이 확인됐는지 조사 기록을 확인하세요."),
    ],
)
def test_incident_rca_negative_and_check_proposals_remain_valid(rca_count, field, text):
    from test_aggregate_report import concentration_records, concentration_report

    records = concentration_records()
    for i, record in enumerate(records[:5]):
        record["result_id"] = f"published-{i}" if i < rca_count else None
    report = concentration_report(records)
    payload = payload_for(report)
    reply = reply_for(payload)
    reply["sections"][0][field] = text
    assert validate_sections(reply, payload, report)[0][field] == text


@pytest.mark.parametrize("rca_count", [1, 5])
def test_incident_published_rca_time_comparison_is_a_proposal(rca_count):
    from test_aggregate_report import concentration_records, concentration_report

    records = concentration_records()
    for i, record in enumerate(records[:5]):
        record["result_id"] = f"published-{i}" if i < rca_count else None
    report = concentration_report(records)
    payload = payload_for(report)
    reply = reply_for(payload)
    text = "공개된 RCA 결과가 이 알림 시각을 다루는지 대조하세요."
    reply["sections"][0]["next_check"] = text
    assert validate_sections(reply, payload, report)[0]["next_check"] == text


def test_incident_rules_scope_purpose_without_names_or_rank_examples():
    from ops_agent.incident_findings import INCIDENT_RULES
    from ops_agent.report_interpretation import SYSTEM, ADVICE_SYSTEM

    for system in (SYSTEM, ADVICE_SYSTEM):
        assert INCIDENT_RULES in system
        assert "type_previous_count" in system
        assert "노드별 이전 기록이 아닙니다" in system
        assert "0이면 기간 중 알림" in system
        assert "앞으로 확인할 자료" in system
        assert "관측 사실을 다시 열거하지 말고" in system
        assert "공개 결과와의 대조 목적을 빠짐없이" in system
        assert INCIDENT_LIMIT in system
        assert "meaning은 두 문장" in system
        assert "meaning에 쓰지 말고" in system
        assert "코드가 별도 한계를 표시해도 이 둘째 문장은 생략하지 마세요" in system
        assert "한계 문장만 단독으로 반환하지 마세요" in system
        assert "숫자를 한글 수사로 바꿔 쓰지 마세요" in system
        assert (
            "next_check에서 같은 노드의 다른 알림이나 같은 종류의 다른 노드" in system
        )
        assert "원인 한계는 '확인되지 않았습니다'" not in system
        assert "각각을 모두 설명할 의무는 없습니다" in system
        assert "핵심 이유 하나" in system
        assert "때문에·때문이다" in system
        assert "부정문·한계 문장에서도 쓰지" in system
        assert "'~이 있어', '~이므로'" in system
        assert "meaning의 확인 목적은 '~했는지·~됐는지' 대신 '~ 여부'" in system
        assert "선후·연쇄·시간 겹침을 사실로 단정하지" in system
        assert "후보 선정 순위·위험도·심각도" in system
        assert "dgx01·dgx02에서 XID 79가 기록됐습니다" not in system
        assert "INCIDENT_RULES" not in system


def test_mixed_topic_shape_guidance_is_scoped_to_full_responses():
    from ops_agent.report_interpretation import SYSTEM, ADVICE_SYSTEM

    guidance = "부분 보완이 아니면 JSON 객체의 sections 배열에"
    assert guidance in ADVICE_SYSTEM
    assert guidance not in SYSTEM
    assert "주제 ID를 최상위 키로 쓰거나 같은 topic_id를 반복" in ADVICE_SYSTEM
    assert "Namespace 후보는 namespace_usage 항목의 advice 배열에" in ADVICE_SYSTEM
    assert "부분 보완은 요청한 항목만 반환" in ADVICE_SYSTEM


@pytest.mark.parametrize(
    "field,text,reason,violation",
    [
        ("meaning", "이전 기록이 있어 확인이 필요합니다.", None, None),
        ("meaning", "저장 범위가 제한적이므로 확인이 필요합니다.", None, None),
        ("meaning", "원인은 확인되지 않았습니다.", None, None),
        ("meaning", "원인·같은 GPU 반복 장애·복구는 확정하지 않습니다.", None, None),
        ("meaning", "해제 여부를 확인할 필요가 있습니다.", None, None),
        ("next_check", "해제됐는지 상태를 확인하세요.", None, None),
        (
            "meaning",
            "있기 때문에 확인이 필요합니다.",
            "unsupported_prose",
            "forbidden_expression",
        ),
        (
            "meaning",
            "원인으로 판단할 수 없습니다.",
            "unsupported_prose",
            "forbidden_expression",
        ),
        (
            "meaning",
            "복구 완료를 뜻하지 않습니다.",
            "unsupported_prose",
            "forbidden_expression",
        ),
        (
            "meaning",
            "해결됐다고 볼 수 없습니다.",
            "unsupported_prose",
            "forbidden_expression",
        ),
        (
            "meaning",
            "해제됐는지 확인할 필요가 있습니다.",
            "incident_meaning_required",
            None,
        ),
        ("meaning", "원인이 확인된 것은 아닙니다.", "incident_overreach", None),
    ],
)
def test_incident_prompt_wording_matches_existing_validator(
    concentrated_result, field, text, reason, violation
):
    payload = payload_for(concentrated_result)
    reply = concentration_reply(payload)
    reply["sections"][1][field] = text
    if reason is None:
        assert validate_sections(reply, payload, concentrated_result)[1][field] == text
    else:
        with pytest.raises(ValueError, match=f"^{reason}:") as caught:
            validate_sections(reply, payload, concentrated_result)
        if violation:
            assert caught.value.topic_id == "incident_summary"
            assert caught.value.field == field
            assert caught.value.violation_kind == violation


def test_incident_fixed_limit_is_not_an_instruction_placeholder():
    from ops_agent.incident_findings import INCIDENT_RULES
    from ops_agent.report_interpretation import INCIDENT_EXAMPLE

    assert INCIDENT_RULES.count(INCIDENT_LIMIT) == 1
    assert INCIDENT_LIMIT not in INCIDENT_EXAMPLE.values()


@pytest.mark.parametrize(
    "suffix,reason,violation",
    [
        ("", None, None),
        (" 13건입니다.", "unsupported_prose", "number"),
        (" 때문에 확인이 필요합니다.", "unsupported_prose", "forbidden_expression"),
        (" XID79 기록입니다.", "unsupported_prose", "number"),
    ],
)
def test_incident_fixed_limit_keeps_existing_prose_guards(
    concentrated_result, suffix, reason, violation
):
    payload = payload_for(concentrated_result)
    reply = concentration_reply(payload)
    meaning = (
        "이 확인 대상의 알림 시각이 기존 기록에 포함되는지는 미확인입니다. "
        + INCIDENT_LIMIT
        + suffix
    )
    reply["sections"][1]["meaning"] = meaning
    if reason is None:
        assert (
            validate_sections(reply, payload, concentrated_result)[1]["meaning"]
            == meaning
        )
    else:
        with pytest.raises(ValueError, match=f"^{reason}:") as caught:
            validate_sections(reply, payload, concentrated_result)
        assert caught.value.violation_kind == violation


@pytest.mark.parametrize("field", ["meaning", "next_check"])
def test_incident_exact_names_remain_valid_despite_writing_guidance(
    concentrated_result, field
):
    payload = payload_for(concentrated_result)
    reply = concentration_reply(payload)
    reply["sections"][1][field] = "XID 79 기록을 확인할 대상입니다."
    assert (
        validate_sections(reply, payload, concentrated_result)[1][field]
        == reply["sections"][1][field]
    )


@pytest.mark.parametrize("text", [INCIDENT_LIMIT, "저장 알림은 열세 건입니다."])
def test_current_validator_limit_allows_limit_only_or_hangul_counts(
    concentrated_result, text
):
    payload = payload_for(concentrated_result)
    reply = concentration_reply(payload)
    reply["sections"][1]["meaning"] = text
    assert validate_sections(reply, payload, concentrated_result)[1]["meaning"] == text
