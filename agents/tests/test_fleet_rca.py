import copy
import json
from pathlib import Path
import time
from uuid import uuid4

import pytest

from agent_common.contracts import content_hash, timestamp, validate_result
from agent_common.observation import usable_observation
from agent_common.parsers import parse_health, health_facts
from agent_common.runtime import attempt_context
from rcca_agent.synthesis import synthesis_input
from rcca_agent.workflow import run
from test_rca_analysis import general_runbook, analysis_reply


def profile():
    return json.loads(
        (
            Path(__file__).resolve().parents[2] / "agents/tests/fixtures/config-v7.json"
        ).read_text()
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


def test_repeated_fleet_report_is_not_a_new_device_event_or_gpu_mapping():
    p, raw = profile(), fleet()
    raw["attributes"]["time"] = "2026-09-29T05:00:00Z"
    raw["resources"]["gpuInfo.gpus"] = [{"uuid": "GPU-inventory-only"}]
    first = evidence(raw)
    second = evidence(raw, str(int(NS) + 1_000_000))
    second["id"] = "later-report"
    observations = parse_health([first, second], p["health_contracts"], p["queries"])
    assert len(observations) == 2  # Reports, not two newly occurring SXID events.
    assert all(h["error_code"] == "sxid:11001" for h in observations)
    assert all(h["time_basis"] == "loki_recorded_at" for h in observations)
    assert all(not h["fact_eligible"] for h in observations)
    assert all("gpu_uuid" not in h["target"] for h in observations)
    assert all(not h["gpu_candidates"][0]["verified"] for h in observations)
    assert health_facts(observations, {"node": "node-1", "cluster_id": "c"}) == {}


def test_nonregistered_disk_report_does_not_gain_xid_health_contract():
    p, raw = profile(), fleet()
    raw["attributes"].update(component="disk", reason="synthetic disk error")
    assert parse_health([evidence(raw)], p["health_contracts"], p["queries"]) == []


@pytest.mark.parametrize("component,code", [("xid", 79), ("sxid", 11001)])
def test_zero_component_time_and_string_inventory_are_not_device_facts(component, code):
    p, raw = profile(), fleet()
    raw["attributes"].update(
        component=f"accelerator-nvidia-error-{component}",
        reason=f"{component.upper()} {code} detected on PCI:0000:01:00",
        time="0001-01-01 00:00:00 +0000 UTC",
    )
    raw["resources"]["gpuInfo.gpus"] = json.dumps(
        [{"uuid": "GPU-fixture", "busID": "0000:07:00.0"}]
    )
    observations = parse_health([evidence(raw)], p["health_contracts"], p["queries"])
    assert observations[0]["error_code"] == f"{component}:{code}"
    assert observations[0]["fact_eligible"] is False
    assert "gpu_uuid" not in observations[0]["target"]
    assert health_facts(observations, {"node": "node-1", "cluster_id": "c"}) == {}


def test_structured_error_event_is_not_a_component_health_snapshot():
    p, raw = profile(), fleet()
    raw["attributes"].update(
        log_type="event",
        event_name="error_sxid",
        event_type="Fatal",
        extra_info={"data": {"time": "2026-09-30T05:08:46Z", "sxid": 11001}},
    )
    # Even with health/reason fields present, event severity cannot establish health.
    assert parse_health([evidence(raw)], p["health_contracts"], p["queries"]) == []


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
@pytest.mark.parametrize("include_event", [False, True])
async def test_fractional_fleet_logs_degraded_followup_and_r02_plan(include_event):
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
    from test_fleet_events import event

    raw_event = event()
    raw_event["attributes"].update(
        component="accelerator-nvidia-error-sxid", event_name="error_sxid"
    )
    detail = raw_event["attributes"]["extra_info"]["data"]
    detail.pop("xid")
    detail.update(sxid=11001, raw_kmsg="SXID 11001")
    event_rows = [[NS, json.dumps(raw_event)]] if include_event else []

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
                        "values": event_rows
                        + [
                            [str(int(NS) + i * 1000), json.dumps(fleet())]
                            for i in range(31)
                        ],
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
                and 0 < len(payload["device_observations"]) <= 31
            )
            assert len(payload["error_events"]) == int(include_event)
            if include_event:
                assert payload["error_events"][0]["fact_eligible"] is False
            assert (
                len(payload["device_observations"])
                + payload["context_selection"]["omitted_observations"][
                    "device_observations"
                ]
                == 31
            )
            return analysis_reply(payload["observation_refs"])

    book = general_runbook()
    book["content"]["required_evidence"].append("incident_mapping")
    for q in ("D08", "D06"):
        book["content"]["required_queries"].append(q)
        book["content"]["observation_plan"].append(
            dict(
                query_id=q,
                priority=4,
                required=True,
                fact_names=["incident_mapping"],
                purpose="Verify incident mapping",
                binding="execution_profile",
                time_range="incident",
                freshness="query_contract",
            )
        )
    book.update(
        content_hash=content_hash(book["content"]),
        reviewed_content_hash=content_hash(book["content"]),
    )
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
                "runbooks": [book],
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
    assert {"D09", "D08", "D06", "D02"} <= collected
    assert calls.count("logs") == 1
    result = output["result"]
    assert len(result["quality"]["analysis"]["error_events"]) == int(include_event)
    assert len(result["device_observations"]) == 31
    diagnostics = result["quality"]["analysis"]["synthesis"]
    assert diagnostics["input_bytes"] <= 64000
    assert (
        diagnostics["context_selection"]["omitted_observations"]["device_observations"]
        > 0
    )
    synthesis_evidence = next(
        e for e in reversed(output["evidence"]) if e["query_id"] == "rca_synthesis"
    )
    assert synthesis_evidence["snapshot"]["diagnostics"] == diagnostics
    assert result["quality"]["analysis"]["status"] == "complete"
    assert result["quality"]["analysis"]["sufficiency"] == "degraded"
    assert "mapping_target_unverified" in result["missing_inputs"]
    assert not result["pod_relations"] and result["result_status"] != "ready"
    assert all(c["causal_status"] == "candidate" for c in result["cause_candidates"])


@pytest.mark.parametrize(
    "inventory",
    [
        '[{"uuid":"GPU-a","busID":"0000:08:00.0"}]',
        [{"uuid": "GPU-a", "busID": "0000:08:00.0"}],
    ],
)
def test_rca_inventory_string_preserves_unverified_health_and_original(inventory):
    from rcca_agent.fleet_events import enrich_report_inventory

    raw = fleet()
    raw["resources"]["gpuInfo.gpus"] = inventory
    e = evidence(raw)
    before = copy.deepcopy(e)
    p = profile()
    health = parse_health([e], p["health_contracts"], p["queries"])
    enriched = enrich_report_inventory(health, [e])
    assert enriched[0]["gpu_candidates"][0]["gpu_uuid"] == "GPU-a"
    assert enriched[0]["gpu_candidates"][0]["verified"] is False
    assert enriched[0]["fact_eligible"] is False
    assert (
        health_facts(
            enriched, {"machine_id": "machine-1", "node": "node-1", "cluster_id": "c"}
        )
        == {}
    )
    assert e == before


@pytest.mark.parametrize("inventory", ["invalid", '{"uuid":"GPU-a"}', None, 42])
def test_rca_inventory_rejects_non_array(inventory):
    from rcca_agent.fleet_events import enrich_report_inventory

    raw = fleet()
    raw["resources"]["gpuInfo.gpus"] = inventory
    p = profile()
    e = evidence(raw)
    health = parse_health([e], p["health_contracts"], p["queries"])
    assert enrich_report_inventory(health, [e])[0]["gpu_candidates"] == []


@pytest.mark.parametrize(
    "address,relation",
    [
        ("PCI:0000:01:00", "not_in_reported_inventory"),
        ("PCI:0000:08:00", "inventory_candidate_only"),
    ],
)
def test_report_pci_comparison_never_promotes_device_identity(address, relation):
    from rcca_agent.fleet_events import enrich_report_inventory

    raw = fleet()
    raw["attributes"]["component"] = "accelerator-nvidia-error-xid"
    raw["attributes"]["reason"] = "XID 79"
    raw["attributes"]["reason"] += " " + address
    raw["resources"]["gpuInfo.gpus"] = '[{"uuid":"GPU-a","busID":"0000:08:00.0"}]'
    e = evidence(raw)
    p = profile()
    health = parse_health([e], p["health_contracts"], p["queries"])
    enriched = enrich_report_inventory(health, [e])[0]
    assert enriched["pci_inventory_relation"] == relation
    assert enriched["fact_eligible"] is False
    assert enriched["gpu_candidates"][0]["verified"] is False


GPU_UUID = "GPU-00000000-0000-4000-8000-000000000001"
REASONS = {
    "xid": "XID 79 GPU has fallen off the bus detected on GPU PCI:0000:01:00"
    f" UUID:{GPU_UUID}",
    "sxid": "SXID 11001(ingress invalid command) detected on PCI:0000:c7:00.0",
}
DEVICES = {"xid": "PCI:0000:01:00", "sxid": "PCI:0000:c7:00.0"}
CODES = {"xid": "xid:79", "sxid": "sxid:11001"}


def alert(kind="xid"):
    return {
        "component": "accelerator-nvidia-error-" + kind,
        "machine_id": "machine-1",
        "k8s_node_name": "node-1",
        "reason": REASONS[kind],
        "error_codes": [CODES[kind]],
    }


def state_report(kind="xid", **change):
    return {
        "raw_health": "Unhealthy",
        "component": "accelerator-nvidia-error-" + kind,
        "target": {"machine_id": "machine-1", "node": "node-1"},
        "reason": REASONS[kind],
        "evidence_refs": ["report"],
        **change,
    }


def kmsg_event(kind="xid", **change):
    return {
        "component": "accelerator-nvidia-error-" + kind,
        "error_code": CODES[kind],
        "reported_device": DEVICES[kind],
        "inventory_gpu_candidate": GPU_UUID if kind == "xid" else None,
        "evidence_refs": ["event"],
        **change,
    }


@pytest.mark.parametrize(
    "kind,change,status",
    [
        ("xid", None, "match"),
        ("sxid", None, "match"),
        ("xid", "event_pci_function", "match"),
        ("xid", "no_code", "error_code_unparsed"),
        ("xid", "other_component_code", "error_code_unparsed"),
        ("xid", "no_report", "alert_report_not_found"),
        ("xid", "healthy_report", "alert_report_not_found"),
        ("xid", "other_machine", "alert_report_not_found"),
        ("xid", "reason", "report_reason_changed"),
        ("xid", "no_event", "event_not_found"),
        ("xid", "pci", "pci_mismatch"),
        ("sxid", "sxid_function", "pci_mismatch"),
        ("xid", "two_devices", "multiple_devices"),
        ("xid", "alert_without_uuid", "uuid_unresolved"),
        ("xid", "inventory_unmapped", "uuid_unresolved"),
        ("xid", "uuid", "uuid_mismatch"),
    ],
)
def test_alert_match_compares_report_and_event_by_error_family(kind, change, status):
    from rcca_agent.fleet_events import match_alert

    clues, reports, events = alert(kind), [state_report(kind)], [kmsg_event(kind)]
    if change == "event_pci_function":
        # XID kmsg addresses carry no PCI function; the comparison ignores it.
        events = [kmsg_event(reported_device="PCI:0000:01:00.0")]
    elif change == "no_code":
        clues["error_codes"] = []
    elif change == "other_component_code":
        clues["error_codes"] = ["sxid:11001"]
    elif change == "no_report":
        reports = []
    elif change == "healthy_report":
        reports = [state_report(raw_health="Healthy")]
    elif change == "other_machine":
        reports = [state_report(target={"machine_id": "machine-2", "node": "node-1"})]
    elif change == "reason":
        reports = [state_report(reason="XID 48 detected on GPU PCI:0000:01:00")]
    elif change == "no_event":
        events = [kmsg_event(error_code="xid:13")]
    elif change == "pci":
        events = [kmsg_event(reported_device="PCI:0000:02:00")]
    elif change == "sxid_function":
        # SXID addresses an NVSwitch function; the function is compared.
        events = [kmsg_event("sxid", reported_device="PCI:0000:c7:00.1")]
    elif change == "two_devices":
        events.append(kmsg_event(reported_device="PCI:0000:02:00"))
    elif change == "alert_without_uuid":
        clues["reason"] = reports[0]["reason"] = REASONS["xid"].split(" UUID:")[0]
    elif change == "inventory_unmapped":
        events = [kmsg_event(inventory_gpu_candidate=None)]
    elif change == "uuid":
        other = GPU_UUID.replace("0001", "0002")
        events = [kmsg_event(inventory_gpu_candidate=other)]
    result = match_alert(clues, reports, events)
    assert result["status"] == status, result
    if status == "match":
        assert result["alert"]["error_code"] == CODES[kind]
        assert result["alert"]["gpu_uuid"] == (GPU_UUID if kind == "xid" else None)
        assert set(result["evidence_refs"]) == {"report", "event"}
    if change == "no_event":
        assert result["detail"] == {"other_codes": ["xid:13"]}


def fleet_line(kind, log_type, ns):
    attributes = {"component": "accelerator-nvidia-error-" + kind, "log_type": log_type}
    if log_type == "component_data":
        attributes.update(health="Unhealthy", reason=REASONS[kind])
    else:
        at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(ns) // 10**9))
        code = int(CODES[kind].split(":")[1])
        attributes.update(
            event_name="error_" + kind,
            event_type="Fatal",
            event_id="fixture-" + kind,
            extra_info={
                "data": {
                    "time": at,
                    "data_source": "kmsg",
                    kind: code,
                    "device_uuid": DEVICES[kind],
                    "raw_kmsg": f"NVRM: {kind.upper()} ({DEVICES[kind]}): {code}",
                }
            },
        )
    inventory = [{"uuid": GPU_UUID, "busID": "00000000:01:00.0"}]
    resources = {
        "machine.id": "machine-1",
        "k8s.node.name": "node-1",
        "gpuInfo.gpus": json.dumps(inventory),
    }
    return [ns, json.dumps({"attributes": attributes, "resources": resources})]


@pytest.mark.parametrize("kind", ["xid", "sxid"])
def test_parsed_d09_report_and_event_match_the_alert(kind):
    from rcca_agent.fleet_events import enrich_report_inventory, match_alert
    from rcca_agent.fleet_events import parse_events

    p, e = profile(), evidence()
    e["snapshot"]["data"]["result"][0]["values"] = [
        fleet_line(kind, "event", NS),
        fleet_line(kind, "component_data", NS),
    ]
    health = enrich_report_inventory(
        parse_health([e], p["health_contracts"], p["queries"]), [e]
    )
    target = {"cluster_id": "c", "node": "node-1", "machine_id": "machine-1"}
    events = parse_events([e], p, target)
    assert match_alert(alert(kind), health, events)["status"] == "match"


# The D09 LogQL the workflow builds from the alert's component and node labels.
D09_LOGQL = (
    "{} | drop dsx_json_0, dsx_json_0_extracted, dsx_json_1, dsx_json_1_extracted"
    ' | json dsx_json_0="attributes[\\"component\\"]",'
    ' dsx_json_1="resources[\\"k8s.node.name\\"]" | __error__=""'
    ' | (dsx_json_0="accelerator-nvidia-error-xid"'
    ' or dsx_json_0_extracted="accelerator-nvidia-error-xid")'
    ' | (dsx_json_1="node-1" or dsx_json_1_extracted="node-1")'
)


def match_case(change=None, kind="xid"):
    from test_rca_combined_policy import policy_case

    case = policy_case(kind)
    labels = {k: v for k, v in alert(kind).items() if k != "error_codes"}
    case["attempt"]["claim"]["input"]["incident_snapshot"] = {
        "alert": {"labels": labels}
    }
    d09 = case["queries"][0]
    d09["arguments"]["logql"] = D09_LOGQL.replace("error-xid", "error-" + kind)
    start = int(d09["response"]["data"]["result"][0]["values"][0][0])
    event = fleet_line(kind, "event", str(start + 10 * 10**9))
    if change == "pci":
        event[1] = event[1].replace(DEVICES["xid"], "PCI:0000:02:00")
    d09["response"]["data"]["result"][0]["values"] = [
        event,
        fleet_line(kind, "component_data", str(start + 20 * 10**9)),
    ]
    return case


@pytest.mark.parametrize("kind", ["xid", "sxid"])
async def test_alert_match_skips_analysis_and_review_models(kind):
    from rca_replay import replay

    result = await replay(match_case(kind=kind))
    output = result["output"]["result"]
    analysis = output["quality"]["analysis"]
    assert analysis["alert_match"]["status"] == "match"
    assert analysis["collection_stop_reason"] == "alert_match"
    assert [c["stage"] for c in result["model_calls"]] == ["report_writing"]
    assert [c["matched"] for c in result["query_calls"]] == [True]
    evaluation = output["quality"]["rca_evaluation"]
    assert evaluation["review"]["reason"] == "alert_match"
    assert not any(m.startswith("synthesis_") for m in output["missing_inputs"])
    assert not any(
        c["id"] == "observed_device_symptom" for c in output["cause_candidates"]
    )
    sources = output["quality"]["report"]["source_items"]
    assert any(
        s["text"].startswith("알림과 오류·상태 로그를 비교한 결과:") for s in sources
    )
    assert output["result_status"] == "ready"
    assert not output["missing_inputs"]
    assert analysis["sufficiency"] == "sufficient"
    assert any(s["text"].startswith("이번 조사 범위 밖:") for s in sources)
    assert not any("분석 처리 상태" in s["text"] for s in sources)


async def test_alert_mismatch_collects_auxiliary_queries_before_one_analysis():
    from rca_replay import replay

    result = await replay(match_case("pci"))
    output = result["output"]
    analysis = output["result"]["quality"]["analysis"]
    assert analysis["alert_match"]["status"] == "pci_mismatch"
    assert "pci_mismatch" not in output["result"]["missing_inputs"]
    assert "pci_mismatch" in analysis["resolved_scope_gaps"]
    decision = next(
        e["snapshot"]
        for e in output["evidence"]
        if e["query_id"] == "investigation_decision"
    )
    assert decision["reason"] == "alert_mismatch"
    assert set(decision["selected_queries"]) == {"D44", "D02", "D11"}
    # Analysis and review run once, after the auxiliary batch.
    assert [c["stage"] for c in result["model_calls"]] == [
        "synthesis",
        "analysis_review",
        "report_writing",
    ]
    author = result["model_calls"][0]["input"]
    assert author["alert_match"]["status"] == "pci_mismatch"
    assert "pci_mismatch" in author["evidence_gap"]
