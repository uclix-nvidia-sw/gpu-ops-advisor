import copy
import json
import time

import pytest

from agent_common.observation import Observation


PERIOD = {"start": "2026-09-15T00:00:00Z", "end": "2026-09-15T01:00:00Z"}


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
