import copy
import json
import time

import pytest

from agent_common.observation import MCPResponseError, Observation, unwrap
from agent_common.grafana_time import mcp_time
from agent_common.contracts import timestamp
from agent_common.parsers import log_lines


PERIOD = {"start": "2026-09-15T00:00:00Z", "end": "2026-09-15T01:00:00Z"}


@pytest.mark.parametrize(
    "value,expected,rounded_start",
    [
        (
            "2026-09-21T02:34:41.713295Z",
            "2026-09-21T02:34:41.713Z",
            "2026-09-21T02:34:41.714Z",
        ),
        (
            "2026-09-21T11:34:41.713295+09:00",
            "2026-09-21T02:34:41.713Z",
            "2026-09-21T02:34:41.714Z",
        ),
        (
            "2026-09-21T23:59:59.999999Z",
            "2026-09-21T23:59:59.999Z",
            "2026-09-22T00:00:00Z",
        ),
        ("2026-09-21T02:34:41Z", "2026-09-21T02:34:41Z", "2026-09-21T02:34:41Z"),
    ],
)
def test_mcp_time_supports_fractional_alert_times(value, expected, rounded_start):
    assert mcp_time(value) == expected
    assert mcp_time(value, ceiling=True) == rounded_start


def test_mcp_time_requires_timezone():
    with pytest.raises(ValueError, match="timezone required"):
        mcp_time("2026-09-21T02:34:41.713295")


def profile():
    with open("agents/config.example.json", encoding="utf-8") as f:
        return json.load(f)


class Grafana:
    def __init__(self):
        self.calls = []
        self.sources = [
            {"uid": "metrics", "type": "prometheus"},
            {"uid": "logs", "type": "loki"},
        ]
        self.labels = {
            ("metrics", "cluster_id"): ["cluster-a", "cluster-b"],
            ("logs", "cluster"): ["cluster-a", "cluster-b"],
        }

    async def call(self, name, args):
        self.calls.append((name, args))
        if name == "list_datasources":
            rows = [s for s in self.sources if s["type"] == args["type"]]
            return {"datasources": rows, "hasMore": False, "total": len(rows)}
        if "label_values" in name:
            return self.labels.get((args["datasourceUid"], args["labelName"]), [])
        return {"data": []}

    def tools(self):
        def bind(name):
            async def call(args):
                return await self.call(name, args)

            return call

        return {
            name: bind(name)
            for name in (
                "list_datasources",
                "list_prometheus_label_values",
                "list_loki_label_values",
                "query_prometheus",
                "query_loki_logs",
            )
        }


def observation(grafana, config=None, cluster="cluster-a"):
    return Observation(
        grafana.tools(),
        config or profile(),
        {
            "time_range": PERIOD,
            "scope": {"clusters": [{"cluster_id": cluster, "namespaces": ['dev"|.*']}]},
        },
        time.monotonic() + 30,
    )


@pytest.mark.asyncio
async def test_builtin_profile_discovers_both_sources_and_preserves_scope():
    grafana = Grafana()
    obs = observation(grafana)
    assert profile()["clusters"] == {}
    assert all(q["validated"] for q in profile()["queries"].values())
    await obs.collect("D02")
    discovery_count = obs.discovery_calls
    await obs.collect("D03")
    assert obs.discovery_calls == discovery_count
    await obs.collect("D09")
    queries = [(n, a) for n, a in grafana.calls if n.startswith("query_")]
    assert len(queries) == 3
    assert queries[0][1]["datasourceUid"] == "metrics"
    assert 'cluster_id="cluster-a"' in queries[0][1]["expr"]
    assert 'namespace=~"dev\\"\\\\|\\\\.\\\\*"' in queries[0][1]["expr"]
    assert queries[-1][1]["datasourceUid"] == "logs"
    assert 'cluster="cluster-a"' in queries[-1][1]["logql"]
    for name, args in grafana.calls:
        if "label_values" in name:
            assert args["startRfc3339"] == PERIOD["start"]
            assert args["endRfc3339"] == PERIOD["end"]


@pytest.mark.asyncio
async def test_fractional_times_normalized_at_both_mcp_boundaries():
    grafana = Grafana()
    obs = observation(grafana)
    period = {
        "start": "2026-09-21T02:04:10.123456Z",
        "end": "2026-09-21T02:34:41.713295Z",
    }
    obs.data["time_range"] = period.copy()
    await obs.collect("D02")
    await obs.collect("D09")
    assert obs.data["time_range"] == period
    for name, args in grafana.calls:
        if name == "list_prometheus_label_values":
            assert args["startRfc3339"] == "2026-09-21T02:04:10.124Z"
            assert args["endRfc3339"] == "2026-09-21T02:34:41.713Z"
        elif name == "query_prometheus":
            assert args["endTime"] == "2026-09-21T02:34:41.713Z"
        elif name in {"list_loki_label_values", "query_loki_logs"}:
            assert args["startRfc3339"] == "2026-09-21T02:04:10.124Z"
            assert args["endRfc3339"] == "2026-09-21T02:34:41.713Z"
    assert all(e["time_range"] == period for e in obs.evidence)
    assert (
        next(e for e in obs.evidence if e["query_id"] == "D09")["quality"]["reason"]
        == "time_precision_reduced"
    )


@pytest.mark.asyncio
async def test_discovery_submillisecond_range_does_not_expand_scope():
    grafana = Grafana()
    obs = observation(grafana)
    obs.data["time_range"] = {
        "start": "2026-09-21T02:04:10.123456Z",
        "end": "2026-09-21T02:04:10.123789Z",
    }
    result = await obs.collect("D02")
    assert result[0]["quality"]["reason"] == "time_range_below_millisecond_resolution"
    assert not any(
        "label_values" in name or name.startswith("query_") for name, _ in grafana.calls
    )


@pytest.mark.asyncio
async def test_validated_is_not_a_deployment_switch():
    config = profile()
    config["queries"]["D02"]["validated"] = False
    grafana = Grafana()
    result = await observation(grafana, config).collect("D02")
    assert result[0]["tool_status"] == "empty"
    assert any(n == "query_prometheus" for n, _ in grafana.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case,reason",
    [
        ("none", "datasource_not_found"),
        ("ambiguous", "datasource_ambiguous"),
        ("missing_cluster", "cluster_not_found_in_datasources"),
        ("no_labels", "cluster_not_found_in_datasources"),
        ("alias", "cluster_not_found_in_datasources"),
        ("truncated", "cluster_discovery_limit_exceeded"),
    ],
)
async def test_unresolved_sources_never_issue_unscoped_queries(case, reason):
    grafana = Grafana()
    if case == "none":
        grafana.sources = []
    elif case == "ambiguous":
        grafana.sources.append({"uid": "other", "type": "prometheus"})
        grafana.labels[("other", "cluster_id")] = ["cluster-a"]
    elif case == "missing_cluster":
        grafana.labels[("metrics", "cluster_id")] = ["cluster-b"]
    elif case == "no_labels":
        grafana.labels = {}
    elif case == "alias":
        grafana.labels[("metrics", "cluster_id")] = ["clustera"]
    elif case == "truncated":
        grafana.labels[("metrics", "cluster_id")] = ["cluster-a"] * 5001
    result = await observation(grafana).collect("D02")
    assert result[0]["quality"]["reason"] == reason
    assert not any(n.startswith("query_") for n, _ in grafana.calls)


@pytest.mark.asyncio
async def test_multiple_sources_select_only_one_containing_requested_cluster():
    grafana = Grafana()
    grafana.sources.insert(0, {"uid": "unrelated", "type": "prometheus"})
    grafana.labels[("unrelated", "cluster_id")] = ["cluster-b"]
    result = await observation(grafana).collect("D02")
    assert result[0]["quality"]["datasource_uid"] == "metrics"


@pytest.mark.asyncio
async def test_discovery_failure_does_not_block_other_source_or_leak_error():
    grafana = Grafana()
    tools = grafana.tools()

    async def forbidden(args):
        raise RuntimeError("Bearer private-test-token")

    tools["list_prometheus_label_values"] = forbidden
    obs = observation(grafana)
    obs.tools = tools
    result = await obs.collect("D02")
    assert result[0]["quality"]["reason"] == "datasource_discovery_failed"
    assert "private-test-token" not in json.dumps(result)
    assert (await obs.collect("D09"))[0]["tool_status"] == "empty"


@pytest.mark.asyncio
async def test_discovery_budget_and_deadline_are_bounded():
    config = profile()
    config["limits"]["max_discovery_calls"] = 1
    grafana = Grafana()
    result = await observation(grafana, config).collect("D02")
    assert result[0]["quality"]["reason"] == "discovery_budget_exhausted"
    assert len(grafana.calls) == 1
    obs = observation(Grafana())
    obs.deadline = time.monotonic() - 1
    assert (await obs.collect("D02"))[0]["quality"][
        "reason"
    ] == "discovery_deadline_exhausted"


@pytest.mark.asyncio
async def test_discovery_follows_pagination_before_selecting_source():
    grafana = Grafana()
    obs = observation(grafana)

    async def pages(args):
        return {
            "datasources": [
                {
                    "uid": "unrelated" if args["offset"] == 0 else "metrics",
                    "type": "prometheus",
                }
            ],
            "hasMore": args["offset"] == 0,
        }

    obs.tools["list_datasources"] = pages
    grafana.labels[("unrelated", "cluster_id")] = ["cluster-b"]
    assert (await obs.collect("D02"))[0]["quality"]["datasource_uid"] == "metrics"


@pytest.mark.asyncio
async def test_expert_profile_override_still_works_without_discovery_tools():
    config = copy.deepcopy(profile())
    config["clusters"] = {
        "cluster-a": {"mimir_uid": "custom", "metric_selector": {"cluster": "alias"}}
    }
    grafana = Grafana()
    obs = observation(grafana, config)
    obs.tools = {"query_prometheus": grafana.tools()["query_prometheus"]}
    assert (await obs.collect("D02"))[0]["quality"]["datasource_uid"] == "custom"
    assert obs.discovery_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["D05", "D09", "D13"])
async def test_loki_reserves_mcp_probe_and_preserves_truncation(query):
    grafana = Grafana()
    config = profile()
    config["limits"]["max_rows"] = 3
    obs = observation(grafana, config)

    async def truncated(args):
        assert args["limit"] == 2  # MCP asks Loki for one additional entry.
        return {"data": [{"line": "retained"}], "metadata": {"resultsTruncated": True}}

    obs.tools["query_loki_logs"] = truncated
    result = (await obs.collect(query))[0]
    assert result["tool_status"] == "partial"
    assert result["quality"]["reason"] == "sample_limit_exceeded"
    assert result["quality"]["complete"] is False
    assert result["snapshot"]["data"] == [{"line": "retained"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("max_rows", [1, 3, 5000, 5001, 10000])
async def test_loki_requested_limit_is_positive_and_enforced(max_rows):
    obs = observation(Grafana())
    obs.profile["limits"]["max_rows"] = max_rows

    async def full(args):
        assert args["limit"] == min(4999, max(1, max_rows - 1))
        return [{"line": "fixture"}] * args["limit"]

    obs.tools["query_loki_logs"] = full
    result = (await obs.collect("D09"))[0]
    assert result["tool_status"] == "partial"
    assert result["quality"]["reason"] == "sample_limit_exceeded"


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["D05", "D09", "D02"])
@pytest.mark.parametrize(
    "response,code",
    [
        (
            "MCPToolClient tool call failed: max entries limit per query exceeded; private-test-token",
            "loki_entry_limit_exceeded",
        ),
        (
            "MCPToolClient tool call failed: Forbidden private-test-token",
            "mcp_tool_error",
        ),
        (
            {
                "isError": True,
                "content": [{"type": "text", "text": "private-test-token"}],
            },
            "mcp_tool_error",
        ),
        ("<html>private-test-token</html>", "invalid_mcp_response"),
    ],
)
async def test_mcp_failures_keep_safe_codes_instead_of_json_errors(
    query, response, code, caplog
):
    obs = observation(Grafana())

    async def failed(args):
        return response

    obs.tools["query_prometheus" if query == "D02" else "query_loki_logs"] = failed
    result = (await obs.collect(query))[0]
    assert result["tool_status"] == "unavailable"
    assert result["snapshot"] == {}
    assert result["quality"]["reason"] == "query_failed"
    assert result["quality"]["error_type"] == "MCPResponseError"
    assert result["quality"]["error_code"] == code
    assert f"error_code={code}" in caplog.text
    assert "private-test-token" not in json.dumps(result) + caplog.text


def test_mcp_success_and_error_envelopes():
    from mcp.types import CallToolResult, TextContent

    assert unwrap(
        CallToolResult(content=[TextContent(type="text", text='{"data": []}')])
    ) == {"data": []}
    assert unwrap({"structuredContent": {}, "content": []}) == {}
    with pytest.raises(MCPResponseError, match="mcp_tool_error"):
        unwrap({"isError": True, "structuredContent": {"data": []}, "content": []})


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["D05", "D09"])
async def test_fleet_json_filters_keep_scope_and_escape_clues(query):
    grafana = Grafana()
    obs = observation(grafana)
    node = 'node"|~".*'
    component = "xid\\test\nvalue"
    obs.data["target"] = {"node": node}
    obs.data["log_query_target"] = {"node": node, "component": component}
    obs.profile["queries"][query]["json_target_fields"] = {
        "node": 'resources["k8s.node.name"]',
        "component": 'attributes["component"]',
    }
    original = copy.deepcopy(obs.data)
    await obs.collect(query)
    args = next(a for n, a in grafana.calls if n == "query_loki_logs")
    selector, pipeline = args["logql"].split(" | drop ", 1)
    assert selector == '{cluster="cluster-a",namespace=~"dev\\"\\\\|\\\\.\\\\*"}'
    assert "node=" not in selector and "component=" not in selector
    assert pipeline.startswith(
        "dsx_json_0, dsx_json_0_extracted, dsx_json_1, dsx_json_1_extracted | json "
    )
    assert 'dsx_json_1="resources[\\"k8s.node.name\\"]"' in pipeline
    assert 'dsx_json_0="attributes[\\"component\\"]"' in pipeline
    assert ' | __error__=""' in pipeline
    assert (
        f" | (dsx_json_1={json.dumps(node)} or dsx_json_1_extracted={json.dumps(node)})"
        in pipeline
    )
    assert (
        f" | (dsx_json_0={json.dumps(component)} or dsx_json_0_extracted={json.dumps(component)})"
        in pipeline
    )
    assert obs.data == original


@pytest.mark.asyncio
async def test_native_node_selector_and_prometheus_ignore_json_clues():
    grafana = Grafana()
    obs = observation(grafana)
    obs.data["target"] = {"node": "native-node"}
    await obs.collect("D09")
    args = next(a for n, a in grafana.calls if n == "query_loki_logs")
    assert 'node="native-node"' in args["logql"] and " | json " not in args["logql"]
    obs.data["log_query_target"] = {"node": "other-node", "component": "xid"}
    await obs.collect("D02")
    args = next(a for n, a in grafana.calls if n == "query_prometheus")
    assert 'node="native-node"' in args["expr"]
    assert "other-node" not in args["expr"] and "component" not in args["expr"]


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["D05", "D09", "D13"])
async def test_loki_byte_limit_splits_and_retains_all_log_entries(query):
    obs = observation(Grafana())
    obs.profile["limits"]["max_bytes"] = 2500
    start = int(timestamp(PERIOD["start"]))
    events = [
        (start + offset, str(offset) + "x" * 400) for offset in range(1, 3600, 180)
    ]
    calls = []

    async def logs(args):
        calls.append(args.copy())
        return {
            "data": [
                {"line": line}
                for at, line in events
                if timestamp(args["startRfc3339"])
                <= at
                <= timestamp(args["endRfc3339"])
            ]
        }

    obs.tools["query_loki_logs"] = logs
    result = await obs.collect(query)
    assert 1 < len(calls) == obs.calls <= obs.profile["limits"]["max_queries"]
    assert all(
        e["tool_status"] in {"ok", "empty"} and e["quality"]["complete"] for e in result
    )
    assert {line for e in result for line in log_lines(e["snapshot"])} == {
        line for _, line in events
    }
    assert timestamp(result[0]["time_range"]["start"]) == start
    assert timestamp(result[-1]["time_range"]["end"]) == timestamp(PERIOD["end"])
    assert all(
        left["time_range"]["end"] == right["time_range"]["start"]
        for left, right in zip(result, result[1:])
    )
    assert all(
        args["logql"] == calls[0]["logql"] and args["limit"] <= 4999 for args in calls
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("exhaust", ["queries", "deadline"])
async def test_oversized_loki_retry_keeps_unqueried_tail_unknown(exhaust):
    obs = observation(Grafana())
    obs.profile["limits"].update(
        max_bytes=2000, max_queries=1 if exhaust == "queries" else 48
    )

    async def huge(args):
        if exhaust == "deadline":
            obs.deadline = time.monotonic() - 1
        return {"data": [{"line": "x" * 3000}]}

    obs.tools["query_loki_logs"] = huge
    result = await obs.collect("D09")
    assert obs.calls == 1 and len(result) == 1
    assert result[0]["tool_status"] == "unavailable"
    assert result[0]["quality"]["reason"] == "budget_exhausted"
    assert timestamp(result[0]["time_range"]["start"]) == timestamp(PERIOD["start"])
    assert timestamp(result[0]["time_range"]["end"]) == timestamp(PERIOD["end"])


@pytest.mark.asyncio
async def test_single_oversized_loki_entry_remains_partial():
    obs = observation(Grafana())
    obs.data["time_range"] = {"start": PERIOD["start"], "end": "2026-09-15T00:00:01Z"}
    obs.profile["limits"]["max_bytes"] = 2000

    async def huge(args):
        return {"data": [{"line": "x" * 3000}]}

    obs.tools["query_loki_logs"] = huge
    result = await obs.collect("D09")
    assert obs.calls == 1
    assert result[0]["tool_status"] == "partial" and result[0]["snapshot"] == {}
    assert result[0]["quality"]["reason"] == "response_byte_limit"
