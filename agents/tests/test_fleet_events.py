import copy
import json
from pathlib import Path

import pytest

from agent_common.parsers import parse_health, health_facts
from rcca_agent.fleet_events import parse_events
from rcca_agent.synthesis import synthesis_input, synthesize
from rcca_agent.synthesis_context import bounded_context
from test_fleet_rca import evidence, profile, PERIOD


TARGET = {"cluster_id": "c", "node": "node-1", "machine_id": "machine-1"}


def test_current_binding_contract_and_distinct_payloads_keep_provenance():
    p = json.loads(
        (Path(__file__).resolve().parents[2] / "agents/config.example.json").read_text()
    )
    raw = event()
    first = evidence(raw)
    first["quality"]["health_contract"] = p["bindings"]["fleet_intelligence.D09"][
        "health_contract"
    ]
    raw["attributes"]["extra_info"]["data"]["error_status_hex"] = "0x00000001"
    second = evidence(raw)
    second["id"] = "changed-payload"
    second["quality"]["health_contract"] = first["quality"]["health_contract"]
    rows = parse_events([first, second], p, TARGET)
    assert len(rows) == 2
    assert rows[0]["source_payload_sha256"] != rows[1]["source_payload_sha256"]
    assert parse_events([first], p, {**TARGET, "component": "disk"}) == []


def test_event_and_transport_times_remain_separate_without_clock_correction():
    raw = event()
    raw["attributes"]["extra_info"]["data"]["time"] = "2026-09-30T05:08:45.500Z"
    row = parse_events([evidence(raw)], profile(), TARGET)[0]
    assert row["event_time"] == "2026-09-30T05:08:45.500000+00:00"
    assert (
        row["loki_timestamp_ns"]
        == evidence(raw)["snapshot"]["data"]["result"][0]["values"][0][0]
    )
    assert not row["fact_eligible"]


def test_sxid_switch_is_not_mapped_to_gpu_even_when_pci_matches():
    raw = event()
    raw["attributes"].update(
        component="accelerator-nvidia-error-sxid", event_name="error_sxid"
    )
    data = raw["attributes"]["extra_info"]["data"]
    data.pop("xid")
    data.update(
        sxid=11001,
        device_uuid="PCI:0000:07:00.0",
        raw_kmsg="SXid (PCI:0000:07:00.0): 11001, Fatal",
    )
    row = parse_events([evidence(raw)], profile(), TARGET)[0]
    assert row["error_code"] == "sxid:11001"
    assert row["inventory_gpu_candidate"] is None


def event():
    return {
        "attributes": {
            "component": "accelerator-nvidia-error-xid",
            "log_type": "event",
            "event_name": "error_xid",
            "event_type": "Fatal",
            "event_id": "fixture",
            "extra_info": {
                "data": {
                    "time": "2026-09-30T05:08:46Z",
                    "data_source": "kmsg",
                    "xid": 79,
                    "device_uuid": "PCI:0000:01:00",
                    "raw_kmsg": "NVRM: Xid (PCI:0000:01:00): 79, GPU has fallen off the bus",
                }
            },
        },
        "resources": {
            "machine.id": "machine-1",
            "k8s.node.name": "node-1",
            "gpuInfo.gpus": json.dumps(
                [{"uuid": "GPU-fixture", "busID": "0000:07:00.0"}]
            ),
        },
    }


def test_event_is_reported_history_not_health_or_device_fact():
    p, raw = profile(), event()
    e = evidence(raw)
    before = copy.deepcopy(e)
    events = parse_events([e], p, TARGET)
    assert e == before
    assert len(events) == 1
    assert events[0]["error_code"] == "xid:79"
    assert events[0]["device_mapping"] == "unresolved"
    assert events[0]["inventory_gpu_candidate"] is None
    assert not events[0]["fact_eligible"]
    assert parse_health([e], p["health_contracts"], p["queries"]) == []
    assert health_facts([], TARGET) == {}
    assert parse_events([e], p, {**TARGET, "gpu_uuid": "GPU-fixture"}) == []


@pytest.mark.parametrize(
    "change",
    [
        "time",
        "old",
        "code_bool",
        "namespace",
        "message",
        "node",
        "cluster",
        "component",
        "contract",
        "quality",
        "kind",
        "no_target",
    ],
)
def test_invalid_event_does_not_enter_model(change):
    raw, p, target = event(), profile(), dict(TARGET)
    a = raw["attributes"]
    d = a["extra_info"]["data"]
    if change == "time":
        d["time"] = "0001-01-01 00:00:00 +0000 UTC"
    if change == "old":
        d["time"] = "2026-09-29T05:08:46Z"
    if change == "code_bool":
        d["xid"] = True
    if change == "namespace":
        d["sxid"] = 11001
    if change == "message":
        d["raw_kmsg"] = "XID 48"
    if change == "node":
        target["node"] = "other"
    if change == "cluster":
        target["cluster_id"] = "other"
    if change == "component":
        a["component"] = []
    if change == "contract":
        p["health_contracts"] = {}
    if change == "kind":
        a["log_type"] = "component_data"
    if change == "no_target":
        target = {}
    e = evidence(raw)
    if change == "quality":
        e["quality"]["reason"] = "sample_limit_exceeded"
    assert parse_events([e], p, target) == []


def test_inventory_match_is_candidate_and_duplicate_exports_union_refs():
    raw, p = event(), profile()
    raw["resources"]["gpuInfo.gpus"] = [
        {"uuid": "GPU-fixture", "busID": "00000000:01:00.0"}
    ]
    first = evidence(raw)
    raw["attributes"]["event_id"] = "regenerated"
    raw["attributes"]["extra_info"] = json.dumps(raw["attributes"]["extra_info"])
    second = evidence(raw)
    second["id"] = "second"
    events = parse_events([first, second], p, TARGET)
    assert len(events) == 1
    assert events[0]["evidence_refs"] == ["log", "second"]
    assert events[0]["inventory_gpu_candidate"] == "GPU-fixture"
    assert "gpu_uuid" not in events[0]["target"]
    raw = event()
    raw["attributes"]["extra_info"]["device_uuid"] = "PCI:0000:07:00"
    assert (
        parse_events([evidence(raw)], p, TARGET)[0]["device_mapping"] == "conflicting"
    )


@pytest.mark.asyncio
async def test_event_only_synthesis_has_bounded_refs_and_no_health_promotion():
    e, p = evidence(event()), profile()
    data = {"incident_time": PERIOD["end"], "scope": {}, "target": TARGET}
    events = parse_events([e], p, TARGET)
    payload = synthesis_input(data, [e], [], [], [], events=events)
    assert payload["observation_refs"] == ["log"]
    view = bounded_context(payload, 16000)
    assert view["error_events"] == events
    assert view["device_observations"] == []

    class Model:
        configured = True
        usage = {}

        async def complete(self, system, payload, **kwargs):
            assert payload["error_events"][0]["fact_eligible"] is False
            return {
                "hypotheses": [
                    {
                        "claim": "보고된 XID 79는 추가 확인이 필요합니다.",
                        "supporting_refs": ["log"],
                        "contradicting_refs": [],
                        "missing_inputs": ["현재 장비 상태"],
                    }
                ],
                "limitations": [],
            }

    status, candidates, _ = await synthesize(Model(), payload)
    assert status == "complete"
    assert candidates[0]["causal_status"] == "candidate"
