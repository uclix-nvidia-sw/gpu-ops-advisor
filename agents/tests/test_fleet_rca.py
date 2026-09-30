import copy
import json
from pathlib import Path
import time
from uuid import uuid4

import pytest

from agent_common.contracts import timestamp, validate_result
from agent_common.observation import usable_observation
from agent_common.parsers import parse_health, health_facts
from agent_common.runtime import attempt_context
from rcca_agent.synthesis import synthesis_input
from rcca_agent.workflow import run
from test_rca_analysis import general_runbook, analysis_reply


def profile():
    return json.loads(
        (Path(__file__).resolve().parents[2] / "agents/config.example.json").read_text()
    )


def fleet():
    return {
        "attributes": {
            "component": "accelerator-nvidia-error-sxid",
            "health": "Unhealthy",
            "log_type": "component_data",
            "reason": "SXID 11001(ingress invalid command)",
        },
        "resources": {"machine.id": "machine-1", "k8s.node.name": "node-1"},
    }


PERIOD = {"start": "2026-09-30T05:08:45.123505Z", "end": "2026-09-30T05:08:46.123505Z"}
REQUEST = {"start": "2026-09-30T05:08:45.124Z", "end": "2026-09-30T05:08:46.123Z"}
NS = str(int(timestamp("2026-09-30T05:08:46Z")) * 1_000_000_000)


def evidence(raw=None, ns=NS):
    return dict(
        id="log",
        query_id="D09",
        cluster_id="c",
        time_range=PERIOD,
        tool_status="partial",
        quality={
            "complete": False,
            "reason": "time_precision_reduced",
            "observation_usable": True,
            "request_time_range": REQUEST,
        },
        snapshot={
            "data": {
                "result": [{"stream": {}, "values": [[ns, json.dumps(raw or fleet())]]}]
            }
        },
    )


def test_fleet_report_time_is_not_device_observation_time():
    p = profile()
    e = evidence()
    before = copy.deepcopy(e)
    health = parse_health([e], p["health_contracts"], p["queries"])
    assert e == before
    assert health[0]["normalized_health"] == "unhealthy"
    assert health[0]["error_code"] == "sxid:11001"
    assert health[0]["time_basis"] == "loki_recorded_at"
    assert health[0]["loki_timestamp_ns"] == NS
    mcp_evidence = copy.deepcopy(e)
    mcp_evidence["snapshot"] = {
        "data": [{"timestamp": NS, "line": json.dumps(fleet()), "labels": {}}]
    }
    assert parse_health([mcp_evidence], p["health_contracts"], p["queries"]) == health
    target = {
        "machine_id": "machine-1",
        "k8s_node_name": "node-1",
        "cluster_id": "c",
        "alertname": "GPUAlert",
    }
    assert health_facts(health, target) == {}
    # Only an explicitly verified producer time contract enables fact promotion.
    p["health_contracts"]["fleet-component-log-v1"]["loki_timestamp_is_observed_at"] = (
        True
    )
    health = parse_health([e], p["health_contracts"], p["queries"])
    assert health_facts(health, target)["error_code"] == "sxid:11001"
    assert health_facts(health, {**target, "machine_id": "other"}) == {}
    assert health_facts(health, {"cluster_id": "c", "alertname": "GPUAlert"}) == {}
    data = {"incident_time": PERIOD["end"], "scope": {}, "purpose_ids": ["R01"]}
    assert synthesis_input(data, [e], health, [], [])["observation_refs"] == ["log"]
    for reason in (
        "sample_limit_exceeded",
        "source_warning",
        "response_byte_limit",
        "query_failed",
    ):
        bad = copy.deepcopy(e)
        bad["quality"]["reason"] = reason
        assert not usable_observation(bad)
        assert synthesis_input(data, [bad], health, [], [])["observation_refs"] == []


def test_registered_native_health_coexists_with_fleet_adapter():
    p = profile()
    p["health_contracts"]["native"] = dict(
        producer_contract="native",
        revision="v1",
        checks={"valid": "valid"},
        health={"Healthy": {"normalized_health": "healthy", "severity": "info"}},
    )
    raw = dict(
        producer_contract="native",
        health="Healthy",
        check_status="valid",
        target={"node": "node-1"},
        component="gpu",
        observed_at="2026-09-30T05:08:46Z",
    )
    health = parse_health([evidence(raw)], p["health_contracts"], p["queries"])
    assert health[0]["normalized_health"] == "healthy"
    assert health[0]["producer_contract"] == "native"


@pytest.mark.parametrize(
    "change",
    [
        "missing_machine",
        "wrong_component",
        "wrong_kind",
        "timestamp",
        "outside",
        "namespace",
        "multiple_codes",
        "unknown_health",
    ],
)
def test_fleet_rejects_missing_identity_time_and_ambiguous_codes(change):
    p, raw, ns = profile(), fleet(), NS
    if change == "missing_machine":
        raw["resources"].pop("machine.id")
    if change == "wrong_component":
        raw["attributes"]["component"] = "other"
    if change == "wrong_kind":
        raw["attributes"]["log_type"] = "other"
    if change == "timestamp":
        ns = "not-a-time"
    if change == "outside":
        ns = str(int(timestamp("2026-09-30T05:08:47Z")) * 1_000_000_000)
    if change == "namespace":
        raw["attributes"]["reason"] = "XID 79"
    if change == "multiple_codes":
        raw["attributes"]["reason"] = "SXID 11001 SXID 11002"
    if change == "unknown_health":
        raw["attributes"]["health"] = "Unregistered"
    health = parse_health([evidence(raw, ns)], p["health_contracts"], p["queries"])
    if change in ("namespace", "multiple_codes"):
        assert health[0]["error_code"] is None
    elif change == "unknown_health":
        assert health[0]["normalized_health"] == "unknown"
    else:
        assert health == []


@pytest.mark.asyncio
async def test_fractional_fleet_logs_degraded_followup_and_r02_plan():
    p = profile()
    p["clusters"] = {
        "c": {
            "loki_uid": "logs",
            "loki_selector": {},
            "mimir_uid": "metrics",
            "metric_selector": {},
        }
    }
    data = dict(
        incident_id=str(uuid4()),
        evidence_version=1,
        incident_time=PERIOD["end"],
        time_range=PERIOD,
        scope={"clusters": [{"cluster_id": "c", "namespaces": None}]},
        target={"cluster_id": "c", "alertname": "GPUAlert"},
        purpose_ids=["R01", "R02"],
        incident_snapshot={
            "alert": {
                "labels": {
                    "machine_id": "machine-1",
                    "k8s_node_name": "node-1",
                    "component": "accelerator-nvidia-error-sxid",
                    "reason": "SXID 11001",
                }
            }
        },
    )
    original = copy.deepcopy(data)
    calls = []

    async def logs(args):
        assert (
            args["startRfc3339"] == REQUEST["start"]
            and args["endRfc3339"] == REQUEST["end"]
        )
        calls.append("logs")
        return {
            "data": {
                "result": [
                    {
                        "stream": {},
                        "values": [[NS, json.dumps(fleet())] for _ in range(31)],
                    }
                ]
            }
        }

    async def metrics(args):
        calls.append(args["expr"].split("{")[0])
        return {"data": {"result": []}}

    class Model:
        configured = True
        usage = {}

        async def complete(self, system, payload, **kwargs):
            assert not kwargs.get(
                "tools"
            )  # Degraded followup is deterministic and independent.
            if "facts" in payload:
                return {"fact_ids": [s["id"] for s in payload["facts"]]}
            assert (
                payload["observation_refs"]
                and len(payload["device_observations"]) == 62
            )
            return analysis_reply(payload["observation_refs"])

    token = attempt_context.set(
        dict(
            claim={
                "job_id": str(uuid4()),
                "kind": "rca",
                "input": data,
                "versions": {},
            },
            profile=p,
            context={
                "data_cutoff_at": PERIOD["end"],
                "runbooks": [general_runbook()],
                "incidents": [],
            },
            deadline=time.monotonic() + 30,
            llm=Model(),
        )
    )
    try:
        output = await run({"query_loki_logs": logs, "query_prometheus": metrics})
    finally:
        attempt_context.reset(token)
    assert data == original
    validate_result(output["result"], output["evidence"])
    collected = {
        e["query_id"] for e in output["evidence"] if e["query_id"].startswith("D")
    }
    assert {"D05", "D09", "D08", "D06", "D02"} <= collected
    assert calls.count("logs") == 2
    result = output["result"]
    assert result["quality"]["analysis"]["status"] == "complete"
    assert result["quality"]["analysis"]["sufficiency"] == "degraded"
    assert "mapping_target_unverified" in result["missing_inputs"]
    assert not result["pod_relations"] and result["result_status"] != "ready"
    assert all(c["causal_status"] == "candidate" for c in result["cause_candidates"])
