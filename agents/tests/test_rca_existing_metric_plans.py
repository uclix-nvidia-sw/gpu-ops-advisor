"""Existing verified bindings reach RCA comparisons without changing Ops plans."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from agent_common.contracts import content_hash
from rcca_agent.incident_dossier import component_view
from rca_replay import replay
from test_rca_incident_dossier import dossier_case


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("code", ["10004", "10005"])
async def test_thermal_sxid_collects_existing_optional_metrics_in_one_round(code):
    case = json.loads(json.dumps(dossier_case("sxid")).replace("11001", code))
    book = case["attempt"]["context"]["runbooks"][0]
    book["content"] = json.loads(
        (ROOT / f"rcca-agent/runbooks/sxid/RB-SXID-{code}.json").read_text("utf-8")
    )["content"]
    book["content_hash"] = book["reviewed_content_hash"] = content_hash(book["content"])
    profile = case["attempt"]["profile"]
    for step in book["content"]["observation_plan"]:
        query = step["query_id"]
        if query not in profile["queries"]:
            profile["queries"][query] = deepcopy(profile["queries"]["D44"])
            profile["queries"][query]["metric"] = "fixture_" + query
    case["token_budget"] = 0
    result = await replay(case)
    evidence = result["output"]["evidence"]
    assert {"D61", "D45", "D11"} <= {row["query_id"] for row in evidence}
    for query in ("D61", "D45", "D11"):
        assert any(
            profile["queries"][query]["metric"] in json.dumps(call["arguments"])
            for call in result["query_calls"]
            if call["tool"] == "query_prometheus"
        )
        assert any(
            row["query_id"] == query and row["tool_status"] in {"ok", "empty"}
            for row in evidence
        )
    assert all(
        not step["required"]
        for step in book["content"]["observation_plan"]
        if step["query_id"] in {"D61", "D45", "D11"}
    )
    assert len(result["query_calls"]) <= profile["limits"]["max_queries"]


@pytest.mark.parametrize(
    "query,name", [("D31", "GPU PCIe 수신 속도"), ("D32", "GPU PCIe 송신 속도")]
)
def test_pcie_rates_keep_units_scope_and_before_after_values(query, name):
    data = {
        "scope": {"clusters": [{"cluster_id": "test-cluster"}]},
        "target": {"node": "node-1"},
        "time_range": {"start": "2026-10-23T08:00:00Z", "end": "2026-10-23T08:30:00Z"},
        "incident_time": "2026-10-23T08:19:00Z",
    }
    evidence = {
        "id": "ev-pcie",
        "query_id": query,
        "cluster_id": "test-cluster",
        "tool_status": "ok",
        "quality": {
            "complete": True,
            "original_samples": True,
            "unit": "bytes_per_second",
        },
        "snapshot": {
            "data": {
                "result": [
                    {
                        "metric": {"node": "node-1", "uuid": "GPU-1"},
                        "values": [[1792742460, "100"], [1792743900, "300"]],
                    },
                    {
                        "metric": {"node": "other-node", "uuid": "GPU-2"},
                        "values": [[1792742460, "900"]],
                    },
                ]
            }
        },
    }
    view = component_view(data, [evidence], [], "accelerator-nvidia-dcgm-pcie")
    assert len(view["metrics"]) == 1
    metric = view["metrics"][0]
    assert metric["name"] == name
    assert metric["unit"] == "bytes_per_second"
    assert metric["kind"] == "gauge"
    assert metric["incident_windows"]["before"]["last_value"] == 100
    assert metric["incident_windows"]["at_or_after"]["last_value"] == 300
