"""Current-period priority and bounded, fair transition collection."""

import asyncio
from collections import Counter
from copy import deepcopy
import time
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from agent_common.contracts import timestamp
from agent_common.runtime import attempt_context
from ops_agent.aggregate_report import run
from ops_agent.report_contract import VERSION, previous_period
from ops_agent.report_queries import ReportQueries, hourly_queries
from test_aggregate_report import DATA
from test_report_diagnostics import changed_hours, diagnostic, result_for


def group(cluster, period, hours, gpus=1):
    evidence = changed_hours(period, cluster, hours)
    for index in (0, 2):
        original = deepcopy(evidence[index]["snapshot"]["series"])
        for gpu in range(1, gpus):
            extra = deepcopy(original)
            for series in extra:
                series["metric"]["UUID"] = f"gpu-{gpu + 1}"
            evidence[index]["snapshot"]["series"].extend(extra)
    return evidence[0]["scope"]["clusters"][0], period, "mimir", evidence


async def test_gpu_batches_alternate_even_within_the_same_hour():
    groups = [
        group("cpc-1", DATA["time_range"], 1, 17),
        group("cpc-2", DATA["time_range"], 1),
    ]
    query = AsyncMock(return_value={"data": {"result": []}})
    collector = ReportQueries({"query_prometheus": query}, DATA, time.monotonic() + 900)
    evidence = await collector.check_transitions(groups)
    assert [(e["cluster_id"], e["quality"]["gpu_count"]) for e in evidence] == [
        ("cpc-1", 16),
        ("cpc-2", 1),
        ("cpc-1", 1),
    ]
    assert query.await_count == 6


async def test_uneven_clusters_do_not_block_other_current_periods():
    previous = previous_period(DATA)
    groups = [
        group(c, p, n)
        for c, n in [("cpc-1", 20), ("cpc-2", 1), ("cpc-3", 7)]
        for p in (previous, DATA["time_range"])
    ]
    query = AsyncMock(return_value={"data": {"result": []}})
    collector = ReportQueries({"query_prometheus": query}, DATA, time.monotonic() + 900)
    evidence = await collector.check_transitions(groups)
    assert query.await_count == collector.transition_calls == 32
    assert Counter(e["cluster_id"] for e in evidence) == {
        "cpc-1": 8,
        "cpc-2": 1,
        "cpc-3": 7,
    }
    assert all(e["time_range"] == DATA["time_range"] for e in evidence)
    for _, period, _, base in groups:
        audit = base[0]["quality"]["transition_verification"]
        if period == previous:
            assert all(
                e["reason"] == "transition_query_budget_exhausted" for e in audit
            )


@pytest.mark.parametrize("unavailable", [True, False])
async def test_unavailable_or_empty_first_cluster_does_not_block_next(unavailable):
    first = group("cpc-1", DATA["time_range"], 1 if unavailable else 0)
    if unavailable:
        first[3][1]["tool_status"] = "unavailable"
    query = AsyncMock(return_value={"data": {"result": []}})
    collector = ReportQueries({"query_prometheus": query}, DATA, time.monotonic() + 900)
    evidence = await collector.check_transitions(
        [first, group("cpc-2", DATA["time_range"], 1)]
    )
    assert [e["cluster_id"] for e in evidence] == ["cpc-2"]
    assert query.await_count == 2
    assert first[3][0]["quality"].get("transition_skip_reason") == (
        "base_query_unavailable" if unavailable else None
    )


async def test_expiring_deadline_applies_to_remaining_clusters_and_periods():
    calls = []

    async def query(args):
        calls.append(args)
        if len(calls) == 2:
            collector.transition_deadline = time.monotonic() - 1
        return {"data": {"result": []}}

    groups = [
        group(c, p, 2)
        for c in ("cpc-1", "cpc-2")
        for p in (DATA["time_range"], previous_period(DATA))
    ]
    collector = ReportQueries({"query_prometheus": query}, DATA, time.monotonic() + 900)
    evidence = await collector.check_transitions(groups)
    assert len(calls) == 2 and len(evidence) == 1
    skipped = [
        e
        for *_, base in groups
        for e in base[0]["quality"]["transition_verification"]
        if e["status"] == "not_checked"
    ]
    assert len(skipped) == 7
    assert {e["reason"] for e in skipped} == {"transition_deadline_exhausted"}


async def test_cancellation_stops_before_another_cluster_query():
    query = AsyncMock(side_effect=asyncio.CancelledError)
    collector = ReportQueries({"query_prometheus": query}, DATA, time.monotonic() + 900)
    with pytest.raises(asyncio.CancelledError):
        await collector.check_transitions(
            [group(c, DATA["time_range"], 2) for c in ("cpc-1", "cpc-2")]
        )
    assert query.await_count == 1


@pytest.mark.parametrize("datasources", [1, 2])
@pytest.mark.parametrize("clusters", [1, 2, 3, 4])
async def test_cluster_supplements_and_collectors_keep_reserved_budget(
    datasources, clusters
):
    data = deepcopy(DATA)
    data["scope"]["clusters"] = [
        dict(cluster_id=f"cpc-{i}", namespaces=None) for i in range(1, clusters + 1)
    ]
    transition_calls = 30 if (clusters, datasources) == (4, 2) else 32
    expected_calls = (
        1 + 2 * datasources + 10 * clusters + transition_calls + min(4, 2 * clusters)
    )
    calls = []

    async def list_datasources(args):
        calls.append("discovery")
        return {
            "datasources": [
                dict(uid=f"mimir-{i}", type="prometheus") for i in range(datasources)
            ],
            "hasMore": False,
        }

    async def labels(args):
        calls.append("discovery")
        return (
            [c["cluster_id"] for c in data["scope"]["clusters"]]
            if args["datasourceUid"] == "mimir-0"
            else ["other"]
        )

    async def query(args):
        calls.append(args)
        if args["queryType"] == "range":
            for cluster in data["scope"]["clusters"]:
                for index, expr in enumerate(hourly_queries(cluster).values()):
                    if args["expr"] != expr:
                        continue
                    period = (
                        data["time_range"]
                        if timestamp(args["endTime"])
                        == timestamp(data["time_range"]["end"])
                        else previous_period(data)
                    )
                    rows = changed_hours(period, cluster["cluster_id"], 24)[index][
                        "snapshot"
                    ]["series"]
                    if index == 1:
                        # Four collector reads exercise the existing global cap too.
                        extra = deepcopy(rows[0])
                        extra["metric"]["instance"] = "second-collector"
                        extra["values"] = extra["values"][:1]
                        rows.append(extra)
                    return {"data": {"result": rows}}
        return {"data": {"result": []}}

    token = attempt_context.set(
        dict(
            claim=dict(
                job_id=str(uuid4()),
                kind="report",
                input=data,
                versions={"criteria": VERSION},
            ),
            context=dict(
                data_cutoff_at=data["time_range"]["end"],
                incidents=[],
                previous_incidents=[],
            ),
            deadline=time.monotonic() + 900,
            llm=AsyncMock(configured=False, usage={}),
        )
    )
    try:
        output = await run(
            {
                "query_prometheus": query,
                "list_datasources": list_datasources,
                "list_prometheus_label_values": labels,
            }
        )
    finally:
        attempt_context.reset(token)
    assert len(calls) == min(expected_calls, 80)
    assert output["result"]["quality"]["query_count"] == expected_calls
    supplemental = [
        e
        for e in output["evidence"]
        if e["query_id"]
        in {
            "hourly_gpu_memory",
            "hourly_gpu_workload",
            "hourly_gpu_jobs",
            "hourly_gpu_workload_context",
        }
    ]
    assert len(supplemental) == 4 * clusters and all(
        e["tool_status"] == "ok" for e in supplemental
    )
    transitions = [
        e for e in output["evidence"] if e["query_id"] == "gpu_identity_transitions"
    ]
    assert len(transitions) == transition_calls // 2
    counts = Counter(e["cluster_id"] for e in transitions)
    assert max(counts.values()) - min(counts.values()) <= 1
    reasons = {
        a.get("reason")
        for e in output["evidence"]
        for a in e["quality"].get("transition_verification", [])
    }
    assert ("transition_query_budget_reserved" in reasons) == (
        (clusters, datasources) == (4, 2)
    )
    audits = [
        a
        for e in output["evidence"]
        for a in e["quality"].get("collector_verification", [])
    ]
    assert len(audits) == min(4, 2 * clusters)
    assert all(a["reason"] is None for a in audits)


def test_legacy_pod_rejection_audit_remains_readable():
    _, period, _, evidence = group("cpc-1", DATA["time_range"], 1)
    labels = evidence[0]["snapshot"]["series"][0]["metric"]
    from ops_agent.report_contract import iso

    at = evidence[0]["snapshot"]["series"][0]["values"][0][0]
    evidence[0]["quality"]["transition_verification"] = [
        dict(
            hour_end=iso(at),
            gpu_ids=[labels["UUID"]],
            status="checked",
            reason=None,
            rejected=[
                dict(
                    gpu_id=labels["UUID"],
                    namespace=labels["namespace"],
                    pod=labels["pod"],
                    reason="pod_interval_unverified",
                )
            ],
        )
    ]
    result = result_for(evidence)
    assert any(
        "Pod UID·노드·표본·연결 구간 조건을 확인하지 못함" in m
        for m in diagnostic(result)["messages"]
    )


@pytest.mark.parametrize(
    "used,reserved,expected,reason",
    [
        (73, 4, 2, "transition_query_budget_reserved"),
        (74, 4, 2, "transition_query_budget_reserved"),
        (75, 4, 0, "transition_query_budget_reserved"),
        (79, 4, 0, "report_query_limit_exceeded"),
        (20, 8, 32, "transition_query_budget_exhausted"),
    ],
)
async def test_reservation_skips_whole_batches_without_spending_calls(
    used, reserved, expected, reason
):
    group_data = group("cpc-1", DATA["time_range"], 24)
    query = AsyncMock(return_value={"data": {"result": []}})
    collector = ReportQueries({"query_prometheus": query}, DATA, time.monotonic() + 900)
    collector.calls = used
    await collector.check_transitions([group_data], reserved_calls=reserved)
    assert query.await_count == collector.transition_calls == expected
    assert collector.calls == used + expected
    audit = group_data[3][0]["quality"]["transition_verification"]
    skipped = [a for a in audit if a["status"] == "not_checked"]
    assert skipped and {a["reason"] for a in skipped} == {reason}


async def test_failed_transition_queries_do_not_spend_reserved_calls():
    group_data = group("cpc-1", DATA["time_range"], 24)
    query = AsyncMock(side_effect=ValueError("fixture query failure"))
    collector = ReportQueries({"query_prometheus": query}, DATA, time.monotonic() + 900)
    collector.calls = 72
    await collector.check_transitions([group_data], reserved_calls=4)
    # Each failure spends only the first call of a pair. One spare call cannot start a pair.
    assert query.await_count == 3
    assert collector.calls == 75
    audit = group_data[3][0]["quality"]["transition_verification"]
    assert sum(a["status"] == "query_failed" for a in audit) == 3
    assert all(
        a["reason"] == "transition_query_budget_reserved"
        for a in audit
        if a["status"] == "not_checked"
    )


async def test_deadline_is_not_misreported_as_reservation():
    group_data = group("cpc-1", DATA["time_range"], 1)
    query = AsyncMock()
    collector = ReportQueries({"query_prometheus": query}, DATA, time.monotonic() + 900)
    collector.calls = 75
    collector.transition_deadline = time.monotonic() - 1
    await collector.check_transitions([group_data], reserved_calls=4)
    query.assert_not_awaited()
    assert (
        group_data[3][0]["quality"]["transition_verification"][0]["reason"]
        == "transition_deadline_exhausted"
    )
