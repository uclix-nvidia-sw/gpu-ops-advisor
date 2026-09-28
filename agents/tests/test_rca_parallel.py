import asyncio
import copy
import time

import pytest

from agent_common.observation import Observation
from rcca_agent.observation_agents import collect_round


def parent(tool):
    profile = {
        "limits": {
            "max_queries": 3,
            "max_rows": 100,
            "max_bytes": 10000,
            "max_range_seconds": 3600,
            "chunk_seconds": 3600,
        },
        "clusters": {"c": {"mimir_uid": "m", "metric_selector": {}}},
        "queries": {
            q: {
                "source": "mimir",
                "metric": metric,
                "revision": "test",
                "max_hold_seconds": 30,
            }
            for q, metric in (("D01", "metric_a"), ("D02", "metric_b"))
        },
    }
    data = {
        "scope": {"clusters": [{"cluster_id": "c", "namespaces": None}]},
        "time_range": {"start": "2026-09-15T00:00:00Z", "end": "2026-09-15T00:01:00Z"},
    }
    return Observation({"query_prometheus": tool}, profile, data, time.monotonic() + 10)


@pytest.mark.asyncio
async def test_parallel_partial_failure_budget_and_canonical_order():
    both_started = asyncio.Event()
    active = 0
    peak = 0

    async def tool(args):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        if active == 2:
            both_started.set()
        try:
            await asyncio.wait_for(both_started.wait(), 1)
            if args["expr"].startswith("metric_a"):
                raise OSError("fixture failure")
            return {"data": {"result": [{"metric": {}, "values": [[1789430400, "1"]]}]}}
        finally:
            active -= 1

    obs = parent(tool)
    unchanged = copy.deepcopy(obs.profile)
    budget = {"queries": 3, "discovery": 0}
    results = await collect_round(
        obs, ["D02", "D01"], budget, round_no=0, concurrency=2
    )
    assert peak == 2 and active == 0
    assert budget == {"queries": 1, "discovery": 0}
    assert obs.profile == unchanged
    assert [e["query_id"] for e in obs.evidence if e["query_id"].startswith("D")] == [
        "D01",
        "D02",
    ]
    assert results["D01"][0]["tool_status"] == "unavailable"
    assert results["D02"][0]["tool_status"] == "ok"


@pytest.mark.asyncio
async def test_cancellation_reaps_all_sub_agents():
    started = asyncio.Event()
    active = 0

    async def tool(args):
        nonlocal active
        active += 1
        if active == 2:
            started.set()
        try:
            await asyncio.Event().wait()
        finally:
            active -= 1

    obs = parent(tool)
    task = asyncio.create_task(
        collect_round(obs, ["D01", "D02"], {"queries": 4, "discovery": 0}, round_no=0)
    )
    await asyncio.wait_for(started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert active == 0
    assert not any(t.get_name().startswith("observation-") for t in asyncio.all_tasks())


@pytest.mark.asyncio
async def test_zero_reservation_cannot_issue_request():
    calls = 0

    async def tool(args):
        nonlocal calls
        calls += 1
        return {"data": {"result": []}}

    obs = parent(tool)
    budget = {"queries": 1, "discovery": 0}
    results = await collect_round(obs, ["D01", "D02"], budget, round_no=0)
    assert calls == 1 and budget["queries"] == 0
    assert results["D02"][0]["quality"]["reason"] == "budget_exhausted"
