"""New report contract and calculations; no production metrics are used."""

from copy import deepcopy
from uuid import uuid4

import pytest

from agent_common.contracts import timestamp, validate_input, validate_result
from ops_agent.aggregate_report import build_result
from ops_agent.namespace_summary import summarize, compare
from ops_agent.report_contract import VERSION, previous_period, validate
from ops_agent.report_queries import hourly_queries, matrix
from ops_agent.report_store import ReportSettings

DATA = {
    "scope": {"clusters": [{"cluster_id": "cpc-1", "namespaces": None}]},
    "time_range": {"start": "2026-10-11T15:00:00Z", "end": "2026-10-12T15:00:00Z"},
    "timezone": "Asia/Seoul",
    "topic_ids": ["namespace_usage", "incident_summary"],
    "group_by": ["cluster", "namespace"],
}


def fixture(
    period=None, cluster="cpc-1", namespace="test-dept-service", model="A100", value=60
):
    period = period or DATA["time_range"]
    times = list(
        range(
            int(timestamp(period["start"])) + 3600,
            int(timestamp(period["end"])) + 1,
            3600,
        )
    )
    gpu = {
        "cluster_id": cluster,
        "namespace": namespace,
        "pod": "test-pod",
        "Hostname": "test-node",
        "UUID": "gpu-1",
        "modelName": model,
    }

    def evidence(name, series):
        return {
            "id": str(uuid4()),
            "query_id": name,
            "query_version": VERSION,
            "cluster_id": cluster,
            "scope": {"clusters": [{"cluster_id": cluster, "namespaces": None}]},
            "time_range": period,
            "tool_status": "ok",
            "quality": {},
            "input": {},
            "snapshot": {"series": series},
        }

    def series(labels, val):
        return {"metric": labels, "values": [[at, str(val)] for at in times]}

    return [
        evidence(
            "hourly_gpu_activity",
            [
                series({**gpu, "measure": k}, v)
                for k, v in {
                    "activity_sum": value * 240,
                    "sample_count": 240,
                    "minimum": value,
                    "maximum": value,
                }.items()
            ],
        ),
        evidence(
            "hourly_pod_identity",
            [
                series(
                    {
                        "cluster_id": cluster,
                        "namespace": namespace,
                        "pod": "test-pod",
                        "node": "test-node",
                        "uid": "uid-1",
                    },
                    240,
                )
            ],
        ),
        evidence(
            "hourly_gpu_identity_count",
            [
                series(
                    {
                        "cluster_id": cluster,
                        "UUID": "gpu-1",
                    },
                    1,
                )
            ],
        ),
    ]


def test_period_contract_and_profile_isolation():
    validate(DATA)
    validate_input("report", DATA)
    settings = ReportSettings("report", config_path="does-not-exist")
    assert (
        settings.profile_for_claim({"input": DATA, "versions": {"criteria": VERSION}})[
            "limits"
        ]["deadline_seconds"]
        == 900
    )
    for mutate in (
        lambda d: d["topic_ids"].append("O08"),
        lambda d: d["time_range"].update(end="2026-10-13T15:00:00Z"),
        lambda d: d.update(comparison_range=previous_period(d)),
    ):
        data = deepcopy(DATA)
        mutate(data)
        with pytest.raises(ValueError):
            validate(data)


def test_hourly_aggregation_and_previous_period():
    current, _ = summarize(fixture(value=60), DATA["time_range"])
    previous, _ = summarize(
        fixture(previous_period(DATA), value=40), previous_period(DATA)
    )
    row = compare(current, previous)[0]
    assert row["activity_percent"] == 60
    assert row["change_percentage_points"] == 20
    assert row["sample_count"] == 24 * 240
    assert row["observed_gpu_count"] == 1
    assert row["low_activity_hours"] == 0


@pytest.mark.parametrize(
    "problem",
    [
        "missing",
        "duplicate",
        "pod_changed",
        "sharing",
        "mig",
        "invalid",
        "interval",
        "query_failure",
        "label_conflict",
    ],
)
def test_unsafe_attribution_never_becomes_zero_or_comparable(problem):
    evidence = fixture()
    if problem == "missing":
        evidence[1]["snapshot"]["series"] = []
    if problem == "duplicate":
        more = deepcopy(evidence[0]["snapshot"]["series"])
        for row in more:
            row["metric"]["instance"] = "duplicate"
        evidence[0]["snapshot"]["series"] += more
    if problem == "pod_changed":
        more = deepcopy(evidence[1]["snapshot"]["series"][0])
        more["metric"]["uid"] = "uid-2"
        evidence[1]["snapshot"]["series"].append(more)
    if problem == "sharing":
        evidence[2]["snapshot"]["series"][0]["values"][0][1] = "2"
    if problem == "mig":
        for row in evidence[0]["snapshot"]["series"]:
            row["metric"]["GPU_I_ID"] = "0"
    if problem == "invalid":
        evidence[0]["snapshot"]["series"][3]["values"][0][1] = "101"
    if problem == "interval":
        evidence[0]["snapshot"]["series"][1]["values"][0][1] = "120"
    if problem == "query_failure":
        evidence[1]["tool_status"] = "unavailable"
    if problem == "label_conflict":
        for row in evidence[0]["snapshot"]["series"]:
            row["metric"]["node"] = "other-node"
    current, _ = summarize(evidence, DATA["time_range"])
    assert current[0]["hours"][0]["activity_percent"] is None
    assert current[0]["low_activity_hours"] is None
    assert compare(current, current)[0]["change_percentage_points"] is None


def test_cluster_boundary_and_real_zero():
    evidence = fixture(value=0) + fixture(cluster="cpc-2", value=80)
    current, _ = summarize(evidence, DATA["time_range"])
    assert [r["activity_percent"] for r in current] == [0, 80]
    assert current[0]["low_activity_hours"] == 24
    assert compare(current, [])[0]["change_percentage_points"] is None
    assert compare([], current)[0]["activity_percent"] is None


def test_one_unavailable_cluster_does_not_block_another():
    evidence = fixture() + fixture(cluster="cpc-2", value=80)
    evidence[1]["tool_status"] = "unavailable"
    current, errors = summarize(evidence, DATA["time_range"])
    assert current[0]["activity_percent"] is None
    assert current[1]["activity_percent"] == 80
    assert errors == ["query_unavailable"]


def test_weekly_calendar_and_low_hour_windows():
    data = deepcopy(DATA)
    data["time_range"]["end"] = "2026-10-18T15:00:00Z"
    validate(data)
    current, _ = summarize(fixture(data["time_range"], value=0), data["time_range"])
    assert current[0]["valid_hours"] == 168
    assert current[0]["low_activity_windows"] == [data["time_range"]]
    data["time_range"] = {
        "start": "2026-10-11T16:00:00Z",
        "end": "2026-10-18T16:00:00Z",
    }
    with pytest.raises(ValueError):
        validate(data)


def test_no_raw_range_or_rca_query_registry():
    queries = hourly_queries(DATA["scope"]["clusters"][0])
    assert len(queries) == 3
    assert all(":15s" not in q and "[24h]" not in q for q in queries.values())
    assert "sum_over_time" in queries["hourly_gpu_activity"]
    with pytest.raises(ValueError):
        matrix({"warnings": ["partial"], "data": []})


def test_result_and_artifacts_contract():
    from agent_common.artifacts import render

    claim = {
        "job_id": str(uuid4()),
        "kind": "report",
        "input": DATA,
        "versions": {"criteria": VERSION},
    }
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
    result = build_result(claim, context, evidence)
    validate_result(result, evidence)
    assert result["result_status"] == "ready"
    assert result["topics"][1]["summary"]["count"] == 0
    assert b"period" in render(result)["csv"]


def test_incident_count_and_repeat_are_not_webhook_counts():
    from ops_agent.incident_summary import summarize as incidents

    row = {
        "id": "a",
        "cluster_id": "cpc-1",
        "symptom": "XID 79",
        "target": {"gpu_uuid": "GPU-1"},
    }
    context = {
        "incidents": [row, row, {**row, "id": "b"}],
        "previous_incidents": [row],
        "data_cutoff_at": DATA["time_range"]["end"],
    }
    result = incidents(context)
    assert result["count"] == 2 and result["change"] == 1
    assert result["groups"][0]["count"] == 2
    context["incident_limit_exceeded"] = True
    assert incidents(context)["count"] is None
