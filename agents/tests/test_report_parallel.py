"""Concurrent report collection keeps scope, evidence and task lifetime bounded."""

import asyncio
import copy
import time

import pytest

from ops_agent.collection import collect_report
from ops_agent.workflow import calculate
from test_report_collection import setup, source


@pytest.mark.asyncio
async def test_parallel_calls_match_serial_results_and_reduce_fixture_time():
    profile, data = setup(1)
    results = []
    for concurrency in (1, 3):
        profile["report"]["limits"]["max_concurrency"] = concurrency
        calls, active, peak = [], 0, 0
        upstream = source(data, calls)

        async def query(args):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(0.04)
                return await upstream(args)
            finally:
                active -= 1

        started = time.monotonic()
        collected, evidence, summary = await collect_report(
            {"query_prometheus": query},
            profile,
            data,
            time.monotonic() + 20,
            ["D03", "D04", "D06", "D03"],
            False,
        )
        duration = time.monotonic() - started
        metrics = calculate("O01", data, collected, {}, {})["metrics"]
        for metric in metrics:
            metric.pop("evidence_refs", None)
        assert summary["query_calls"] == len(calls) == 6
        assert peak <= concurrency and active == 0 and summary["complete"]
        assert len(summary["tasks"]) == 6
        assert all(e["quality"]["sub_agent_id"] for e in evidence)
        results.append((metrics, duration, peak))
    assert results[0][0] == results[1][0]
    assert results[1][2] == 3
    assert results[1][1] < results[0][1] * 0.75
    print(
        f"fixed 40ms MCP fixture: serial={results[0][1]:.3f}s parallel={results[1][1]:.3f}s"
    )


@pytest.mark.asyncio
async def test_dependencies_preserve_namespace_narrowing_and_response_reuse():
    profile, data = setup(1)
    profile["queries"]["D08"].update(
        metric="DCGM_FI_DEV_GPU_UTIL", allocation_semantics="observed_pod_labels"
    )
    calls = []
    collected, evidence, summary = await collect_report(
        {"query_prometheus": source(data, calls)},
        profile,
        data,
        time.monotonic() + 20,
        ["D06", "D01", "D02", "D08"],
        True,
    )
    assert len(calls) == 4  # One GPU response and one narrowed Pod request per CPC.
    assert all(
        'namespace=~"training"' in a["expr"]
        for a in calls
        if a["expr"].startswith("kube")
    )
    refs = {e["id"] for e in evidence}
    assert all(e["quality"]["reused_from_evidence"] in refs for e in collected["D08"])
    assert all(t["depends_on"] for t in summary["tasks"] if t["query_id"] == "D06")


@pytest.mark.asyncio
async def test_parent_cancellation_reaps_all_mcp_calls():
    profile, data = setup(1)
    entered, active = asyncio.Event(), 0

    async def wait(args):
        nonlocal active
        active += 1
        if active == 3:
            entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            active -= 1

    task = asyncio.create_task(
        collect_report(
            {"query_prometheus": wait},
            profile,
            data,
            time.monotonic() + 20,
            ["D03", "D04", "D06"],
            False,
        )
    )
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert active == 0


@pytest.mark.asyncio
async def test_discovery_reservations_and_failures_stay_within_global_budget():
    profile, data = setup(1)
    profile["clusters"] = {}
    profile["limits"]["max_discovery_calls"] = 3
    active, peak, calls = 0, 0, 0

    async def fail(args):
        nonlocal active, peak, calls
        calls += 1
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0.01)
            raise RuntimeError("secret must not appear in diagnostics")
        finally:
            active -= 1

    _, evidence, summary = await collect_report(
        {"list_datasources": fail},
        profile,
        data,
        time.monotonic() + 20,
        ["D03", "D04", "D06"],
        False,
    )
    assert summary["discovery_calls"] == calls <= 3 and peak <= 3 and active == 0
    assert not summary["complete"] and "secret" not in str(evidence)


@pytest.mark.asyncio
async def test_failed_task_keeps_independent_success_and_comparison_isolated():
    profile, data = setup(1)
    data["topic_ids"] = ["O10"]
    data["comparison_range"] = {
        "start": "2026-08-01T00:00:00Z",
        "end": "2026-08-02T00:00:00Z",
    }
    before = copy.deepcopy(profile)

    async def query(args):
        if args["expr"].startswith("DCGM_FI_DEV_FB_USED"):
            raise ValueError("private upstream failure")
        await asyncio.sleep(0.01)
        return {"data": []}

    collected, evidence, summary = await collect_report(
        {"query_prometheus": query},
        profile,
        data,
        time.monotonic() + 20,
        ["D03", "D04", "D11"],
        False,
    )
    assert profile == before and not summary["complete"]
    assert all(e["tool_status"] == "empty" for e in collected["D04"])
    assert all(
        e["time_range"] == data["comparison_range"] for e in collected["comparison.D11"]
    )
    assert "private upstream" not in str(evidence)
