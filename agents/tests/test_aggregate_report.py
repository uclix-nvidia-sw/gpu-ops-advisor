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


def test_previous_observation_hours_explain_comparison_without_changing_mean():
    current, _ = summarize(fixture(value=30), DATA["time_range"])
    previous = deepcopy(current)
    previous[0].update(valid_hours=12, quality_status="partial", activity_percent=20)
    row = compare(current, previous)[0]
    assert row["activity_percent"] == 30
    assert row["previous_activity_percent"] == 20
    assert row["previous_valid_hours"] == 12
    assert row["previous_expected_hours"] == 24
    assert row["change_percentage_points"] is None
    assert compare([], previous)[0]["previous_valid_hours"] == 12
    assert compare(current, [])[0]["previous_valid_hours"] == 0


def test_incident_categories_keep_cluster_code_and_unknown_device_distinct():
    from ops_agent.incident_summary import summarize as incidents

    xid = {
        "id": "x",
        "cluster_id": "cpc-1",
        "symptom": "XID 79 GPU fallen off bus",
        "target": {"node": "dgx01", "test_alarm": True},
        "alarm_status": "firing",
    }
    sxid = {
        **xid,
        "id": "s",
        "symptom": "SXID 11001 ingress invalid command",
        "target": {"node": "dgx02"},
        "alarm_status": "resolved",
    }
    other = {**xid, "id": "other", "cluster_id": "cpc-2"}
    unknown = {**xid, "id": "unknown", "symptom": None, "target": {}}
    result = incidents(
        {
            "incidents": [xid, xid, sxid, other, unknown],
            "previous_incidents": [{**xid, "id": "old"}],
            "data_cutoff_at": DATA["time_range"]["end"],
        }
    )
    categories = {(c["cluster_id"], c["name"]): c for c in result["categories"]}
    assert len(categories) == 4
    assert categories[("cpc-1", "XID 79")] == {
        "cluster_id": "cpc-1",
        "name": "XID 79",
        "count": 1,
        "previous_count": 1,
        "nodes": ["dgx01"],
        "firing_count": 1,
        "test_count": 1,
        "incident_ids": ["x"],
    }
    assert categories[("cpc-1", "SXID 11001")]["firing_count"] == 0
    assert result["count"] == result["unclassified_count"] == 4
    assert result["groups"] == []


def test_namespace_nodes_require_valid_hours_and_do_not_leak_previous_nodes():
    evidence = fixture()
    current, _ = summarize(evidence, DATA["time_range"])
    assert current[0]["nodes"] == ["test-node"]
    assert current[0]["hours"][0]["nodes"] == ["test-node"]
    assert compare([], current)[0]["nodes"] == []
    evidence[1]["tool_status"] = "unavailable"
    blocked, _ = summarize(evidence, DATA["time_range"])
    assert blocked[0]["nodes"] == []
    assert blocked[0]["activity_percent"] is None


def test_incident_category_fallbacks_and_previous_only_counts():
    from ops_agent.incident_summary import summarize as incidents

    records = [
        {"id": str(i), "cluster_id": "cpc-1", "target": target}
        for i, target in enumerate(
            (
                {"component": "disk", "node": "node-1"},
                {"alertname": "GPUAlert"},
                {},
            )
        )
    ]
    previous = {
        "id": "old",
        "cluster_id": "cpc-2",
        "symptom": "xid: 79",
        "target": {"node": "old-node"},
    }
    result = incidents(
        {
            "incidents": records,
            "previous_incidents": [previous],
            "data_cutoff_at": DATA["time_range"]["end"],
        }
    )
    categories = {c["name"]: c for c in result["categories"]}
    assert categories["디스크·파일시스템"]["nodes"] == ["node-1"]
    assert categories["GPUAlert"]["count"] == 1
    assert categories["장애 종류 미확인"]["count"] == 1
    assert categories["XID 79"]["count"] == 0
    assert categories["XID 79"]["previous_count"] == 1
    assert categories["XID 79"]["nodes"] == []
    assert result["count"] == 3 and result["groups"] == []


def concentration_records():
    return [
        {
            "id": f"event-{i}",
            "cluster_id": "cpc-1",
            "symptom": "XID 79"
            if i < 8
            else "XID 13"
            if i == 8
            else "SXID 11001"
            if i == 9
            else "disk",
            "target": {
                "node": "dgx01" if i < 5 or i == 8 else "dgx02",
                "component": "disk" if i == 10 else "gpu",
            },
            "occurred_at": DATA["time_range"]["start"],
            "alarm_status": "firing" if i == 0 else "resolved",
            "result_id": f"result-{i}" if i != 8 else None,
        }
        for i in range(11)
    ]


def concentration_report(records=None, previous=None, period=None):
    data = {
        **DATA,
        "time_range": period or DATA["time_range"],
        "topic_ids": ["incident_summary"],
    }
    context = {
        "data_cutoff_at": data["time_range"]["end"],
        "incidents": concentration_records() if records is None else records,
        "previous_incidents": previous or [],
    }
    return build_result(
        {
            "job_id": str(uuid4()),
            "kind": "report",
            "input": data,
            "versions": {"criteria": VERSION},
        },
        context,
        [{"id": str(uuid4()), "query_id": "report_incident_snapshot"}],
    )


def test_incident_concentration_counts_shares_targets_and_periods():
    report = concentration_report()
    validate_result(report, [{"id": ref} for ref in report["evidence_refs"]])
    topic = report["topics"][0]
    metrics = {m["id"]: m for m in topic["metrics"]}
    top_type, top_node = topic["findings"][1:3]
    assert [f["id"] for f in topic["findings"][:3]] == [
        "incident-period-summary",
        "incident-top-type-cpc-1",
        "incident-top-node-cpc-1",
    ]
    for fact, target, values, names in (
        (
            top_type,
            {"cluster_id": "cpc-1", "alert_type": "XID 79"},
            [8, 72.7, 0, 11, 0],
            [
                "top_type_count",
                "top_type_share",
                "top_type_previous_count",
                "top_type_cluster_count",
                "top_type_cluster_previous_count",
            ],
        ),
        (
            top_node,
            {"cluster_id": "cpc-1", "node": "dgx01"},
            [6, 54.5, 1],
            ["top_node_count", "top_node_share", "top_node_firing"],
        ),
    ):
        assert fact["target"] == target
        assert fact["evidence_refs"] == topic["evidence_refs"]
        assert len(fact["value_refs"]) == len(names)
        for mid, name, value in zip(fact["value_refs"], names, values):
            metric = metrics[mid]
            assert mid.startswith(f"incident_summary.{name}.")
            expected_target = (
                {"cluster_id": target["cluster_id"]}
                if name.startswith("top_type_cluster_")
                else target
            )
            assert metric["target"] == expected_target and metric["value"] == value
            assert metric["unit"] == ("percent" if name.endswith("share") else "events")
            assert metric["period"] == (
                previous_period(DATA)
                if name.endswith("previous_count")
                else DATA["time_range"]
            )
    assert "XID 79 5건, XID 13 1건" in top_node["text"]
    assert (
        "이 클러스터 저장 사건 11건(이전 기간 0건) 중 8건으로 72.7%" in top_type["text"]
    )
    assert "발생 노드 dgx01, dgx02" in top_type["text"]
    second = topic["findings"][3]
    assert second["id"] == "incident-second-node-cpc-1"
    assert second["target"] == {"cluster_id": "cpc-1", "node": "dgx02"}
    assert [metrics[mid]["value"] for mid in second["value_refs"]] == [5, 45.5]
    assert all(f["id"].startswith("incident-node-") for f in topic["findings"][4:])


@pytest.mark.parametrize("count", [0, 1])
def test_incident_concentration_requires_two_current_events(count):
    topic = concentration_report(concentration_records()[:count])["topics"][0]
    assert not any(f["id"].startswith("incident-top-") for f in topic["findings"])


def test_incident_concentration_orders_clusters_by_current_count():
    records = concentration_records()
    other = [
        {**r, "id": "other-" + r["id"], "cluster_id": "cpc-2"} for r in records[:4]
    ]
    previous = other[:2] + [{**records[0], "symptom": "XID 31"}]
    topic = concentration_report(other + records, previous)["topics"][0]
    assert [
        f["id"] for f in topic["findings"] if f["id"].startswith("incident-top-")
    ] == [
        "incident-top-type-cpc-1",
        "incident-top-node-cpc-1",
        "incident-top-type-cpc-2",
        "incident-top-node-cpc-2",
    ]
    metrics = {m["id"]: m for m in topic["metrics"]}
    top_types = [
        f for f in topic["findings"] if f["id"].startswith("incident-top-type-")
    ]
    assert [
        [metrics[mid]["value"] for mid in f["value_refs"][-2:]] for f in top_types
    ] == [[11, 1], [4, 2]]


@pytest.mark.parametrize("known_nodes", [True, False])
def test_incident_concentration_ties_unknown_nodes_and_previous_only_types(known_nodes):
    records = concentration_records()[:4]
    for i, r in enumerate(records):
        r["symptom"] = "XID 79" if i < 2 else "XID 13"
        r["target"] = (
            {"node": "dgx02" if i == 0 else "dgx01"} if known_nodes and i < 2 else {}
        )
    previous = [{**r, "id": "old-" + r["id"]} for r in records[2:]]
    previous += [{**previous[0], "id": "old-only", "symptom": "SXID 11001"}]
    topic = concentration_report(records, previous)["topics"][0]
    facts = [f for f in topic["findings"] if f["id"].startswith("incident-top-")]
    metrics = {m["id"]: m for m in topic["metrics"]}
    assert facts[0]["target"]["alert_type"] == "XID 13"
    assert [metrics[mid]["value"] for mid in facts[0]["value_refs"]] == [2, 50, 2, 4, 3]
    assert len(facts) == (2 if known_nodes else 1)
    if known_nodes:
        assert facts[1]["target"]["node"] == "dgx01"
        assert [metrics[mid]["value"] for mid in facts[1]["value_refs"]] == [1, 25, 0]


def test_second_node_requires_two_identified_nodes():
    records = concentration_records()
    for record in records:
        record["target"]["node"] = "dgx01"
    topic = concentration_report(records)["topics"][0]
    assert not any(
        f["id"].startswith("incident-second-node-") for f in topic["findings"]
    )


def test_second_node_ties_use_name_order_and_full_cluster_denominator():
    records = concentration_records()[:4]
    for record, node in zip(records, ["dgx02", "dgx01", None, None]):
        record["target"] = {"node": node} if node else {}
    topic = concentration_report(records)["topics"][0]
    metrics = {m["id"]: m for m in topic["metrics"]}
    second = next(
        f for f in topic["findings"] if f["id"].startswith("incident-second-node-")
    )
    assert second["target"] == {"cluster_id": "cpc-1", "node": "dgx02"}
    assert [metrics[mid]["value"] for mid in second["value_refs"]] == [1, 25]
    assert [metrics[mid]["unit"] for mid in second["value_refs"]] == [
        "events",
        "percent",
    ]


def test_incident_node_rca_counts_published_results_without_reading_body():
    report = concentration_report()
    topic = report["topics"][0]
    metrics = {m["id"]: m for m in topic["metrics"]}
    facts = [f for f in topic["findings"] if f["id"].startswith("incident-node-")]
    for fact in facts:
        assert [ref.split(".")[1] for ref in fact["value_refs"]] == [
            "node_alert_count",
            "node_alert_firing",
            "node_alert_rca",
        ]
        rca = metrics[fact["value_refs"][2]]
        assert rca["unit"] == "events" and rca["target"] == fact["target"]
        expected = (
            0
            if fact["target"]["alert_type"] == "XID 13"
            else metrics[fact["value_refs"][0]]["value"]
        )
        assert rca["value"] == expected
    assert metrics[facts[0]["value_refs"][2]]["value"] == 5


def test_low_volume_firing_node_survives_six_candidate_limit():
    records = []
    for group in range(8):
        for event in range(8 - group):
            records.append(
                {
                    "id": f"{group}-{event}",
                    "cluster_id": "cpc-1",
                    "symptom": f"XID {group}",
                    "target": {"node": f"node-{group}"},
                    "occurred_at": DATA["time_range"]["start"],
                    "alarm_status": "firing" if group == 7 else "resolved",
                }
            )
    topic = concentration_report(records)["topics"][0]
    facts = [f for f in topic["findings"] if f["id"].startswith("incident-node-")]
    assert len(facts) == 6
    assert facts[0]["target"]["node"] == "node-7"
