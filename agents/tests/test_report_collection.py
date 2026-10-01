"""Report plans preserve complete periods without changing RCA collection."""

import asyncio
import copy
import json
import re
import time
from datetime import datetime, timedelta, timezone

import pytest

from agent_common.contracts import timestamp
from agent_common.observation import Observation, series
from ops_agent.collection import collect_report, report_profile
from ops_agent.workflow import calculate


def setup(days=7):
    profile = json.load(open("agents/config.example.json"))
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
    assert summary["query_calls"] == len(calls) <= 6 * (int(days) + 1)
    assert all(
        s["completed_seconds"] == s["requested_seconds"] for s in summary["tasks"]
    )
    assert any(s["empty_seconds"] > 0 for s in summary["tasks"])
    assert all("[86401s]" in a["expr"] for a in calls) if days in (1, 7, 31) else True
    expected = set(
        range(
            int(timestamp(data["time_range"]["start"])),
            int(timestamp(data["time_range"]["end"])) + 1,
            3600,
        )
    )
    for r in series(collected["D02"]):
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
    profile["report"]["limits"].update(max_queries=16, max_rows=3)
    calls = []
    collected, _, summary = await collect_report(
        {"query_prometheus": source(data, calls, dense=True)},
        profile,
        data,
        time.monotonic() + 60,
        ["D01", "D02", "D08", "D06"],
        True,
    )
    assert summary["query_calls"] <= 16 and not summary["complete"]
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
