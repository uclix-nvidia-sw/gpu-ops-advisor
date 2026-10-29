"""Offline-only checks for daily limits and the manual collection probe."""

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import json
import time
from unittest.mock import AsyncMock

import pytest

from agent_common.contracts import timestamp
from agent_common.runtime import attempt_context
from ops_agent.aggregate_report import run
from ops_agent.report_contract import MAX_BYTES, VERSION, iso, previous_period
from ops_agent.report_queries import ReportQueries, hourly_queries, matrix
from ops_collect_probe import probe
from test_aggregate_report import DATA
from test_report_diagnostics import changed_hours
from test_transition_scheduling import group


def input_for(days):
    data = deepcopy(DATA)
    data["time_range"]["end"] = iso(
        timestamp(data["time_range"]["start"]) + days * 86400
    )
    return data


@pytest.mark.parametrize("days,cap,total", [(1, 96, 128), (7, 32, 80)])
async def test_period_caps_and_prefix(days, cap, total):
    data = input_for(days)
    groups = [
        group(c, p, n)
        for c, now, old in [("cpc-1", 9, 12), ("cpc-2", 10, 9)]
        for p, n in [(data["time_range"], now), (previous_period(data), old)]
    ]
    query = AsyncMock(return_value={"data": {"result": []}})
    collector = ReportQueries({"query_prometheus": query}, data, time.monotonic() + 900)
    collector.calls = 15
    evidence = await collector.check_transitions(groups, reserved_calls=12)
    assert (collector.transition_limit, collector.query_limit) == (cap, total)
    assert collector.transition_calls == (80 if days == 1 else 32)
    assert collector.calls + 12 <= total
    assert [e["cluster_id"] for e in evidence[:16]] == ["cpc-1", "cpc-2"] * 8
    if days == 1:
        assert len(evidence) == 40
        assert all(
            a["status"] == "checked"
            for *_, base in groups
            for a in base[0]["quality"]["transition_verification"]
        )


@pytest.mark.parametrize("days,total", [(1, 128), (7, 80)])
async def test_byte_stop_and_query_error_precedence(days, total):
    tool = AsyncMock(return_value={"padding": "x" * MAX_BYTES})
    collector = ReportQueries(
        {"query_prometheus": tool}, input_for(days), time.monotonic() + 900
    )
    with pytest.raises(ValueError, match="report_response_limit_exceeded"):
        await collector.call("query_prometheus", {})
    size = collector.bytes_received
    assert size > MAX_BYTES
    with pytest.raises(ValueError, match="report_response_limit_exceeded"):
        await collector.call("query_prometheus", {})
    assert (
        tool.await_count == 1
        and collector.calls == 2
        and collector.bytes_received == size
    )
    collector.calls = total
    with pytest.raises(ValueError, match="report_query_limit_exceeded"):
        await collector.call("query_prometheus", {})
    assert tool.await_count == 1 and collector.calls == total + 1


async def test_bytes_discovery_unwrap_and_matrix_failures():
    tool = AsyncMock(
        side_effect=[{"datasources": []}, "invalid json", {"data": "invalid matrix"}]
    )
    c = ReportQueries({"list_datasources": tool}, DATA, time.monotonic() + 900)
    first = await c.call("list_datasources", {})
    size = len(json.dumps(first).encode())
    assert c.bytes_received == size
    with pytest.raises(ValueError):
        await c.call("list_datasources", {})
    assert c.bytes_received == size
    response = await c.call("list_datasources", {})
    with pytest.raises(ValueError):
        matrix(response)
    assert c.bytes_received == size + len(json.dumps(response).encode())


def fake_tools(data, requests):
    async def sources(args):
        requests.append(("list_datasources", args))
        return {
            "datasources": [{"uid": "mimir", "type": "prometheus"}],
            "hasMore": False,
        }

    async def labels(args):
        requests.append(("list_prometheus_label_values", args))
        return [c["cluster_id"] for c in data["scope"]["clusters"]]

    async def query(args):
        requests.append(("query_prometheus", args))
        if args["queryType"] == "range":
            for cluster in data["scope"]["clusters"]:
                for index, expr in enumerate(hourly_queries(cluster).values()):
                    if expr == args["expr"]:
                        period = (
                            data["time_range"]
                            if timestamp(args["endTime"])
                            == timestamp(data["time_range"]["end"])
                            else previous_period(data)
                        )
                        rows = changed_hours(period, cluster["cluster_id"], 3)[index][
                            "snapshot"
                        ]["series"]
                        if index == 1:
                            extra = deepcopy(rows[0])
                            extra["metric"]["instance"] = "second-collector"
                            extra["values"] = extra["values"][:1]
                            rows.append(extra)
                        return {"data": {"result": rows}}
        return {"data": {"result": []}}

    return dict(
        list_datasources=sources,
        list_prometheus_label_values=labels,
        query_prometheus=query,
    )


@pytest.mark.parametrize("days", [1, 7])
async def test_probe_matches_product_collection_and_saves_privately(tmp_path, days):
    data = input_for(days)
    data["scope"]["clusters"].append({"cluster_id": "cpc-2", "namespaces": None})
    product_calls, probe_calls = [], []
    token = attempt_context.set(
        dict(
            claim=dict(
                job_id="00000000-0000-0000-0000-000000000001",
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
        product = await run(fake_tools(data, product_calls))
    finally:
        attempt_context.reset(token)

    @asynccontextmanager
    async def connect():
        yield fake_tools(data, probe_calls)

    folder = tmp_path / "probe"
    result = await probe(data, folder, connect)
    assert probe_calls == product_calls
    assert result["query_count"] == product["result"]["quality"]["query_count"]
    assert result["bytes_received"] == product["result"]["quality"]["bytes_received"]
    assert result["remote_tool_calls"] == len(probe_calls)
    assert result["stages"][-1]["attempted_calls"] == 4
    assert [s["stage"] for s in result["stages"]] == [
        "base",
        "transitions",
        "memory",
        "workload",
        "context",
        "collectors",
    ]
    evidence = json.loads((folder / "evidence.json").read_text())
    original = [
        e for e in product["evidence"] if e["query_id"] != "report_incident_snapshot"
    ]
    for actual, expected in zip(evidence, original, strict=True):
        for key in ("query_id", "cluster_id", "time_range", "snapshot", "tool_status"):
            assert actual[key] == expected[key]
    assert result["llm_called"] is False and result["published"] is False
    assert folder.stat().st_mode & 0o777 == 0o700
    assert (folder / "summary.json").stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        await probe(data, folder, connect)


@pytest.mark.parametrize("cancel", [False, True])
async def test_probe_keeps_safe_failure_diagnostics(tmp_path, cancel):
    @asynccontextmanager
    async def connect():
        if cancel:
            raise asyncio.CancelledError("private secret")
        raise ValueError("private secret")
        yield  # pragma: no cover

    folder = tmp_path / "failed"
    with pytest.raises((ValueError, asyncio.CancelledError)):
        await probe(deepcopy(DATA), folder, connect)
    text = (folder / "summary.json").read_text()
    assert "private secret" not in text
    assert json.loads(text)["status"] == "failed"
    assert json.loads(text)["remote_tool_calls"] == 0


async def test_invalid_input_never_connects(tmp_path):
    connect = AsyncMock()
    data = input_for(2)
    with pytest.raises(ValueError):
        await probe(data, tmp_path / "invalid", connect)
    connect.assert_not_called()
    assert not (tmp_path / "invalid").exists()


async def test_byte_equality_and_timeout_accounting():
    tool = AsyncMock(return_value={})
    collector = ReportQueries({"query_prometheus": tool}, DATA, time.monotonic() + 900)
    collector.bytes_received = MAX_BYTES
    with pytest.raises(ValueError, match="report_response_limit_exceeded"):
        await collector.call("query_prometheus", {})
    assert tool.await_count == 1 and collector.bytes_received == MAX_BYTES + 2
    collector.bytes_received = 0
    tool.side_effect = TimeoutError("private")
    with pytest.raises(TimeoutError):
        await collector.call("query_prometheus", {})
    assert collector.bytes_received == 0


async def test_daily_expansion_preserves_original_request_prefix():
    calls = []
    data = deepcopy(DATA)
    data["scope"]["clusters"].append({"cluster_id": "cpc-2", "namespaces": None})
    for limit in (32, 96):
        query = AsyncMock(return_value={"data": {"result": []}})
        collector = ReportQueries(
            {"query_prometheus": query}, data, time.monotonic() + 900
        )
        collector.transition_limit = limit
        groups = [
            group(c, p, 20)
            for c in ("cpc-1", "cpc-2")
            for p in (data["time_range"], previous_period(data))
        ]
        await collector.check_transitions(groups, reserved_calls=12)
        calls.append([c.args for c in query.await_args_list])
    assert len(calls[0]) == 32 and len(calls[1]) == 96
    assert calls[1][:32] == calls[0]


async def test_probe_cancellation_during_query_keeps_prior_evidence(tmp_path):
    data = deepcopy(DATA)
    requests = []
    tools = fake_tools(data, requests)
    original = tools["query_prometheus"]
    count = 0

    async def query(args):
        nonlocal count
        count += 1
        if count == 4:
            raise asyncio.CancelledError("private cancellation")
        return await original(args)

    tools["query_prometheus"] = query

    @asynccontextmanager
    async def connect():
        yield tools

    folder = tmp_path / "cancelled"
    with pytest.raises(asyncio.CancelledError):
        await probe(data, folder, connect)
    summary = json.loads((folder / "summary.json").read_text())
    assert summary["status"] == "failed" and summary["evidence_count"] == 3
    assert summary["tool_calls"][-1]["status"] == "cancelled"
    assert "private cancellation" not in (folder / "summary.json").read_text()
