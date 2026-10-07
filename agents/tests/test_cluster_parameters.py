"""Shared request scope for both workers; upstream responses are fixtures."""

import copy
import json
import time

import pytest

from agent_common.observation import Observation
from agent_common.query_contract import query_definition, validate_profile
from agent_common.settings import Settings
from ops_agent.workflow import calculate
from rcca_agent.workflow import normalized_state
from test_binding_contract import DATA, PERIOD, START, profile, verified


def parameterized(config, query="D02", **kwargs):
    binding = verified(config, query, **kwargs)
    binding["environment"] = {
        "datasource_uid": "fixture-mimir",
        "scope_labels": {"cluster_id": "cluster_id"},
        "selector": {"job": "fixture-producer"},
    }
    binding["verification"]["applicability"] = (
        "Synthetic source contract for all fixture partitions"
    )
    return binding


def test_both_workers_load_shared_parameter_template():
    config = Settings("rca").profile()
    assert config == Settings("report").profile() == profile(active_defaults=True)
    assert config["clusters"] == {}
    for binding in config["bindings"].values():
        assert set(binding["environment"]["scope_labels"]) == {"cluster_id"}
        assert "cluster_id" not in binding["environment"]


@pytest.mark.parametrize(
    "cluster", ["new-region-42", 'quote"slash\\newline\n', "지역-새클러스터"]
)
async def test_parameter_is_exact_escaped_match_with_original_evidence(cluster):
    config = profile()
    parameterized(config)
    original = copy.deepcopy(config)
    calls = []

    async def query(args):
        calls.append(args)
        return {
            "data": [{"metric": {"UUID": "g", "node": "n"}, "values": [[START, "0"]]}]
        }

    data = {
        **DATA,
        "scope": {"clusters": [{"cluster_id": cluster, "namespaces": None}]},
    }
    obs = Observation({"query_prometheus": query}, config, data, time.monotonic() + 30)
    result = await obs.collect("D02")
    assert calls and all(
        f"cluster_id={json.dumps(cluster)}" in c["expr"] for c in calls
    )
    assert all('job="fixture-producer"' in c["expr"] for c in calls)
    assert all(c["datasourceUid"] == "fixture-mimir" for c in calls)
    assert result[0]["cluster_id"] == cluster
    assert result[0]["quality"]["binding_id"] == "nvidia_dcgm_exporter.D02"
    assert result[0]["quality"]["binding_revision"] == "fixture-binding-1"
    assert config == original


async def test_multiple_clusters_do_not_leak_selectors_or_mutate_profile():
    config = profile()
    binding = parameterized(config)
    binding["environment"]["scope_labels"] = {"cluster_id": "tenant_cluster"}
    original = copy.deepcopy(config)
    calls = []

    async def query(args):
        calls.append(args["expr"])
        return {"data": []}

    data = {
        **DATA,
        "scope": {
            "clusters": [
                {"cluster_id": c, "namespaces": None} for c in ("east-9", "west-12")
            ]
        },
    }
    obs = Observation({"query_prometheus": query}, config, data, time.monotonic() + 30)
    await obs.collect("D02")
    assert len(calls) == 2
    assert 'tenant_cluster="east-9"' in calls[0] and "west-12" not in calls[0]
    assert 'tenant_cluster="west-12"' in calls[1] and "east-9" not in calls[1]
    assert config == original


@pytest.mark.parametrize("cluster", [None, "", "  ", 1, ["east"]])
def test_missing_cluster_never_becomes_unscoped_query(cluster):
    config = profile()
    parameterized(config)
    assert (
        query_definition(config, "D02", cluster)["reason"]
        == "binding_scope_unavailable"
    )
    data = {
        **DATA,
        "scope": {"clusters": [{"cluster_id": cluster, "namespaces": None}]},
    }
    with pytest.raises(ValueError, match="explicit cluster_id"):
        Observation({}, config, data, time.monotonic() + 30)


@pytest.mark.parametrize(
    "change",
    [
        {"scope_labels": {}},
        {"scope_labels": {"cluster_id": "invalid-label"}},
        {"scope_labels": {"cluster_id": "cluster_id", "other": "node"}},
        {"cluster_id": "fixed-name"},
        {"selector": {"cluster_id": "fixed-name"}},
    ],
)
def test_ambiguous_or_invalid_scope_mapping_rejected(change):
    config = profile()
    binding = parameterized(config)
    binding["environment"].update(change)
    with pytest.raises(ValueError):
        validate_profile(config)


def test_target_cannot_overwrite_cluster_scope_and_applicability_required():
    config = profile()
    binding = parameterized(config)
    binding["target_labels"]["node"] = "cluster_id"
    with pytest.raises(ValueError, match="scope label cannot"):
        validate_profile(config)
    binding["target_labels"]["node"] = "node"
    binding["verification"].pop("applicability")
    with pytest.raises(ValueError, match="applicability"):
        validate_profile(config)


def test_automatic_selection_requires_unique_verified_parameter_contract():
    config = profile()
    binding = parameterized(config)
    config["queries"]["D02"]["selected_binding"] = None
    assert (
        query_definition(config, "D02", "new-region")["selection_method"]
        == "automatic_verified"
    )
    config["auto_select_verified_bindings"] = False
    assert (
        query_definition(config, "D02", "new-region")["reason"] == "binding_unselected"
    )
    config["auto_select_verified_bindings"] = True
    config["clusters"]["new-region"] = {"bindings": {"D02": None}}
    assert (
        query_definition(config, "D02", "new-region")["reason"] == "binding_unselected"
    )
    config["clusters"] = {}
    other = "alternative.D02"
    config["bindings"][other] = copy.deepcopy(binding)
    config["bindings"][other]["equivalence_evidence_refs"] = ["fixture-equivalence"]
    config["queries"]["D02"]["binding_candidates"].append(other)
    validate_profile(config)
    resolved = query_definition(config, "D02", "new-region")
    assert resolved["availability"] == "unavailable"
    assert resolved["selection_reason"] == "multiple_verified_candidates"
    config["queries"]["D02"]["selected_binding"] = other
    assert query_definition(config, "D02", "new-region")["binding_id"] == other


def test_literal_or_unevidenced_alternative_is_not_automatically_selected():
    config = profile()
    verified(config)
    config["queries"]["D02"]["selected_binding"] = None
    assert query_definition(config, "D02", "fixture")["reason"] == "binding_unselected"
    binding = parameterized(config)
    config["queries"]["D02"]["selected_binding"] = None
    other = "alternative.D02"
    config["bindings"][other] = copy.deepcopy(binding)
    config["queries"]["D02"]["binding_candidates"].append(other)
    binding["verification"]["status"] = "candidate"
    assert (
        query_definition(config, "D02", "new-region")["reason"] == "binding_unselected"
    )


async def test_parameter_does_not_activate_candidate():
    config = profile()
    data = {
        **DATA,
        "scope": {"clusters": [{"cluster_id": "new-cpc", "namespaces": None}]},
    }
    obs = Observation({}, config, data, time.monotonic() + 30)
    assert (await obs.collect("D02"))[0]["quality"]["reason"] == "binding_unselected"
    assert obs.calls == obs.discovery_calls == 0


async def test_ksm_gauge_remains_node_observation_for_both_consumers():
    config = profile()
    binding = parameterized(config, "D20", unit="boolean")
    binding["target_labels"] = {
        "node": "node",
        "condition": "condition",
        "status": "status",
    }

    async def query(args):
        return {
            "data": [
                {
                    "metric": {
                        "node": "fixture-node",
                        "condition": "Ready",
                        "status": "true",
                    },
                    "values": [[START, "1"], [START + 15, "1"]],
                }
            ]
        }

    data = {
        **DATA,
        "group_by": ["cluster"],
        "incident_time": PERIOD["end"],
        "target": {},
    }
    obs = Observation({"query_prometheus": query}, config, data, time.monotonic() + 30)
    collected = {"D20": await obs.collect("D20")}
    assert calculate("O01", data, collected, {}, {}, profile=config)["quality"][
        "node_condition_observations"
    ]
    assert not normalized_state(obs, collected, data, config, {})[0]
