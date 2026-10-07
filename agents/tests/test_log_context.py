"""Raw D13 context never acquires workload or health meaning from a log line."""

import copy
import time

import pytest

from agent_common.observation import Observation
from agent_common.query_contract import query_facts, validate_profile
from test_binding_contract import DATA, profile
from test_discovery import Grafana


async def test_raw_context_discovers_exact_cluster_and_preserves_limitations():
    config = profile(active_defaults=True)
    validate_profile(config)
    data = copy.deepcopy(DATA)
    data["scope"]["clusters"][0]["cluster_id"] = "new-site-93"
    grafana = Grafana()
    grafana.labels[("logs", "cluster_id")] = ["new-site-93"]
    obs = Observation(grafana.tools(), config, data, time.monotonic() + 30)
    row = (await obs.collect("D13"))[0]
    assert row["tool_status"] == "empty"
    assert row["quality"]["binding_id"] == "loki_recorded_streams.D13"
    assert row["quality"]["health_contract"] is None
    assert row["quality"]["observation_semantics"]["workload_fact_eligible"] is False
    assert query_facts("D13") == {"observations"}
    requests = [args for name, args in grafana.calls if name == "query_loki_logs"]
    assert requests[0]["logql"] == '{cluster_id="new-site-93"}'
    assert (
        config["bindings"]["workload_log_producer.D13"]["verification"]["status"]
        == "candidate"
    )


@pytest.mark.parametrize(
    "narrowing",
    [
        "node",
        "pod_uid",
        "namespace",
        "log_target",
        "projected_namespace",
        "k8s_node_name",
    ],
)
async def test_unverified_target_never_falls_back_to_cluster_wide_logs(narrowing):
    data = copy.deepcopy(DATA)
    kwargs = {}
    if narrowing == "namespace":
        data["scope"]["clusters"][0]["namespaces"] = ["training"]
    elif narrowing == "log_target":
        data["log_query_target"] = {"machine_id": "host-1"}
    elif narrowing == "projected_namespace":
        kwargs["namespace_scope"] = {"fixture": ["training"]}
    else:
        data["target"] = {narrowing: "target-1"}
    obs = Observation({}, profile(active_defaults=True), data, time.monotonic() + 30)
    row = (await obs.collect("D13", **kwargs))[0]
    assert row["quality"]["reason"] == "binding_scope_unavailable"
    assert obs.calls == obs.discovery_calls == 0


@pytest.mark.parametrize("field", ["health_fact_eligible", "workload_fact_eligible"])
def test_raw_context_cannot_be_promoted_by_configuration(field):
    config = profile(active_defaults=True)
    config["bindings"]["loki_recorded_streams.D13"]["observation_semantics"][field] = (
        True
    )
    with pytest.raises(ValueError, match="cannot promote facts"):
        validate_profile(config)
