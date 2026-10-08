"""Authored auxiliary query plans exercise the worker with local fixtures."""

import json
from pathlib import Path
import time
from uuid import uuid4

import pytest

from agent_common.contracts import content_hash, validate_result
from agent_common.runtime import attempt_context
from agent_common.query_contract import query_definition, query_facts
from agent_common.observation import Observation
from rcca_agent.workflow import run
from test_discovery import Grafana


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("query", ["D04", "D11", "D33", "D34", "D44"])
@pytest.mark.parametrize("fault", ["missing_gpu_mapping", "ambiguous_datasource"])
async def test_auxiliary_query_never_broadens_unresolved_scope(query, fault):
    profile = json.loads((ROOT / "agents/config.example.json").read_text("utf-8"))
    binding = query_definition(profile, query, "new-cluster-fixture")
    grafana = Grafana()
    grafana.labels = {("metrics", "cluster_id"): ["new-cluster-fixture"]}
    if fault == "missing_gpu_mapping":
        profile["bindings"][binding["binding_id"]]["target_labels"].pop("gpu_uuid")
    else:
        grafana.sources.append({"uid": "duplicate", "type": "prometheus"})
        grafana.labels[("duplicate", "cluster_id")] = ["new-cluster-fixture"]
    data = dict(
        scope={"clusters": [{"cluster_id": "new-cluster-fixture", "namespaces": None}]},
        target={"gpu_uuid": "GPU-1", "node": "node-1"},
        time_range={"start": "2026-09-15T00:00:00Z", "end": "2026-09-15T00:01:00Z"},
    )
    if fault == "missing_gpu_mapping":
        with pytest.raises(ValueError, match="scope entity labels"):
            Observation(grafana.tools(), profile, data, time.monotonic() + 30)
        assert grafana.calls == []
        return
    obs = Observation(grafana.tools(), profile, data, time.monotonic() + 30)
    evidence = await obs.collect(query)
    assert evidence and all(e["tool_status"] != "ok" for e in evidence)
    assert all(e["quality"].get("reason") for e in evidence)
    assert not any(name == "query_prometheus" for name, _ in grafana.calls)


@pytest.mark.parametrize(
    "query,unit",
    [
        ("D04", "celsius"),
        ("D11", "W"),
        ("D44", "count"),
        ("D33", "bytes_per_second"),
        ("D34", "bytes_per_second"),
    ],
)
def test_current_binding_is_parameterized_observation_not_health(query, unit):
    profile = json.loads((ROOT / "agents/config.example.json").read_text("utf-8"))
    resolved = query_definition(profile, query, "new-cluster-fixture")
    assert resolved["availability"] == "verified"
    assert resolved["unit"] == unit
    assert resolved["environment"]["cluster_id"] == "new-cluster-fixture"
    assert "cluster_id" in resolved["environment"]["scope_labels"]
    assert query_facts(query) == {"observations"}
    profile["bindings"][resolved["binding_id"]]["verification"]["status"] = "candidate"
    assert (
        query_definition(profile, query, "new-cluster-fixture")["availability"]
        == "unavailable"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code,query",
    [
        (54, "D11"),
        (163, "D04"),
        (32, "D44"),
        (79, "D44"),
        (74, "D33"),
    ],
)
@pytest.mark.parametrize("mode", ["samples", "empty", "failed"])
@pytest.mark.parametrize("profile_kind", ["legacy_fixture", "current"])
async def test_power_followup_never_establishes_health_or_recovery(
    code, query, mode, profile_kind
):
    profile = json.loads(
        (ROOT / "agents/tests/fixtures/config-v7.json").read_text("utf-8")
    )
    profile["clusters"] = {
        "fixture-cluster": {
            "mimir_uid": "m",
            "metric_selector": {},
            "loki_uid": "l",
            "loki_selector": {},
        }
    }
    # Explicit fixture sources for new queries not present in the v7 profile.
    for query_id, unit in (
        ("D44", "count"),
        ("D33", "bytes_per_second"),
        ("D34", "bytes_per_second"),
    ):
        profile["queries"][query_id] = dict(
            source="mimir",
            metric="fixture_" + query_id.lower(),
            unit=unit,
            revision="fixture-v1",
            validated=True,
            max_hold_seconds=30,
            target_labels={"gpu_uuid": "uuid", "node": "node"},
        )
    if profile_kind == "current":
        profile = json.loads((ROOT / "agents/config.example.json").read_text("utf-8"))
    book = json.loads(
        (ROOT / f"rcca-agent/runbooks/xid/RB-XID-{code}.json").read_text("utf-8")
    )
    book.update(
        id="fixture-book", revision=1, compatibility={"cluster_id": "fixture-cluster"}
    )
    book.update(
        content_hash=content_hash(book["content"]),
        reviewed_content_hash=content_hash(book["content"]),
    )
    period = {"start": "2026-09-15T00:00:00Z", "end": "2026-09-15T00:01:00Z"}
    data = dict(
        incident_id=str(uuid4()),
        evidence_version=1,
        scope={"clusters": [{"cluster_id": "fixture-cluster", "namespaces": None}]},
        target={"gpu_uuid": "GPU-1", "node": "node-1"},
        incident_time=period["start"],
        time_range=period,
        incident_snapshot={"alert": {"annotations": {"summary": f"Xid {code}"}}},
    )

    async def logs(args):
        return {"data": {"result": []}}

    async def metrics(args):
        if profile_kind == "current":
            assert 'cluster_id="fixture-cluster"' in args["expr"]
            assert 'uuid="GPU-1"' in args["expr"]
            assert 'node="node-1"' in args["expr"]
        if mode == "failed":
            raise OSError("fixture unavailable")
        return {
            "data": {
                "result": []
                if mode == "empty"
                else [
                    {
                        "metric": {"uuid": "GPU-1", "node": "node-1"},
                        "values": [[1789430400, "40"], [1789430415, "41"]],
                    }
                ]
            }
        }

    class Model:
        configured = False
        usage = {}

    grafana = Grafana()
    grafana.labels = {
        ("metrics", "cluster_id"): ["fixture-cluster"],
        ("logs", "cluster_id"): ["fixture-cluster"],
    }
    tools = grafana.tools()
    tools.update(query_prometheus=metrics, query_loki_logs=logs)

    token = attempt_context.set(
        dict(
            claim=dict(
                job_id=str(uuid4()),
                kind="rca",
                input=data,
                versions={"input_contract": "1.5"},
            ),
            profile=profile,
            context=dict(data_cutoff_at=period["end"], runbooks=[book], incidents=[]),
            deadline=time.monotonic() + 30,
            llm=Model(),
        )
    )
    try:
        output = await run(tools)
    finally:
        attempt_context.reset(token)
    result = output["result"]
    validate_result(result, output["evidence"])
    followup = [e for e in output["evidence"] if e["query_id"] == query]
    assert followup
    if profile_kind == "current":
        assert all(e["quality"].get("binding_id") for e in followup)
    if mode == "empty":
        assert all(e["tool_status"] == "empty" for e in followup)
    elif mode == "failed":
        assert all(e["tool_status"] not in ("ok", "empty") for e in followup)
    else:
        assert any(e["tool_status"] == "ok" for e in followup)
    assert result["result_status"] != "ready"
    assert "normalized_health" in result["missing_inputs"]
    assert not any(
        c["causal_status"] == "confirmed" for c in result["cause_candidates"]
    )
    assert not any(r["eligibility"] == "eligible" for r in result["recommendations"])
