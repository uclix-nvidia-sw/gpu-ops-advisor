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

    return {
        "topics": [
            topic("namespace_usage", 60, "percent"),
            topic("incident_summary", 0, "events"),
        ],
        "time_range": {},
        "quality": {},
        "limitations": ["알림 상태는 보고서 작성 당시 기준입니다."],
    }


def reply_for(payload):
    sections = []
    for t in payload["topics"]:
        if t.get("advice_mode"):
            from test_namespace_advice import section

            sections.append(section(t["findings"]))
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
    assert "0건" in result["narrative"][1]["observation"]
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
        s["fact_ids"] = ["incident_summary-fact"]
    if problem == "unknown_value":
        s["observation"] = "{{value:incident_summary.value}}"
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
        "{{target:incident_summary-fact}}의 사건은 {{value:incident_summary.value}}건입니다."
    )
    sections = validate_sections(reply, payload, result)
    assert sections[0]["observation"] == "60.00%입니다."
    assert sections[1]["observation"] == "선택한 보고서 범위의 사건은 0건입니다."


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
    assert fact["fact_id"] == "incident_summary-fact"
    assert fact["values"][0]["metric_id"] == "incident_summary.value"
    reply = reply_for(payload)
    reply["sections"][1]["observation"] = (
        "{{period:incident_summary.value}}의 저장 사건은 {{value:incident_summary.value}}입니다."
    )
    rendered = validate_sections(reply, payload, result)
    assert "10/13 00:00~10/14 00:00 KST" in rendered[1]["observation"]
    reply["sections"][1]["fact_ids"] = ["incident_summary.value"]
    with pytest.raises(ValueError, match="invalid_fact_reference"):
        validate_sections(reply, payload, result)


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
        data = json.loads(request.content)["messages"][1]["content"]
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
