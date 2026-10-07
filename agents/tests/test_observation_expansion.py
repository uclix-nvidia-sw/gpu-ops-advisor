"""Synthetic acceptance of shared observation contracts, not production proof."""

import copy
import time

import pytest

from agent_common.binding_samples import sample_value
from agent_common.observation import Observation, series
from agent_common.query_contract import query_definition
from rcca_agent.synthesis import synthesis_input
from test_binding_contract import DATA, START, profile
from test_discovery import Grafana


@pytest.mark.parametrize(
    "query,unit,value,expected",
    [
        ("D04", "celsius", 42, 42),
        ("D16", "MiB", 81920, 81920),
        ("D17", "ratio", 0.75, 0.75),
        ("D17", "ratio", 75, None),
        ("D19", "load", 2.5, 2.5),
        ("D23", "celsius", 55, 55),
        ("D26", "ratio", 1.2, None),
        ("D31", "bytes_per_second", 4096, 4096),
        ("D36", "count", 3, 3),
        ("D44", "count", 9223372036854775794, None),
        ("D45", "bitmask", 1.5, None),
        ("D47", "enum", 0, 0),
    ],
)
async def test_fleet_contract_reaches_rca_with_units_and_time_limit(
    query, unit, value, expected
):
    config = profile(active_defaults=True)
    definition = query_definition(config, query, "new-site-91")

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
                                    "__name__": definition["metric"],
                                    "uuid": "gpu-test",
                                    "node": "node-test",
                                    "load_duration": "1m",
                                },
                                "values": [
                                    [START, str(value)],
                                    [START + 30, str(value)],
                                ],
                            }
                        ],
                    }
                }
            return await super().call(name, args)

    data = copy.deepcopy(DATA)
    data["scope"]["clusters"][0]["cluster_id"] = "new-site-91"
    data["incident_time"] = data["time_range"]["start"]
    grafana = Samples()
    grafana.labels[("metrics", "cluster_id")] = ["new-site-91"]
    evidence = await Observation(
        grafana.tools(), config, data, time.monotonic() + 30
    ).collect(query)
    metrics = series(evidence)
    assert metrics[0]["unit"] == unit
    assert metrics[0]["samples"][0][1] == expected
    assert metrics[0]["max_hold_seconds"] == 0
    assert metrics[0]["observation_semantics"]["measurement_time_verified"] is False
    payload = synthesis_input(data, evidence, [], [], [])
    assert payload["metric_observations"] == metrics
    assert payload["device_observations"] == []
    for name, args in grafana.calls:
        if name == "query_prometheus":
            assert 'cluster_id="new-site-91"' in args["expr"]
            assert 'job="fleet-intelligence-agent"' in args["expr"]
            assert definition["metric"] in args["expr"]


def test_alternatives_keep_explicit_source_equivalence_and_no_counter_rates():
    config = profile(active_defaults=True)
    for number in (*range(23, 33), 44):
        query = f"D{number:02}"
        original, alternative = config["queries"][query]["binding_candidates"]
        assert config["bindings"][original]["verification"]["status"] == "candidate"
        assert config["bindings"][alternative]["equivalence_evidence_refs"]
        resolved = query_definition(config, query, "new-site-91")
        assert resolved["producer"] == "fleet_intelligence"
    for query in ("D31", "D32", "D33", "D34"):
        resolved = query_definition(config, query, "new-site-91")
        assert resolved["sample_type"] == "gauge"
        assert resolved["counter_reset"]["mode"] == "not_applicable"
    for query in ("D36", "D37", "D38", "D39", "D40", "D41", "D42", "D43", "D44"):
        assert query_definition(config, query, "new-site-91")["counter_reset"] == {
            "mode": "reject_decrease"
        }


def test_resource_dimensions_and_ratio_definition_are_not_lost():
    config = profile(active_defaults=True)
    raw = query_definition(config, "D21", "new-site-91")
    assert raw["target_labels"]["resource"] == "resource"
    assert raw["target_labels"]["resource_unit"] == "unit"
    assert raw["target_labels"]["uid"] == "uid"
    assert (
        query_definition(config, "D07", "new-site-91")["availability"] == "unavailable"
    )
    ratio = query_definition(config, "D17", "new-site-91")
    assert "total minus reserved" in ratio["observation_semantics"]["note"]
    assert sample_value(100, ratio) is None
