"""Datasource discovery resolves routing only; contracts remain verified separately."""

import copy
import time

import pytest

from agent_common.observation import Observation
from agent_common.query_contract import validate_profile
from test_binding_contract import DATA, profile
from test_cluster_parameters import parameterized
from test_discovery import Grafana


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
        assert available == {"D02", "D09"}
    assert config["bindings"]["fleet_intelligence.D09"]["max_hold"]["seconds"] == 0
