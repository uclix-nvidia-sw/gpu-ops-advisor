"""Environment selection and consumer regressions; transport responses are fixtures."""

import json
from pathlib import Path
import time

import pytest

from agent_common.settings import Settings
from agent_common.query_contract import query_definition, validate_profile
from agent_common.observation import Observation
from ops_agent.workflow import calculate
from rcca_agent.workflow import normalized_state

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "agents/config.cpc-direct.json"
SELECTED = {"D02", "D03", "D06", "D10", "D15", "D20", "D22"}
PERIOD = {"start": "2026-10-06T08:15:00Z", "end": "2026-10-06T08:16:00Z"}


def test_both_workers_load_same_environment_profile(monkeypatch):
    monkeypatch.setenv("AGENT_CONFIG_FILE", str(PROFILE))
    config = Settings("rca").profile()
    assert config == Settings("report").profile()
    validate_profile(config)
    for cluster in ("cpc-1", "cpc-2"):
        assert set(config["clusters"][cluster]["bindings"]) == SELECTED
        for query in SELECTED:
            binding = query_definition(config, query, cluster)
            assert (
                binding["environment"]["selector"]["collection_path"] == "alloy-direct"
            )
            assert binding["environment"]["cluster_id"] == cluster
    assert query_definition(config, "D02", "unknown")["reason"] == "binding_unselected"


@pytest.mark.parametrize("cluster", ["cpc-1", "cpc-2", "unknown"])
async def test_unselected_logs_never_call_remote(cluster):
    config = json.loads(PROFILE.read_text("utf-8"))
    data = {
        "scope": {"clusters": [{"cluster_id": cluster, "namespaces": None}]},
        "time_range": PERIOD,
    }
    obs = Observation({}, config, data, time.monotonic() + 30)
    result = await obs.collect("D09")
    assert result[0]["quality"]["reason"] == "binding_unselected"
    assert obs.calls == 0


async def test_real_ksm_gauge_type_reaches_report_without_becoming_gpu_health():
    config = json.loads(PROFILE.read_text("utf-8"))
    data = {
        "scope": {"clusters": [{"cluster_id": "cpc-1", "namespaces": None}]},
        "time_range": PERIOD,
        "group_by": ["cluster"],
        "incident_time": PERIOD["end"],
        "target": {},
    }

    async def query(args):
        assert args["expr"].startswith("kube_node_status_condition{")
        assert 'collection_path="alloy-direct"' in args["expr"]
        return {
            "data": [
                {
                    "metric": {
                        "node": "fixture-node",
                        "condition": "Ready",
                        "status": "true",
                    },
                    "values": [[1791274500, "1"], [1791274515, "1"]],
                }
            ]
        }

    obs = Observation({"query_prometheus": query}, config, data, time.monotonic() + 30)
    collected = {"D20": await obs.collect("D20")}
    result = calculate("O01", data, collected, {}, {}, profile=config)
    assert result["quality"]["node_condition_observations"]
    state = normalized_state(obs, collected, data, config, {})
    assert not state[0]


@pytest.mark.parametrize("cluster", ["cpc-1", "cpc-2"])
def test_dcgm_sentinels_are_rejected_by_range(cluster):
    from agent_common.binding_samples import sample_value

    config = json.loads(PROFILE.read_text("utf-8"))
    for query in ("D02", "D03", "D15"):
        binding = query_definition(config, query, cluster)
        assert sample_value(9223372036854775807, binding) is None
        assert sample_value(float("nan"), binding) is None
        assert sample_value(-1, binding) is None
        assert sample_value(0, binding) == 0
