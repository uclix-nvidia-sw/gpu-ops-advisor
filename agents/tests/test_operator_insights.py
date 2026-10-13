"""Operator conclusions preserve calculations and never promote missing data to health."""

import copy

import pytest

from ops_agent import workflow
from test_binding_contract import profile
from test_namespace_usage import observations
from test_report_minimization import execute_fixture, fixture_collection
from test_report_observation import DATA, START, END, evidence, row


def usage(source):
    return workflow.calculate(
        "O08",
        dict(DATA, group_by=["namespace"], timezone="Asia/Seoul"),
        source,
        {},
        {},
        criteria_version="1.3",
    )


def category(topic, name):
    return [f for f in topic["findings"] if f.get("category") == name]


def test_low_activity_is_per_gpu_and_longest_continuous_window_not_namespace_idle():
    source = observations(
        ("a", "gpu-low", START, END, 0),
        ("a", "gpu-busy", START, END, 80),
    )
    topic = usage(source)
    checks = category(topic, "low_activity")
    assert len(checks) == 1
    finding = checks[0]
    assert "GPU 1대" in finding["text"] and "60분" in finding["text"]
    assert "12:57" in finding["text"] and "gpu-low" in finding["text"]
    assert finding["target"]["namespace"] == "a"
    assert finding["period"] == DATA["time_range"]
    assert "Namespace 전체" in finding["next_check"]
    values = {m["id"]: m for m in topic["metrics"]}
    assert all("observed_low_activity_seconds" in ref for ref in finding["value_refs"])
    assert all(
        values[ref]["target"]["gpu_uuid"] == "gpu-low" for ref in finding["value_refs"]
    )
    assert {ref for f in topic["findings"] for ref in f["value_refs"]} <= values.keys()
    assert source == observations(
        ("a", "gpu-low", START, END, 0), ("a", "gpu-busy", START, END, 80)
    )


def test_discontinuous_low_activity_does_not_become_continuous_window():
    source = observations(
        ("a", "gpu", START, START + 900, 0),
        ("a", "gpu", START + 1200, START + 2100, 0),
    )
    topic = usage(source)
    assert not category(topic, "low_activity")
    assert category(topic, "no_sustained_low_activity")
    assert "유효 관측" in category(topic, "no_sustained_low_activity")[0]["text"]


@pytest.mark.parametrize("state", ["empty", "unavailable", "busy"])
def test_missing_activity_is_never_reported_as_low_or_fully_healthy(state):
    source = observations(("a", "gpu", START, END, 70))
    if state == "unavailable":
        source["D02"][0]["tool_status"] = "unavailable"
    elif state == "empty":
        source = {}
    topic = usage(source)
    assert not category(topic, "low_activity")
    if state == "busy":
        assert category(topic, "no_sustained_low_activity")
    else:
        assert not category(topic, "no_sustained_low_activity")
        assert category(topic, "activity_gap") or category(
            topic, "insufficient_evidence"
        )


def test_only_known_node_warning_conditions_create_check_candidates():
    items = [
        row(dict(node="ready", condition="Ready", status="true"), "1"),
        row(dict(node="attention", condition="Ready", status="false"), "1"),
        row(dict(node="attention", condition="DiskPressure", status="true"), "1"),
        row(dict(node="unknown", condition="CustomFleetState", status="true"), "1"),
    ]
    e = evidence("D20", items)
    e["quality"].update(sample_type="gauge", unit="boolean")
    topic = workflow.calculate(
        "O01", DATA, {"D20": [e]}, {}, {}, criteria_version="1.3"
    )
    findings = category(topic, "node_attention")
    assert len(findings) == 1
    assert findings[0]["target"]["node"] == "attention"
    assert (
        "Ready=false" in findings[0]["text"]
        and "DiskPressure=true" in findings[0]["text"]
    )
    assert "현재 장애" in findings[0]["next_check"]
    assert not category(topic, "node_observation_scope")


def test_snapshot_temperature_never_becomes_overheat_conclusion():
    e = evidence("D04", [row(dict(gpu_uuid="gpu"), "120", START, START)])
    e["quality"].update(
        max_hold_seconds=0, complete=True, sample_type="gauge", unit="celsius"
    )
    topic = workflow.calculate(
        "O01", DATA, {"D04": [e]}, {}, {}, criteria_version="1.3"
    )
    assert category(topic, "equipment_record_limit")
    assert not category(topic, "node_attention")
    assert (
        "실제 측정 시각이 확인되지"
        in category(topic, "equipment_record_limit")[0]["text"]
    )


def test_collection_failure_and_unknown_are_not_combined_or_assigned_to_gpu():
    e = evidence(
        "D10",
        [
            dict(
                metric=dict(job="scrape", instance="one"),
                values=[[START, "1"], [START + 15, "0"]],
            )
        ],
    )
    e["quality"].update(unit="state", sample_type="gauge", max_hold_seconds=15)
    topic = workflow.calculate(
        "O11", DATA, {"D10": [e]}, {}, {}, criteria_version="1.3"
    )
    finding = category(topic, "collection_gap")[0]
    assert "수집 실패 0.25분" in finding["text"] and "미관측 59.5분" in finding["text"]
    assert finding["target"] == dict(cluster_id="cpc-1", job="scrape", instance="one")
    assert len(finding["value_refs"]) == 2
    assert "보류" in finding["next_check"]


def test_incident_links_require_exact_subject_and_record_snapshot_status():
    context = dict(
        data_cutoff_at="2026-09-18T06:00:00Z",
        incidents=[
            dict(
                id="one",
                cluster_id="cpc-1",
                occurred_at=DATA["time_range"]["start"],
                alarm_status="resolved",
                target=dict(node="node"),
            )
        ],
        rca_results=[
            dict(
                result_id="rca-one", content_hash="hash", body=dict(incident_id="one")
            ),
            dict(
                result_id="rca-other",
                content_hash="hash",
                body=dict(incident_id="other"),
            ),
        ],
        actions=[
            dict(id="action-one", body=dict(subject_type="incident", subject_id="one")),
            dict(
                id="action-other",
                body=dict(subject_type="incident", subject_id="other"),
            ),
            dict(id="action-job", body=dict(subject_type="job", subject_id="one")),
        ],
    )
    original = copy.deepcopy(context)
    topic = workflow.calculate(
        "O05",
        DATA,
        {},
        context,
        {"id": "db"},
        criteria_version="1.3",
        profile=profile(),
    )
    finding = category(topic, "incident_followup")[0]
    assert finding["rca_result_ids"] == ["rca-one"]
    assert finding["action_record_ids"] == ["action-one"]
    assert finding["status_as_of"] == context["data_cutoff_at"]
    assert finding["alarm_status"] == "resolved"
    assert finding["evidence_refs"] == ["db"]
    assert "복구 완료를 뜻하지" in finding["next_check"]
    assert context == original
    assert (
        next(m for m in topic["metrics"] if m["id"] == "O05.incident_rate")["value"]
        is None
    )


def test_insights_do_not_change_measurements_or_legacy_findings(monkeypatch):
    source = observations(("a", "gpu", START, END, 0))
    new = usage(source)
    monkeypatch.setattr(workflow, "operator_insights", lambda *args: None)
    old = usage(source)
    for key in ("metrics", "facts", "status", "missing_inputs", "evidence_refs"):
        assert new[key] == old[key]
    legacy = workflow.calculate(
        "O08",
        dict(DATA, group_by=["namespace"]),
        source,
        {},
        {},
        criteria_version="1.2",
    )
    assert legacy["findings"] == []
    assert "operator_analysis" not in legacy["quality"]


@pytest.mark.asyncio
async def test_database_incident_topic_makes_no_remote_calls_in_new_profile():
    config, metrics, snapshots = fixture_collection()
    output, calls = await execute_fixture(config, metrics, snapshots, ["O05"])
    assert calls == []
    topic = output["result"]["topics"][0]
    assert category(topic, "no_incidents")
    assert {q["query_id"] for q in topic["quality"]["omitted_queries"]} == {
        "D09",
        "D10",
        "D22",
    }
    assert workflow.query_ids("O05", "1.2", profile=config) == ("D10", "D22")
    assert workflow.query_ids("O05", "1.3") == ("D10",)


@pytest.mark.asyncio
async def test_equipment_only_omits_pod_history_without_losing_values(monkeypatch):
    config, metrics, snapshots = fixture_collection()
    after, calls = await execute_fixture(config, metrics, snapshots, ["O01"])
    assert "D06" not in {q for q, expr in calls}
    current_ids = workflow.query_ids

    def previous_ids(topic_id, criteria_version=None, **kwargs):
        queries = current_ids(topic_id, criteria_version, **kwargs)
        return (*queries, "D06") if topic_id == "O01" else queries

    monkeypatch.setattr(workflow, "query_ids", previous_ids)
    before, old_calls = await execute_fixture(config, metrics, snapshots, ["O01"])
    assert "D06" in {q for q, expr in old_calls}
    old, new = before["result"]["topics"][0], after["result"]["topics"][0]
    for a, b in zip(old["metrics"], new["metrics"]):
        assert {k: v for k, v in a.items() if k != "evidence_refs"} == {
            k: v for k, v in b.items() if k != "evidence_refs"
        }
    assert (
        old["status"] == new["status"]
        and old["missing_inputs"] == new["missing_inputs"]
    )


@pytest.mark.parametrize(
    "state,has_rca,expected_check",
    [
        ("firing", False, "조사 작업의 진행·실패"),
        ("firing", True, "공개 RCA의 확인 조건"),
        ("resolved", True, "정상으로 돌아왔는지 실제 상태"),
        (None, False, "최신 알람 수신·해제 기록을 먼저"),
    ],
)
def test_incident_symptom_and_next_check_match_state_and_published_result(
    state, has_rca, expected_check
):
    incident = dict(
        id="incident-id",
        cluster_id="cpc-1",
        occurred_at=DATA["time_range"]["start"],
        alarm_status=state,
        target=dict(title="GPU 오류 알람", node="node-1"),
    )
    context = dict(
        incidents=[incident],
        rca_results=[
            dict(
                result_id="result",
                content_hash="hash",
                body=dict(incident_id="incident-id" if has_rca else "other"),
            )
        ],
        actions=[],
        data_cutoff_at=DATA["time_range"]["end"],
    )
    topic = workflow.calculate(
        "O05",
        DATA,
        {},
        context,
        {"id": "db"},
        criteria_version="1.3",
        profile=profile(),
    )
    finding = category(topic, "incident_followup")[0]
    assert "접수된 증상: GPU 오류 알람" in finding["text"]
    assert "incident-id" not in finding["text"]
    assert finding["incident_id"] == "incident-id"
    assert expected_check in finding["next_check"]
    assert finding["rca_result_ids"] == (["result"] if has_rca else [])
