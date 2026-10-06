"""Report plans preserve complete periods without changing RCA collection."""

import asyncio
import copy
import json
import math
import re
import time
from datetime import datetime, timedelta, timezone

import pytest

from agent_common.contracts import timestamp
from agent_common.normalize import allocations
from agent_common.observation import Observation, series
from ops_agent.collection import collect_report, collection_plan, report_profile
from ops_agent.workflow import PLAN, calculate, query_ids


def setup(days=7):
    profile = json.load(open("agents/tests/fixtures/config-v7.json"))
    profile["queries"]["D08"].update(
        metric="gpu_ops_allocation_info", allocation_semantics="normalized_allocation"
    )
    profile["clusters"] = {
        c: {"mimir_uid": "metrics", "metric_selector": {"cluster_id": c}}
        for c in ("cpc-1", "cpc-2")
    }
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    data = dict(
        topic_ids=["O08"],
        group_by=["namespace"],
        time_range={
            "start": start.isoformat(),
            "end": (start + timedelta(days=days)).isoformat(),
        },
        scope={
            "clusters": [
                {"cluster_id": c, "namespaces": None} for c in profile["clusters"]
            ]
        },
    )
    return profile, data


def source(data, calls, *, dense=False):
    start = timestamp(data["time_range"]["start"])
    end = timestamp(data["time_range"]["end"])

    async def query(args):
        calls.append(args)
        stop = timestamp(args["endTime"])
        length = int(re.search(r"\[(\d+)s\]$", args["expr"])[1])
        if args["expr"].startswith("gpu_ops_allocation_info"):
            return {"data": []}
        labels = dict(namespace="training", pod="pod", node="node", uid="uid")
        if args["expr"].startswith("DCGM"):
            labels.update(uuid="gpu", modelName="fixture")
        step = 15 if dense else 3600
        return {
            "data": [
                {
                    "metric": labels,
                    "values": [
                        [t, "0" if "uuid" in labels else "1"]
                        for t in range(int(start), int(end) + 1, step)
                        if stop - length < t <= stop
                    ],
                }
            ]
        }

    return query


@pytest.mark.asyncio
@pytest.mark.parametrize("days", [1, 7, 31, 73 / 24])
async def test_period_collection_preserves_original_samples_and_rca_limits(days):
    profile, data = setup(days)
    before = copy.deepcopy(profile)
    calls = []
    collected, evidence, summary = await collect_report(
        {"query_prometheus": source(data, calls)},
        profile,
        data,
        time.monotonic() + 60,
        ["D01", "D02", "D08", "D06"],
        True,
    )
    assert profile == before and profile["limits"]["max_queries"] == 48
    assert summary["query_limit"] == 2048 and summary["complete"]
    expected_calls = 2 * (2 * math.ceil(days) + math.ceil(days * 12))
    assert summary["query_calls"] == len(calls) == expected_calls
    assert all(
        s["completed_seconds"] == s["requested_seconds"] for s in summary["tasks"]
    )
    assert any(s["empty_seconds"] > 0 for s in summary["tasks"])
    for call in calls:
        length = int(re.search(r"\[(\d+)s\]$", call["expr"])[1])
        cap = 7200 if call["expr"].startswith("kube_pod_info{") else 86400
        assert length <= cap + 1
        if days in (1, 7, 31):
            assert length == cap + 1
    assert all(
        task["chunk_seconds"] == (7200 if task["query_id"] == "D06" else 86400)
        for task in summary["tasks"]
    )
    expected = set(
        range(
            int(timestamp(data["time_range"]["start"])),
            int(timestamp(data["time_range"]["end"])) + 1,
            3600,
        )
    )
    for query in ("D02", "D06"):
        for r in series(collected[query]):
            assert {t for t, _ in r["samples"]} == expected
    assert {e["id"] for e in evidence} >= {e["id"] for e in collected["D02"]}
    rca = Observation({}, profile, data, time.monotonic() + 60)
    assert rca.profile["limits"]["chunk_seconds"] == 3600
    assert not rca.reuse_queries


@pytest.mark.asyncio
async def test_adaptive_split_matches_hourly_namespace_calculation():
    profile, data = setup(1)
    profile["report"]["limits"]["max_rows"] = 5000
    calls = []
    collected, _, summary = await collect_report(
        {"query_prometheus": source(data, calls, dense=True)},
        profile,
        data,
        time.monotonic() + 60,
        ["D01", "D02", "D08", "D06"],
        True,
    )
    assert summary["complete"] and any("[86401s]" not in a["expr"] for a in calls)
    legacy = Observation(
        {"query_prometheus": source(data, [], dense=True)},
        {**profile, "limits": {**profile["limits"], "max_queries": 1000}},
        data,
        time.monotonic() + 60,
        reuse_queries=True,
    )
    original = {q: await legacy.collect(q) for q in ("D01", "D02", "D08", "D06")}

    def metrics(c):
        return [
            (m["id"], m["target"], m["value"], m["unit"])
            for m in calculate("O08", data, c, {}, {}, criteria_version="1.2")[
                "metrics"
            ]
        ]

    assert metrics(original) == metrics(collected)
    assert any(m[2] == 0 for m in metrics(collected))


@pytest.mark.asyncio
async def test_reservation_prevents_first_dense_source_starving_pod_and_other_cluster():
    profile, data = setup(1)
    profile["report"]["limits"].update(max_queries=40, max_rows=3)
    calls = []
    collected, _, summary = await collect_report(
        {"query_prometheus": source(data, calls, dense=True)},
        profile,
        data,
        time.monotonic() + 60,
        ["D01", "D02", "D08", "D06"],
        True,
    )
    assert summary["query_calls"] <= 40 and not summary["complete"]
    assert all(t["query_calls"] >= 1 for t in summary["tasks"])
    assert all(t["query_calls"] <= t["reserved_calls"] for t in summary["tasks"])
    assert {e["cluster_id"] for e in collected["D06"]} == {"cpc-1", "cpc-2"}
    assert any(
        e["quality"].get("reason") == "collection_task_budget_exhausted"
        for e in collected["D01"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "days,limit,reason",
    [(7, 4, "collection_plan_budget_exceeded"), (32, 2048, "range_budget_exhausted")],
)
async def test_preflight_rejects_impossible_plans_before_any_source_call(
    days, limit, reason
):
    profile, data = setup(days)
    profile["report"]["limits"]["max_queries"] = limit
    calls = []
    _, evidence, summary = await collect_report(
        {"query_prometheus": source(data, calls)},
        profile,
        data,
        time.monotonic() + 60,
        ["D01", "D06"],
        False,
    )
    assert summary["plan_status"] == "rejected" and summary["plan_reason"] == reason
    assert not calls and not summary["complete"]
    assert all(e["quality"]["reason"] == reason for e in evidence)


@pytest.mark.asyncio
async def test_failure_deadline_comparison_and_cancellation_remain_explicit():
    profile, data = setup(1)
    data["topic_ids"] = ["O10"]
    data["comparison_range"] = {
        "start": "2026-08-01T00:00:00Z",
        "end": "2026-08-02T00:00:00Z",
    }

    async def fail(args):
        raise RuntimeError("fixture failure")

    collected, _, summary = await collect_report(
        {"query_prometheus": fail}, profile, data, time.monotonic() + 60, ["D11"], False
    )
    assert "comparison.D11" in collected
    assert not summary["complete"] and all(
        s["data_seconds"] == 0 for s in summary["tasks"]
    )
    assert collected["comparison.D11"][0]["time_range"] == data["comparison_range"]
    _, evidence, summary = await collect_report(
        {}, profile, data, time.monotonic() - 1, ["D11"], False
    )
    assert not summary["complete"] and summary["query_calls"] == 0
    assert all(
        e["quality"]["reason"] == "collection_task_deadline_exhausted" for e in evidence
    )

    async def cancel(args):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await collect_report(
            {"query_prometheus": cancel},
            profile,
            data,
            time.monotonic() + 60,
            ["D11"],
            False,
        )


def test_report_override_validation_and_legacy_fallback():
    profile, _ = setup()
    profile.pop("report")
    assert report_profile(profile)["limits"] == profile["limits"]
    profile["limits"].pop("chunk_seconds")
    assert report_profile(profile)["limits"]["chunk_seconds"] == 3600
    for overrides in (
        {"max_queries": 0},
        {"max_queries": True},
        {"deadline_seconds": 900},
    ):
        profile["report"] = {"limits": overrides}
        with pytest.raises(ValueError):
            report_profile(profile)


@pytest.mark.asyncio
@pytest.mark.parametrize("days,planned_calls", [(1, 46), (7, 322), (31, 1426)])
async def test_bounded_pod_plan_reserves_calls_and_rejects_lower_custom_budgets(
    days, planned_calls
):
    profile, data = setup(days)
    data["topic_ids"] = list(PLAN)
    order = sorted({q for topic in PLAN for q in query_ids(topic, "1.2")})
    tasks, reason = collection_plan(report_profile(profile), data, order)
    assert reason is None
    assert sum(task["planned_calls"] for task in tasks) == planned_calls
    assert all(
        task["planned_calls"] == days * (12 if task["query_id"] == "D06" else 1)
        for task in tasks
    )
    profile["report"]["limits"]["max_queries"] = planned_calls - 1
    calls = []
    _, evidence, summary = await collect_report(
        {"query_prometheus": source(data, calls)},
        profile,
        data,
        time.monotonic() + 60,
        order,
        False,
    )
    assert not calls and summary["query_calls"] == 0
    assert summary["planned_calls"] == planned_calls
    assert summary["plan_reason"] == "collection_plan_budget_exceeded"
    assert not summary["complete"]
    assert all(
        e["quality"]["reason"] == "collection_plan_budget_exceeded" for e in evidence
    )


@pytest.mark.asyncio
async def test_query_window_cap_never_enlarges_global_window_or_changes_rca():
    profile, data = setup(1)
    before = copy.deepcopy(profile)
    report_calls, rca_calls = [], []
    profile["report"]["limits"]["chunk_seconds"] = 3600
    _, _, summary = await collect_report(
        {"query_prometheus": source(data, report_calls)},
        profile,
        data,
        time.monotonic() + 60,
        ["D06"],
        False,
    )
    assert summary["planned_calls"] == summary["query_calls"] == len(report_calls) == 48
    assert all(task["chunk_seconds"] == 3600 for task in summary["tasks"])
    assert all("[3601s]" in call["expr"] for call in report_calls)
    rca = Observation(
        {"query_prometheus": source(data, rca_calls)},
        before,
        data,
        time.monotonic() + 60,
    )
    await rca.collect("D06")
    assert rca.calls == len(rca_calls) == 48
    assert all("[3601s]" in call["expr"] for call in rca_calls)
    assert before["limits"] == profile["limits"]


def test_query_window_override_validation_and_legacy_fallback():
    profile, data = setup(1)
    for invalid in (None, [], {"D06": 0}, {"D06": True}, {"D06": 1.5}, {"D99": 7200}):
        profile["report"]["query_chunk_seconds"] = invalid
        with pytest.raises(ValueError, match="invalid report query chunk seconds"):
            report_profile(profile)
    profile["report"].pop("query_chunk_seconds")
    tasks, reason = collection_plan(report_profile(profile), data, ["D06"])
    assert reason is None
    assert all(task["chunk_seconds"] == 86400 for task in tasks)
    assert all(task["planned_calls"] == 1 for task in tasks)


@pytest.mark.asyncio
async def test_pod_window_boundaries_preserve_uid_conflicts_and_sample_gaps():
    profile, data = setup(1)
    data["scope"]["clusters"] = data["scope"]["clusters"][:1]
    start = timestamp(data["time_range"]["start"])
    labels = dict(namespace="training", pod="reused-name", node="node")

    def row(identity, offsets, value):
        return dict(
            metric={**labels, **identity},
            values=[[start + offset, value] for offset in offsets],
        )

    original = {
        query: [
            dict(
                id=query,
                cluster_id="cpc-1",
                tool_status="ok",
                quality={"original_samples": True, "max_hold_seconds": 30},
                snapshot={"data": rows},
            )
        ]
        for query, rows in {
            "D01": [row({"uuid": "gpu"}, [7185, 7200, 7215, 7230, 7305, 7320], "0")],
            "D06": [
                row({"uid": "old"}, [7185, 7200], "1"),
                row({"uid": "new"}, [7200, 7215, 7230, 7305, 7320], "1"),
            ],
        }.items()
    }

    async def query(args):
        query_id = "D06" if args["expr"].startswith("kube_pod_info{") else "D01"
        stop = timestamp(args["endTime"])
        length = int(re.search(r"\[(\d+)s\]$", args["expr"])[1])
        if query_id == "D06":
            assert length == 7201
        rows = copy.deepcopy(original[query_id][0]["snapshot"]["data"])
        for row in rows:
            row["values"] = [v for v in row["values"] if stop - length < v[0] <= stop]
        return {"data": [row for row in rows if row["values"]]}

    collected, _, summary = await collect_report(
        {"query_prometheus": query},
        profile,
        data,
        time.monotonic() + 60,
        ["D01", "D06"],
        False,
    )

    def mapped(source):
        return [
            (row["gpu_uuid"], row["pod_uid"], row["start"], row["end"])
            for row in allocations(
                source["D01"], data["time_range"], source["D06"], observed=True
            )
        ]

    assert summary["complete"] and summary["query_calls"] == 13
    assert mapped(collected) == mapped(original)
    assert {uid for _, uid, _, _ in mapped(collected)} == {"old", "new"}
    for excluded in (start + 7205, start + 7275):
        assert not any(a <= excluded < b for _, _, a, b in mapped(collected))
