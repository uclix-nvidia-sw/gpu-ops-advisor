"""Editorial contract: immutable calculations, grounded tokens and honest fallback."""

from copy import deepcopy
from unittest.mock import AsyncMock
import asyncio
import pytest
from agent_common.llm import RemoteUncertain
from ops_agent.report_interpretation import (
    interpret_report,
    payload_for,
    validate_sections,
)


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
            sections.append(
                {
                    "topic_id": "incident_summary",
                    "fact_ids": [],
                    "observation": "",
                    "meaning": "알림 종류와 노드 분포는 저장된 관측이며 같은 원인을 뜻하지 않습니다.",
                    "next_check": "해당 알림의 발생 시각을 기존 RCA 결과·점검 기록과 대조하고 발생 중 건의 해제 여부를 확인하세요.",
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
        == "선택한 보고서 범위 · 10/13 00:00~10/14 00:00 KST: 저장 사건 1건(이전 0건)."
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


def test_incident_selection_ranks_recorded_firing_then_count_without_recounting(result):
    incident = result["topics"][1]
    incident["metrics"], incident["findings"] = [], []
    for name, count, firing in (
        ("quiet-node", 10, 0),
        ("active-node", 2, 1),
        ("more-active-node", 5, 1),
    ):
        ids = []
        for field, value in (
            ("node_alert_count", count),
            ("node_alert_firing", firing),
        ):
            mid = f"incident_summary.{field}.{name}"
            ids.append(mid)
            incident["metrics"].append(
                dict(id=mid, value=value, unit="events", period={}, quality={})
            )
        incident["findings"].append(
            dict(
                id=name,
                text="저장된 알림",
                target=dict(cluster_id="cpc-1", node=name, alert_type="XID"),
                value_refs=ids,
            )
        )
    before = deepcopy(result)
    findings = payload_for(result)["topics"][1]["findings"]
    assert [f["fact_id"] for f in findings] == [
        "more-active-node",
        "active-node",
        "quiet-node",
    ]
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
        "최다 알림 종류는 이전 기간에 없었고 이번에는 한 종류가 대부분을 차지했습니다. 노드는 양쪽에 비슷하게 나뉘었습니다. 저장 알림이며 시험 알림이 섞일 수 있고 동일 GPU 반복 장애·원인·복구는 확정하지 않습니다."
    )
    return reply


def test_concentration_payload_order_and_rendered_tokens(concentrated_result):
    from ops_agent.incident_findings import INCIDENT_RULES
    from ops_agent.report_interpretation import SYSTEM

    payload = payload_for(concentrated_result)
    assert [f["fact_id"] for f in payload["topics"][1]["findings"][:3]] == [
        "incident-top-type-cpc-1",
        "incident-top-node-cpc-1",
        "incident-second-node-cpc-1",
    ]
    assert INCIDENT_RULES in SYSTEM
    reply = concentration_reply(payload)
    rendered = validate_sections(reply, payload, concentrated_result)[1]
    assert all(
        text in rendered["observation"]
        for text in ("11건", "8건", "72.7%", "6건", "54.5%", "0건")
    )
    assert rendered["source_fact_ids"] == [
        "incident-top-type-cpc-1",
        "incident-top-node-cpc-1",
        "incident-second-node-cpc-1",
        "incident-node-0",
    ]
    assert "cpc-1 / dgx01 / XID 79" in rendered["next_check"]


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
        assert len(request["topics"][1]["findings"]) == 9
        assert [f["fact_id"] for f in request["topics"][1]["findings"][:3]] == [
            "incident-top-type-cpc-1",
            "incident-top-node-cpc-1",
            "incident-second-node-cpc-1",
        ]
        example = request["response_shape"]["sections"][1]
        assert {key: example[key] for key in INCIDENT_EXAMPLE} == INCIDENT_EXAMPLE
        repair = llm.complete.call_args.args[1]
        example = repair["response_shape"]["sections"][0]
        assert {key: example[key] for key in INCIDENT_EXAMPLE} == INCIDENT_EXAMPLE
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
    "cpc-1 / XID 79 · 10/26 00:00~10/27 00:00 KST: 클러스터 저장 사건 11건(이전 0건) 중 8건, 72.7%(이 종류의 이전 기간 0건). "
    "노드별: cpc-1 / dgx01 6건, 54.5%, 작성 당시 발생 중 1건 · cpc-1 / dgx02 5건, 45.5%."
)
CALCULATED_INCIDENT_CHECK_PREFIX = "cpc-1 / dgx01 / XID 79 · 10/26 00:00~10/27 00:00 KST: 저장 사건 5건, 작성 당시 발생 중 1건. "


def test_incident_focus_renders_exact_calculated_observation_and_check(
    concentrated_result,
):
    from ops_agent.incident_findings import incident_focus

    payload = payload_for(concentrated_result)
    focus = incident_focus(payload["topics"][1]["findings"])
    assert len(focus["observation"]) > 450
    reply = concentration_reply(payload)
    before = deepcopy(reply)
    section = validate_sections(reply, payload, concentrated_result)[1]
    assert section["observation"] == CALCULATED_INCIDENT_OBSERVATION
    assert section["next_check"].startswith(CALCULATED_INCIDENT_CHECK_PREFIX)
    assert section["observation_source"] == "calculated"
    assert (
        section["source_fact_ids"]
        == focus["ids"]
        == [
            "incident-top-type-cpc-1",
            "incident-top-node-cpc-1",
            "incident-second-node-cpc-1",
            "incident-node-0",
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
    assert section["next_check"].startswith(CALCULATED_INCIDENT_CHECK_PREFIX)


@pytest.mark.parametrize(
    "meaning",
    [
        "비율에 근거해 알림이 한 종류에 몰렸는지 분산된지를 설명하며, 이는 저장된 알림 기록이고 시험 알림이 섞일 수 있고 같은 GPU의 반복 장애·원인·복구는 이 보고서로 확정하지 않으며 발생 중 건수는 작성 시점 기준입니다.",
        "알림 종류와 노드가 몰렸는지 분산된지를 설명하며 기록의 한계를 유지합니다.",
        "알림 종류는 한 종류에 집중됐습니다.",
        "노드는 양쪽에 나뉘었습니다.",
    ],
)
def test_incident_meaning_requires_conclusions_for_type_and_node(
    concentrated_result, meaning
):
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
            == "cpc-1 / dgx01 / XID 79 · 10/12 00:00~10/13 00:00 KST: 저장 사건 1건, 작성 당시 발생 중 1건."
        )
        assert section["next_check"].startswith(section["observation"] + " ")
    else:
        assert (
            section["observation"]
            == "선택한 보고서 범위 · 10/12 00:00~10/13 00:00 KST: 저장 사건 1건(이전 0건)."
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
    assert "{{target:" + expected["fact_id"] + "}}" in focus["check_prefix"]
    assert ("작성 당시 발생 중" in focus["check_prefix"]) == firing


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
    assert len(facts) == 12
    assert [f["fact_id"] for f in facts[:7]] == [
        "incident-top-type-cpc-1",
        "incident-top-node-cpc-1",
        "incident-second-node-cpc-1",
        "incident-top-type-cpc-2",
        "incident-top-node-cpc-2",
        "incident-second-node-cpc-2",
        "incident-period-summary",
    ]
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
        {"attempt": 1, "reason": "incident_meaning_required"}
    ]
    assert (
        concentrated_result["quality"]["report"]["interpretation_version"]
        == "ops-interpretation-incident-calculated-v5"
    )
    section = next(
        s
        for s in concentrated_result["narrative"]
        if s["topic_id"] == "incident_summary"
    )
    assert section["observation"] == CALCULATED_INCIDENT_OBSERVATION
    assert section["next_check"].startswith(CALCULATED_INCIDENT_CHECK_PREFIX)
    assert llm.complete.call_count == 2


def test_incident_code_prefix_does_not_consume_model_check_limit(concentrated_result):
    payload = payload_for(concentrated_result)
    reply = concentration_reply(payload)
    check = "기록을 대조하세요. " * 37
    assert len(check) <= 450
    reply["sections"][1]["next_check"] = check
    section = validate_sections(reply, payload, concentrated_result)[1]
    assert section["next_check"] == CALCULATED_INCIDENT_CHECK_PREFIX + check.strip()
    assert len(section["next_check"]) > 450
