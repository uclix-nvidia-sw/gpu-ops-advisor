"""Explicit RCA profile preparation and scoped collection; no live service calls."""

from copy import deepcopy
import time

import pytest

from agent_common.observation import Observation, series
from agent_common.query_contract import query_definition
from rcca_agent.source_profile import BINDING, fleet_util_profile
from test_binding_contract import DATA, START, profile
from test_discovery import Grafana


def test_preparation_preserves_shared_profile_and_other_bindings():
    base = profile(active_defaults=True)
    before = deepcopy(base)
    result = fleet_util_profile(base, ["fixture"], "rca-fixture-v1")
    assert base == before
    for cluster in ("fixture", "unaffected"):
        for query in base["queries"]:
            old = query_definition(base, query, cluster)
            new = query_definition(result, query, cluster)
            if cluster == "fixture" and query == "D02":
                assert new["binding_id"] == BINDING
            else:
                # Explicitly pinning the unchanged global binding changes only provenance.
                old.pop("selection_method", None)
                new.pop("selection_method", None)
                assert new == old
    assert result["bindings"][BINDING]["max_hold"]["seconds"] == 0
    assert result["bindings"][BINDING]["health_contract"] is None
    assert result["bindings"][BINDING]["unit"] == "percent"
    for clusters, revision in (
        ([], "new"),
        ([""], "new"),
        (["fixture"], base["revision"]),
    ):
        with pytest.raises(ValueError):
            fleet_util_profile(base, clusters, revision)


async def test_fleet_util_collection_keeps_uuid_scope_and_invalid_values():
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
                                    "__name__": "dcgm_fi_dev_gpu_util",
                                    "uuid": "GPU-fixture",
                                    "node": "node-fixture",
                                },
                                "values": [[START, "12"], [START + 30, "101"]],
                            }
                        ],
                    }
                }
            return await super().call(name, args)

    config = fleet_util_profile(
        profile(active_defaults=True), ["fixture"], "rca-fixture-v1"
    )
    data = deepcopy(DATA)
    data["target"] = {"node": "node-fixture", "gpu_uuid": "GPU-fixture"}
    grafana = Samples()
    grafana.labels[("metrics", "cluster_id")] = ["fixture"]
    observation = Observation(grafana.tools(), config, data, time.monotonic() + 30)
    evidence = await observation.collect("D02")
    requests = [args for name, args in grafana.calls if name == "query_prometheus"]
    assert requests
    for args in requests:
        assert "dcgm_fi_dev_gpu_util{" in args["expr"]
        assert 'cluster_id="fixture"' in args["expr"]
        assert 'uuid="GPU-fixture"' in args["expr"]
        assert 'node="node-fixture"' in args["expr"]
        assert 'job="fleet-intelligence-agent"' in args["expr"]
        assert "alloy-direct" not in args["expr"]
    rows = series(evidence)
    assert rows[0]["unit"] == "percent"
    assert rows[0]["samples"][0][1] == 12
    assert all(value != 101 for row in rows for _, value in row["samples"])
