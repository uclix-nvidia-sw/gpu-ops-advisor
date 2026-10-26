"""Diagnostic explanations must preserve calculations and the writer's inputs."""

import asyncio
from copy import deepcopy
import time
from uuid import uuid4

import pytest

from agent_common.artifacts import render
from agent_common.contracts import validate_result
from ops_agent.aggregate_report import build_result
from ops_agent.report_contract import VERSION, previous_period
from ops_agent.report_interpretation import payload_for
from ops_agent.report_queries import ReportQueries
from test_aggregate_report import DATA, fixture
from test_identity_transitions import transition_fixture, proof


def result_for(evidence, data=DATA):
    context = dict(
        data_cutoff_at=data["time_range"]["end"], incidents=[], previous_incidents=[]
    )
    claim = dict(
        job_id=str(uuid4()), kind="report", input=data, versions={"criteria": VERSION}
    )
    result = build_result(claim, context, evidence)
    validate_result(result, evidence)
    return result


def diagnostic(result):
    return result["topics"][0]["quality"]["observation_diagnostics"]


def changed_hours(period, cluster, count):
    evidence = fixture(period, cluster=cluster)
    for point in evidence[2]["snapshot"]["series"][0]["values"][:count]:
        point[1] = "2"
    return evidence


def test_shared_budget_records_later_cluster_without_changing_order_or_values():
    data = deepcopy(DATA)
    data["scope"]["clusters"].append(dict(cluster_id="cpc-2", namespaces=None))
    previous = previous_period(data)
    groups = [
        changed_hours(data["time_range"], "cpc-1", 7),
        changed_hours(previous, "cpc-1", 9),
        changed_hours(data["time_range"], "cpc-2", 7),
        fixture(previous, cluster="cpc-2"),
    ]
    evidence = [e for group in groups for e in group]
    baseline = result_for(deepcopy(evidence), data)
    calls = []

    async def query(args):
        calls.append(args)
        return {"data": {"result": []}}

    collector = ReportQueries({"query_prometheus": query}, data, time.monotonic() + 900)
    for group in groups:
        cluster = group[0]["scope"]["clusters"][0]
        evidence.extend(
            asyncio.run(
                collector.check_transitions(
                    cluster, group[0]["time_range"], "mimir", group
                )
            )
        )
    assert len(calls) == collector.transition_calls == 32
    assert all('cluster_id="cpc-1"' in call["expr"] for call in calls)
    assert [call["endTime"] for call in calls[::2]] == [
        e["input"]["queries"][0]["endTime"]
        for e in evidence
        if e["query_id"] == "gpu_identity_transitions"
    ]
    result = result_for(evidence, data)
    without_audit = deepcopy(evidence)
    for e in without_audit:
        e["quality"].pop("transition_verification", None)
    unannotated = result_for(without_audit, data)
    assert payload_for(result) == payload_for(unannotated)
    assert render(result)["csv"] == render(unannotated)["csv"]
    calculated_topics = deepcopy(result["topics"])
    old_topics = deepcopy(unannotated["topics"])
    for topic in calculated_topics + old_topics:
        topic["quality"].pop("observation_diagnostics", None)
    assert calculated_topics == old_topics
    assert result["result_status"] == baseline["result_status"] == "partial"
    for before, after in zip(baseline["topics"], result["topics"]):
        # Added evidence IDs are expected; calculations and interpretation are unchanged.
        for key in ("status", "missing_inputs"):
            assert before[key] == after[key]
    cpc2 = next(r for r in diagnostic(result)["rows"] if r["cluster_id"] == "cpc-2")
    assert (cpc2["valid_hours"], cpc2["excluded_hours"]) == (17, 7)
    assert (
        next(
            r
            for r in cpc2["reasons"]
            if r["code"] == "transition_query_budget_exhausted"
        )["hours"]
        == 7
    )
    audit = next(
        r
        for r in diagnostic(result)["collection"]
        if r["cluster_id"] == "cpc-2" and r["period_role"] == "current"
    )
    assert (
        audit["checked_batches"],
        audit["skipped_hours"],
        audit["skipped_gpu_hours"],
    ) == (0, 7, 7)
    # No fake query evidence is created for the skipped cluster.
    assert all(
        e["cluster_id"] == "cpc-1"
        for e in evidence
        if e["query_id"] == "gpu_identity_transitions"
    )


@pytest.mark.parametrize(
    "case", ["deadline", "base", "query", "overlap", "pod", "proof"]
)
def test_failure_stages_are_distinct_and_do_not_promote_hours(case):
    evidence, gpu, pods, at = transition_fixture()
    if case == "base":
        evidence[1]["tool_status"] = "unavailable"
    if case == "overlap":
        gpu[1]["values"][0][0] = gpu[0]["values"][-1][0]
    if case == "pod":
        pods[0]["metric"]["uid"] = ""
    calls = []

    async def query(args):
        calls.append(args)
        if case == "query":
            raise RuntimeError("secret-upstream-detail")
        return {"data": {"result": pods if "kube_pod_info" in args["expr"] else gpu}}

    collector = ReportQueries(
        {"query_prometheus": query},
        DATA,
        time.monotonic() + (20 if case == "deadline" else 900),
    )
    checks = asyncio.run(
        collector.check_transitions(
            DATA["scope"]["clusters"][0], DATA["time_range"], "mimir", evidence
        )
    )
    if case == "proof":
        checks[0]["snapshot"]["checks"][0]["values"]["activity_sum"] += 1
    result = result_for(evidence + checks + fixture(previous_period(DATA)))
    row = next(r for r in result["topics"][0]["rows"] if r["namespace"])
    assert row["valid_hours"] == (0 if case == "base" else 23)
    code = dict(
        deadline="transition_deadline_exhausted",
        base="base_query_unavailable",
        query="transition_verification_unavailable",
        overlap="gpu_interval_unverified",
        pod="pod_interval_unverified",
        proof="transition_aggregate_mismatch",
    )[case]
    assert code in str(diagnostic(result))
    if case == "base":
        collection = diagnostic(result)["collection"][0]
        assert collection["skipped_hours"] is None
        assert collection["skipped_gpu_hours"] is None
    assert "secret-upstream-detail" not in str(evidence + checks)
    assert len(calls) == (
        0 if case in {"deadline", "base"} else 1 if case == "query" else 2
    )


def test_diagnostics_are_output_only_and_old_evidence_does_not_invent_skip_cause():
    evidence, _, _, _ = transition_fixture()
    result = result_for(evidence + fixture(previous_period(DATA)))
    assert "transition_query_budget_exhausted" not in str(diagnostic(result))
    payload = payload_for(result)
    baseline = deepcopy(result)
    del baseline["topics"][0]["quality"]["observation_diagnostics"]
    assert payload == payload_for(baseline)
    assert render(result)["csv"] == render(baseline)["csv"]
    result["limitations"].extend(diagnostic(result)["messages"])
    html = render(result)["html"].decode()
    assert "Namespace 미표기" in html and "미할당 여부는 미확인" in html
    assert render(result)["csv"] == render(baseline)["csv"]


@pytest.mark.parametrize(
    "count,status", [(0, "ready"), (7, "partial"), (24, "blocked")]
)
def test_quality_boundaries_and_previous_period_explanations(count, status):
    result = result_for(
        changed_hours(DATA["time_range"], "cpc-1", count)
        + fixture(previous_period(DATA))
    )
    assert result["topics"][0]["status"] == status
    assert result["result_status"] == ("ready" if status == "ready" else "partial")
    if not count:
        assert diagnostic(result)["messages"] == []
    else:
        assert diagnostic(result)["rows"][0]["excluded_hours"] == count
    previous = result_for(fixture() + changed_hours(previous_period(DATA), "cpc-1", 7))
    assert diagnostic(previous)["rows"][0]["period_role"] == "previous"
    assert "이전 기간" in diagnostic(previous)["messages"][0]


def test_verified_flag_does_not_hide_another_rejected_identity_in_same_row_hour():
    evidence, gpu, pods, at = transition_fixture()
    evidence.append(proof(evidence, gpu, pods, at))
    extra = deepcopy(evidence[0]["snapshot"]["series"][:4])
    for series in extra:
        series["metric"]["UUID"] = "gpu-2"
        series["metric"].pop("pod")
        series["values"] = series["values"][:1]
    evidence[0]["snapshot"]["series"].extend(extra)
    result = result_for(evidence + fixture(previous_period(DATA)))
    row = next(r for r in result["topics"][0]["rows"] if r["namespace"])
    assert row["hours"][0]["verified_connection_change"] is True
    assert row["hours"][0]["activity_percent"] is None
    assert row["valid_hours"] == 23
    assert row["sample_count"] == 23 * 240
    assert (
        next(r for r in diagnostic(result)["rows"] if r["namespace"])["excluded_hours"]
        == 1
    )


def test_multiple_gpus_in_one_skipped_hour_do_not_double_count_row_hours():
    evidence = changed_hours(DATA["time_range"], "cpc-1", 1)
    for index in (0, 2):
        copies = deepcopy(evidence[index]["snapshot"]["series"])
        for series in copies:
            series["metric"]["UUID"] = "gpu-2"
        evidence[index]["snapshot"]["series"].extend(copies)

    async def unexpected(args):
        raise AssertionError("exhausted budget must not call upstream")

    collector = ReportQueries(
        {"query_prometheus": unexpected}, DATA, time.monotonic() + 900
    )
    collector.transition_calls = 32
    assert (
        asyncio.run(
            collector.check_transitions(
                DATA["scope"]["clusters"][0], DATA["time_range"], "mimir", evidence
            )
        )
        == []
    )
    result = result_for(evidence + fixture(previous_period(DATA)))
    audit = diagnostic(result)["collection"][0]
    assert (audit["skipped_hours"], audit["skipped_gpu_hours"]) == (1, 2)
    assert audit["skipped_by_reason"] == [
        dict(code="transition_query_budget_exhausted", hours=1, gpu_hours=2)
    ]
    row = diagnostic(result)["rows"][0]
    assert row["excluded_hours"] == 1
    assert (
        next(
            r
            for r in row["reasons"]
            if r["code"] == "transition_query_budget_exhausted"
        )["hours"]
        == 1
    )


def test_absent_periods_and_all_blocked_keep_existing_status_rules():
    for evidence, missing in [
        (fixture(), "이전"),
        (fixture(previous_period(DATA)), "현재"),
    ]:
        result = result_for(evidence)
        assert any(
            f"{missing} 기간의 대응 관측이 없어" in m
            for m in diagnostic(result)["messages"]
        )
    data = {**DATA, "topic_ids": ["namespace_usage"]}
    result = result_for(changed_hours(DATA["time_range"], "cpc-1", 24), data)
    assert result["result_status"] == "blocked"
