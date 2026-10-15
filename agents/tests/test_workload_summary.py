import json
import re
from copy import deepcopy
from uuid import uuid4

import pytest
from agent_common.contracts import timestamp, validate_result
from agent_common.artifacts import render
from test_aggregate_report import DATA, fixture
from test_gpu_memory import result
from ops_agent.report_contract import previous_period
from ops_agent.report_interpretation import payload_for
from ops_agent.workload_queries import workload_queries


def evidence(query, measures, *, job=False):
    e = deepcopy(fixture()[0])
    e.update(id=str(uuid4()), query_id=query)
    labels = e["snapshot"]["series"][0]["metric"]
    labels = {k: labels[k] for k in ("cluster_id", "namespace")}
    if job:
        labels["job_name"] = "batch-a"
    at = timestamp(DATA["time_range"]["start"]) + 3600
    e["snapshot"]["series"] = [
        {"metric": {**labels, "measure": m}, "values": [[at, str(v)]]}
        for m, v in measures.items()
    ]
    return e


def states():
    return evidence(
        "hourly_gpu_workload",
        {
            f"{s}_{m}": v
            for s, p in (("pending", 2), ("unscheduled", 1), ("running", 3))
            for m, v in (("peak", p), ("samples", 240))
        },
    )


def jobs():
    start = timestamp(DATA["time_range"]["start"])
    return evidence(
        "hourly_gpu_jobs",
        {
            f"{f}_{m}": start + v
            for f, v in (("created", 10), ("started", 30), ("completed", 330))
            for m in ("min", "max")
        },
        job=True,
    )


def build(*extra):
    ev = fixture() + fixture(previous_period(DATA)) + list(extra)
    return result(ev), ev


def test_supplement_preserves_activity_memory_and_references():
    base = fixture() + fixture(previous_period(DATA))
    before = result(base)
    ev = base + [states(), jobs()]
    after = result(ev)
    a, b = before["topics"][0], after["topics"][0]
    assert a["rows"] == b["rows"]
    assert a["metrics"] == b["metrics"][: len(a["metrics"])]
    assert a["status"] == b["status"]
    assert before["topics"][1] == after["topics"][1]
    row = b["workloads"][0]
    assert (row["pending_peak"], row["unscheduled_peak"], row["running_peak"]) == (
        2,
        1,
        3,
    )
    assert row["completed_observed"] == 1
    assert row["mean_elapsed_seconds"] == 300
    validate_result(after, ev)
    assert b"workload_completed_observed" in render(after)["csv"]
    assert any(
        f["fact_id"].startswith("namespace-workload")
        for f in payload_for(after)["topics"][0]["findings"]
    )


@pytest.mark.parametrize(
    "problem",
    ["empty", "failed", "duplicate", "nonfinite", "scope", "fractional", "overflow"],
)
def test_missing_or_invalid_states_do_not_become_zero(problem):
    e = states()
    if problem == "empty":
        e["snapshot"]["series"] = []
    elif problem == "failed":
        e["tool_status"] = "unavailable"
    elif problem == "duplicate":
        e["snapshot"]["series"] *= 2
    else:
        for s in e["snapshot"]["series"]:
            if problem == "scope":
                s["metric"]["namespace"] = "outside"
            elif problem == "nonfinite":
                s["values"][0][1] = "NaN"
            elif problem == "fractional":
                s["values"][0][1] = "1.5"
            elif problem == "overflow":
                s["values"][0][1] = (
                    "241" if s["metric"]["measure"].endswith("samples") else "2"
                )
    out, _ = build(e)
    rows = out["topics"][0]["workloads"]
    row = next(
        r
        for r in rows
        if r["namespace"]
        == fixture()[0]["snapshot"]["series"][0]["metric"]["namespace"]
    )
    assert row["pending_peak"] is None
    assert row["completed_observed"] is None


@pytest.mark.parametrize(
    "problem",
    [
        "duplicate",
        "recreated",
        "timestamp_change",
        "missing_start",
        "outside",
        "future",
    ],
)
def test_ambiguous_job_not_counted(problem):
    e = jobs()
    series = e["snapshot"]["series"]
    if problem == "duplicate":
        series.extend(deepcopy(series))
    elif problem == "missing_start":
        e["snapshot"]["series"] = [
            s for s in series if not s["metric"]["measure"].startswith("started")
        ]
    else:
        for s in series:
            name = s["metric"]["measure"]
            if problem == "recreated":
                at, v = s["values"][0]
                s["values"].append([at + 3600, str(float(v) + 3600)])
            elif problem == "timestamp_change" and name == "created_max":
                s["values"][0][1] = str(float(s["values"][0][1]) + 1)
            elif problem == "outside":
                s["values"][0][1] = str(float(s["values"][0][1]) - 86400)
            elif problem == "future" and name.startswith("completed"):
                s["values"][0][1] = str(s["values"][0][0] + 1)
    out, _ = build(e)
    assert out["topics"][0]["workloads"][0]["completed_observed"] is None


def test_completed_job_seen_in_several_hours_counted_once():
    e = jobs()
    for s in e["snapshot"]["series"]:
        at, v = s["values"][0]
        s["values"].append([at + 3600, v])
    out, _ = build(e)
    assert out["topics"][0]["workloads"][0]["completed_observed"] == 1


def test_queries_are_scoped_hourly_and_require_gpu_owner():
    q = workload_queries({"cluster_id": "cpc-2", "namespaces": ["team-a"]})
    assert len(q) == 2
    assert all("namespace=~" + json.dumps(re.escape("team-a")) in v for v in q.values())
    assert all(
        'cluster_id="cpc-2"' in v and "[1h:15s] offset 1ms" in v for v in q.values()
    )
    assert 'condition="false"' in q["hourly_gpu_workload"]
    assert 'owner_kind="Job"' in q["hourly_gpu_jobs"]
    assert 'resource="nvidia_com_gpu"' in q["hourly_gpu_jobs"]


def test_incident_node_facts_have_specific_counts_without_claiming_gpu_recurrence():
    from ops_agent.aggregate_report import build_result
    from ops_agent.report_contract import VERSION
    from ops_agent.report_interpretation import validate_sections

    events = [
        {
            "id": str(uuid4()),
            "cluster_id": "cpc-1",
            "target": {"node": node},
            "symptom": "XID 79",
            "alarm_status": state,
            "occurred_at": DATA["time_range"]["start"],
        }
        for node, state in (
            ("node-a", "firing"),
            ("node-a", "resolved"),
            ("node-b", "resolved"),
        )
    ]
    context = {
        "data_cutoff_at": DATA["time_range"]["end"],
        "incidents": events,
        "previous_incidents": [],
    }
    claim = {
        "job_id": str(uuid4()),
        "kind": "report",
        "input": {**DATA, "topic_ids": ["incident_summary"]},
        "versions": {"criteria": VERSION},
    }
    report = build_result(claim, context, [])
    topic = report["topics"][0]
    assert topic["summary"]["count"] == 3
    assert topic["summary"]["unclassified_count"] == 3
    facts = payload_for(report)["topics"][0]["findings"]
    assert facts[0]["target"] == {
        "cluster_id": "cpc-1",
        "node": "node-a",
        "alert_type": "XID 79",
    }
    assert [v["value"] for v in facts[0]["values"]] == [2, 1]
    f = facts[0]
    fid = f["fact_id"]
    mid = f["values"][0]["metric_id"]
    sections = {
        "sections": [
            {
                "topic_id": "incident_summary",
                "fact_ids": [fid],
                "observation": "{{target:"
                + fid
                + "}}에서 {{value:"
                + mid
                + "}}의 알림이 확인됐습니다.",
                "meaning": "같은 장비의 반복 장애 여부는 확인이 필요합니다.",
                "next_check": "{{target:"
                + fid
                + "}}의 기존 조사와 점검 기록을 대조하세요.",
            }
        ]
    }
    narrative = validate_sections(sections, payload_for(report), report)
    assert "cpc-1 / node-a / XID 79" in narrative[0]["next_check"]


@pytest.mark.parametrize("bad", ["NaN", "-1", "not-a-number"])
def test_invalid_duplicate_state_cannot_be_hidden_by_valid_sample(bad):
    e = states()
    duplicate = deepcopy(e["snapshot"]["series"][0])
    duplicate["values"][0][1] = bad
    e["snapshot"]["series"].append(duplicate)
    out, _ = build(e)
    assert out["topics"][0]["workloads"][0]["pending_peak"] is None


def test_job_timestamps_from_different_sources_are_not_joined():
    e = jobs()
    for s in e["snapshot"]["series"]:
        s["metric"]["instance"] = (
            "exporter-a"
            if s["metric"]["measure"].startswith("created")
            else "exporter-b"
        )
    out, _ = build(e)
    assert out["topics"][0]["workloads"][0]["completed_observed"] is None


def test_invalid_workload_hours_are_unavailable():
    e = states()
    e["snapshot"]["series"] *= 2
    out, _ = build(e)
    assert out["topics"][0]["workloads"][0]["status"] == "unavailable"


@pytest.mark.parametrize("days", [1, 7])
def test_period_boundary_and_long_running_completion(days):
    from ops_agent.workload_summary import enrich_workloads
    from ops_agent.report_contract import iso

    data = deepcopy(DATA)
    start = timestamp(data["time_range"]["start"])
    end = start + days * 86400
    data["time_range"]["end"] = iso(end)
    e = jobs()
    e["time_range"] = data["time_range"]
    for s in e["snapshot"]["series"]:
        value = (
            start - 300 if s["metric"]["measure"].startswith("created") else start - 200
        )
        if s["metric"]["measure"].startswith("completed"):
            value = start
        s["values"] = [[start + 3600, str(value)]]
    topic = {"rows": [], "metrics": [], "findings": [], "evidence_refs": []}
    enrich_workloads(topic, [e], data)
    row = topic["workloads"][0]
    assert row["completed_observed"] == 1
    assert row["mean_elapsed_seconds"] == 200
    assert all(m["period"] == data["time_range"] for m in topic["metrics"])
    for s in e["snapshot"]["series"]:
        if s["metric"]["measure"].startswith("completed"):
            s["values"] = [[end, str(end)]]
        else:
            s["values"][0][0] = end
    topic = {"rows": [], "metrics": [], "findings": [], "evidence_refs": []}
    enrich_workloads(topic, [e], data)
    assert topic["workloads"][0]["completed_observed"] is None


def test_waiting_only_namespace_and_cluster_are_not_lost_or_duplicated_per_model():
    from ops_agent.workload_summary import enrich_workloads

    data = deepcopy(DATA)
    data["scope"]["clusters"].append({"cluster_id": "cpc-2", "namespaces": None})
    e1, e2 = states(), states()
    e2["cluster_id"] = "cpc-2"
    e2["scope"]["clusters"][0]["cluster_id"] = "cpc-2"
    for s in e2["snapshot"]["series"]:
        s["metric"]["cluster_id"] = "cpc-2"
    topic = {"rows": [], "metrics": [], "findings": [], "evidence_refs": []}
    enrich_workloads(topic, [e1, e2], data)
    assert len(topic["workloads"]) == 2
    assert {r["cluster_id"] for r in topic["workloads"]} == {"cpc-1", "cpc-2"}
    assert all(r["pending_peak"] == 2 for r in topic["workloads"])
