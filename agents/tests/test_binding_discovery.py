"""Datasource discovery resolves routing only; contracts remain verified separately."""

import copy
import time

import pytest

from agent_common.observation import Observation, series
from agent_common.query_contract import validate_profile
from test_binding_contract import DATA, profile
from test_cluster_parameters import parameterized
from test_discovery import Grafana


@pytest.mark.parametrize(
    "query,metric,unit,value",
    [
        ("D03", "DCGM_FI_DEV_FB_USED", "MiB", 2048),
        ("D06", "kube_pod_info", "info", 1),
        ("D10", "up", "boolean", 0),
        ("D15", "DCGM_FI_DEV_FB_FREE", "MiB", 1024),
        ("D20", "kube_node_status_condition", "boolean", 1),
        ("D22", "scrape_duration_seconds", "seconds", 0.2),
        ("D12", "kube_node_status_allocatable", "resource_units", 8),
        ("D35", "DCGM_FI_DEV_XID_ERRORS", "error_code", 79),
        ("D49", "DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION", "mJ", 500000),
    ],
)
async def test_core_defaults_collect_for_new_cluster_and_preserve_observation(
    query, metric, unit, value
):
    from test_binding_contract import START
    from rcca_agent.synthesis import synthesis_input

    class Samples(Grafana):
        async def call(self, name, args):
            if name == "query_prometheus":
                self.calls.append((name, args))
                return {
                    "data": {
                        "resultType": "matrix",
                        "result": [
                            {
                                "metric": {
                                    "__name__": metric,
                                    "UUID": "gpu-fixture",
                                    "node": "node-fixture",
                                    "uid": "pod-fixture",
                                },
                                "values": [
                                    [START, str(value)],
                                    [START + 15, str(value)],
                                ],
                            }
                        ],
                    }
                }
            return await super().call(name, args)

    config = profile(active_defaults=True)
    data = copy.deepcopy(DATA)
    data["scope"]["clusters"][0]["cluster_id"] = "new-region-42"
    data["incident_time"] = data["time_range"]["start"]
    grafana = Samples()
    grafana.labels[("metrics", "cluster_id")] = ["new-region-42"]
    obs = Observation(grafana.tools(), config, data, time.monotonic() + 30)
    evidence = await obs.collect(query)
    assert evidence[0]["tool_status"] == "ok"
    assert evidence[0]["quality"]["selection_method"] == "automatic_verified"
    requests = [args for name, args in grafana.calls if name == "query_prometheus"]
    assert all('cluster_id="new-region-42"' in r["expr"] for r in requests)
    assert all('collection_path="alloy-direct"' in r["expr"] for r in requests)
    samples = series(evidence)
    assert samples[0]["unit"] == unit
    assert samples[0]["samples"][0][1] == value
    payload = synthesis_input(data, evidence, [], [], [])
    assert payload["metric_observations"] == samples
    assert payload["device_observations"] == []


def discovered(config, query="D02"):
    binding = parameterized(config, query)
    binding["environment"].update(datasource_mode="discover", datasource_uid=None)
    if query == "D09":
        binding.update(
            unit="log",
            sample_type="log",
            timestamp_basis="loki_recorded_at",
            event_timestamp_rule="loki_recorded_at",
            json_target_fields={},
        )
        binding["environment"]["scope_labels"] = {"cluster_id": "cluster"}
        for key in ("sample_interval", "invalid_values", "counter_reset"):
            binding[key] = {"mode": "not_applicable", "reason": "fixture logs"}
    config["queries"][query]["selected_binding"] = None
    return binding


@pytest.mark.parametrize(
    "query,source,label", [("D02", "metrics", "cluster_id"), ("D09", "logs", "cluster")]
)
async def test_verified_binding_discovers_uid_preserves_contract_and_evidence(
    query, source, label
):
    config = profile()
    discovered(config, query)
    validate_profile(config)
    original = copy.deepcopy(config)
    grafana = Grafana()
    grafana.labels[(source, label)] = ["fixture"]
    obs = Observation(grafana.tools(), config, DATA, time.monotonic() + 30)
    result = await obs.collect(query)
    assert result[0]["tool_status"] == "empty"
    assert result[0]["quality"]["datasource_uid"] == source
    assert result[0]["quality"]["datasource_resolution"] == "discover"
    assert result[0]["quality"]["selection_method"] == "automatic_verified"
    requests = [args for name, args in grafana.calls if name.startswith("query_")]
    assert len(requests) == 1
    expr = requests[0].get("expr", requests[0].get("logql"))
    assert f'{label}="fixture"' in expr and 'job="fixture-producer"' in expr
    assert config == original


@pytest.mark.parametrize(
    "case,reason",
    [
        ("ambiguous", "datasource_ambiguous"),
        ("wrong_label", "cluster_not_found_in_datasources"),
        ("missing", "cluster_not_found_in_datasources"),
        ("budget", "discovery_budget_exhausted"),
    ],
)
async def test_discovery_failure_never_queries_an_arbitrary_source(case, reason):
    config = profile()
    discovered(config)
    grafana = Grafana()
    grafana.labels[("metrics", "cluster_id")] = ["fixture"]
    if case == "ambiguous":
        grafana.sources.append({"uid": "second", "type": "prometheus"})
        grafana.labels[("second", "cluster_id")] = ["fixture"]
    elif case in ("wrong_label", "missing"):
        grafana.labels[("metrics", "cluster_id")] = []
        if case == "wrong_label":
            grafana.labels[("metrics", "cluster")] = ["fixture"]
    elif case == "budget":
        config["limits"]["max_discovery_calls"] = 0
    obs = Observation(grafana.tools(), config, DATA, time.monotonic() + 30)
    assert (await obs.collect("D02"))[0]["quality"]["reason"] == reason
    assert not any(name.startswith("query_") for name, _ in grafana.calls)


async def test_discovery_does_not_promote_unverified_candidate():
    config = profile()
    binding = discovered(config)
    binding["verification"]["status"] = "candidate"
    validate_profile(config)
    obs = Observation({}, config, DATA, time.monotonic() + 30)
    assert (await obs.collect("D02"))[0]["quality"]["reason"] == "binding_unselected"
    assert obs.calls == obs.discovery_calls == 0


@pytest.mark.parametrize(
    "change",
    [
        {"datasource_mode": "guess"},
        {"datasource_mode": "discover", "datasource_uid": "pinned-too"},
        {"datasource_mode": "pinned", "datasource_uid": None},
    ],
)
def test_invalid_or_ambiguous_datasource_configuration_rejected(change):
    config = profile()
    binding = discovered(config)
    binding["environment"].update(change)
    with pytest.raises(ValueError):
        validate_profile(config)


def test_discovery_requires_explicit_parameter_label_contract():
    config = profile()
    binding = discovered(config)
    binding["environment"].pop("scope_labels")
    binding["environment"]["cluster_id"] = "fixture"
    with pytest.raises(ValueError, match="discovery requires parameter scope"):
        validate_profile(config)


@pytest.mark.parametrize("stronger", [[], ["other-cluster"], ["fixture-alias"]])
async def test_label_candidates_preserve_exact_cluster_and_precedence(stronger):
    config = profile()
    binding = discovered(config)
    binding["environment"]["scope_labels"]["cluster_id"] = ["cluster_id", "cluster"]
    validate_profile(config)
    grafana = Grafana()
    grafana.labels[("metrics", "cluster_id")] = stronger
    grafana.labels[("metrics", "cluster")] = ["fixture"]
    obs = Observation(grafana.tools(), config, DATA, time.monotonic() + 30)
    row = (await obs.collect("D02"))[0]
    if stronger:
        assert row["quality"]["reason"] == "cluster_not_found_in_datasources"
        assert not any(name.startswith("query_") for name, _ in grafana.calls)
    else:
        assert row["quality"]["resolved_cluster_selector"] == {"cluster": "fixture"}
        assert row["quality"]["datasource_uid"] == "metrics"


@pytest.mark.parametrize(
    "labels", [[], ["cluster_id", "cluster_id"], ["bad-label"], [None], 42]
)
def test_invalid_label_candidates_rejected(labels):
    config = profile()
    binding = discovered(config)
    binding["environment"]["scope_labels"]["cluster_id"] = labels
    with pytest.raises(ValueError):
        validate_profile(config)


@pytest.mark.parametrize("conflict", ["selector", "target_labels", "pinned"])
def test_candidate_labels_cannot_be_overridden(conflict):
    config = profile()
    binding = discovered(config)
    binding["environment"]["scope_labels"]["cluster_id"] = ["cluster_id", "cluster"]
    if conflict == "selector":
        binding["environment"]["selector"]["cluster"] = "fixed"
    elif conflict == "target_labels":
        binding["target_labels"]["node"] = "cluster"
    else:
        binding["environment"].update(datasource_mode="pinned", datasource_uid="fixed")
    with pytest.raises(ValueError):
        validate_profile(config)


def test_shared_defaults_activate_only_reviewed_observation_contracts():
    from agent_common.query_contract import query_definition

    config = profile(active_defaults=True)
    validate_profile(config)
    assert config["clusters"] == {}
    for cluster in ("new-region-42", "another-site"):
        available = {
            key
            for key in config["queries"]
            if query_definition(config, key, cluster).get("availability")
            != "unavailable"
        }
        assert available == set(config["queries"]) - {
            "D07",
            "D46",
        }
    assert config["bindings"]["fleet_intelligence.D09"]["max_hold"]["seconds"] == 0
