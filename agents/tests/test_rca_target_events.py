"""Mixed-device evidence must not veto or evict the incident's own event."""

from copy import deepcopy
import json

import pytest

from rcca_agent.fleet_events import event_selector, match_alert
from rcca_agent.requirement_diagnostics import reported_facts
from rcca_agent.synthesis_context import bounded_context, encoded_size
from test_fleet_rca import CODES, DEVICES, alert, kmsg_event, state_report, match_case


@pytest.mark.parametrize("kind", ["xid", "sxid"])
def test_target_events_survive_other_devices_codes_and_repeated_occurrences(kind):
    target = kmsg_event(kind, evidence_refs=["target"])
    others = [
        kmsg_event(kind, reported_device="PCI:0000:02:00.0", evidence_refs=["sibling"]),
        kmsg_event(kind, error_code=kind + ":31", evidence_refs=["other-code"]),
        kmsg_event(
            kind,
            target={"machine_id": "other", "node": "node-1"},
            evidence_refs=["other-host"],
        ),
    ]
    rows = others + [target, dict(target, event_id="second")]
    before = deepcopy(rows)
    result = match_alert(
        alert(kind), [state_report(kind, reason="another error")], rows
    )
    assert result["status"] == "match"
    assert result["evidence_refs"] == ["target"]
    assert result["detail"]["matched_event_count"] == 2
    assert rows == before
    assert match_alert(alert(kind), [], others)["status"] == "event_not_found"


@pytest.mark.parametrize(
    "field,value",
    [("cluster_id", "other"), ("target", {"node": "other", "machine_id": "machine-1"})],
)
def test_same_pci_on_other_host_or_cluster_cannot_match(field, value):
    clues = dict(alert(), cluster_id="c")
    row = kmsg_event(cluster_id="c")
    row[field] = value
    assert match_alert(clues, [], [row])["status"] == "event_not_found"


def test_reported_code_selects_alert_event_from_multiple_codes():
    clues = alert()
    data = {
        "scope": {"clusters": [{"cluster_id": "c"}]},
        "target": {"node": "node-1", "machine_id": "machine-1"},
        "incident_snapshot": {"alert": {"labels": clues}},
    }
    row = kmsg_event(
        cluster_id="c",
        status="reported_event",
        producer_contract="fleet-component-log-v1",
    )
    others = [
        dict(row, error_code="xid:48"),
        dict(row, reported_device="PCI:0000:02:00"),
    ]
    result = reported_facts([], others + [row], data)
    assert result["reported_error_code"] == "xid:79"
    assert result["reported_producer_contract"] == "fleet-component-log-v1"
    assert not {"normalized_health", "error_code"} & result.keys()
    assert "reported_error_code" not in reported_facts([], others, data)


def test_other_device_or_code_health_does_not_create_target_conflict():
    from rcca_agent.workflow import conflicting_health

    target = dict(
        kmsg_event(),
        cluster_id="c",
        check_status="valid",
        observed_at="2026-01-01T00:00:00Z",
        normalized_health="unhealthy",
    )
    healthy = dict(target, normalized_health="healthy")
    selector = event_selector(alert())
    assert not conflicting_health(
        [target, dict(healthy, reported_device="PCI:0000:02:00")], selector
    )
    assert not conflicting_health(
        [target, dict(healthy, error_code="xid:92")], selector
    )
    assert conflicting_health([target, healthy], selector)


def target_payload():
    target = kmsg_event(event_time="2026-01-01T00:01:00Z", evidence_refs=["target"])
    return {
        "event_target": event_selector(alert()),
        "incident_time": "2026-01-01T00:01:01Z",
        "incident_brief": [{"evidence_refs": ["summary"], "text": "x" * 11000}],
        "error_events": [
            kmsg_event(
                reported_device=f"PCI:0000:{i:02x}:00",
                evidence_refs=["other"],
                text="x" * 2000,
            )
            for i in range(2, 18)
        ]
        + [dict(target, event_time="2026-01-01T00:00:00Z"), target],
        "observation_refs": ["target", "other", "summary"],
    }


def test_bounded_context_keeps_nearest_target_before_large_sibling_evidence():
    payload = target_payload()
    before = deepcopy(payload)
    view = bounded_context(payload, 24000)
    assert encoded_size(view) <= 24000
    assert view["error_events"][0] == payload["error_events"][-1]
    assert any(e["evidence_refs"] == ["other"] for e in view["error_events"])
    assert "target" in view["observation_refs"]
    assert view["context_selection"]["target_event"] == "retained"
    assert view["context_selection"]["omitted_observations"]["error_events"] > 0
    assert payload == before


def test_target_too_large_fails_size_gate_instead_of_silently_disappearing():
    payload = target_payload()
    payload["error_events"][-1]["text"] = "x" * 30000
    view = bounded_context(payload, 24000)
    assert view["context_selection"]["target_event"] == "budget_exceeded"
    assert encoded_size(view) > 24000
    assert payload["error_events"][-1] in view["error_events"]


@pytest.mark.parametrize("kind", ["xid", "sxid"])
async def test_workflow_mixed_errors_preserve_target_in_author_input(kind):
    from rca_replay import replay

    case = match_case(kind=kind)
    rows = case["queries"][0]["response"]["data"]["result"][0]["values"]
    event = deepcopy(rows[0])
    other = json.loads(event[1])
    detail = other["attributes"]["extra_info"]["data"]
    detail["raw_kmsg"] = detail["raw_kmsg"].replace(str(detail[kind]), "31")
    detail[kind] = 31
    other["attributes"]["event_id"] = "other-event"
    rows.insert(0, [event[0], json.dumps(other)])
    state = json.loads(rows[-1][1])
    state["attributes"]["reason"] = "another error"
    rows[-1][1] = json.dumps(state)
    replayed = await replay(case)
    result = replayed["output"]["result"]
    assert result["quality"]["analysis"]["alert_match"]["status"] == "match"
    assert not {"reported_error_code", "report_reason_changed"} & set(
        result["missing_inputs"]
    )
    author = replayed["model_calls"][0]["input"]
    assert author["event_target"]["error_code"] == alert(kind)["error_codes"][0]
    assert (
        author["error_events"][0]["error_code"] == author["event_target"]["error_code"]
    )
    assert any(e["error_code"] == kind + ":31" for e in author["error_events"])


def healthy_event_case(kind):
    case = match_case(kind=kind)
    rows = case["queries"][0]["response"]["data"]["result"][0]["values"]
    report = json.loads(rows[-1][1])
    report["attributes"]["health"] = "Healthy"
    rows[-1][1] = json.dumps(report)
    return case, rows, report


@pytest.mark.parametrize("kind", ["xid", "sxid"])
@pytest.mark.parametrize("target_health", ["Healthy", "Unhealthy"])
async def test_confirmed_event_keeps_unknown_sibling_reports_as_context(
    kind, target_health
):
    from rca_replay import replay

    case, rows, report = healthy_event_case(kind)
    target = deepcopy(report)
    target["attributes"]["health"] = target_health
    rows[-1][1] = json.dumps(target)
    for change in ("pci", "code", "host"):
        other = deepcopy(report)
        if change == "pci":
            other["attributes"]["reason"] = other["attributes"]["reason"].replace(
                DEVICES[kind], "PCI:0000:02:00.0"
            )
        elif change == "code":
            other["attributes"]["reason"] = other["attributes"]["reason"].replace(
                CODES[kind].split(":")[1], "31", 1
            )
        else:
            other["resources"]["machine.id"] = "other-machine"
        rows.append([rows[-1][0], json.dumps(other)])
    original = deepcopy(rows)
    replayed = await replay(case)
    result = replayed["output"]["result"]
    assert result["quality"]["analysis"]["alert_match"]["status"] == "match"
    assert result["missing_inputs"] == []
    assert result["result_status"] == "ready"
    assert len(result["device_observations"]) == 4
    unknown = [h for h in result["device_observations"] if h["raw_health"] == "Healthy"]
    assert unknown and all(h["normalized_health"] == "unknown" for h in unknown)
    assert all(not h["fact_eligible"] for h in result["device_observations"])
    author = replayed["model_calls"][0]["input"]
    # Unknown reports stay in stored context, never promoted to verified model facts.
    assert len(author["device_observations"]) == int(target_health == "Unhealthy")
    evidence = replayed["output"]["evidence"]
    source = next(e for e in evidence if e["query_id"] == "D09")
    assert source["snapshot"]["data"]["result"][0]["values"] == original
    assessment = next(e for e in evidence if e["query_id"] == "collection_assessment")
    decision = next(
        c for c in assessment["snapshot"]["checks"] if c["rule"] == "unknown_value"
    )
    assert decision["value"] is False
    assert decision["inputs"]["event_confirmed"] is True
    assert decision["inputs"]["context_report_count"] == 3
    assert decision["inputs"]["relevant_count"] == 1
    assert rows == original


@pytest.mark.parametrize("kind", ["xid", "sxid"])
@pytest.mark.parametrize("baseline", [False, True])
async def test_confirmed_event_does_not_require_component_state(kind, baseline):
    from rca_replay import replay

    case, rows, report = healthy_event_case(kind)
    if baseline:
        report["attributes"]["reason"] = kind.upper() + "Component is healthy"
        rows[-1][1] = json.dumps(report)
    else:
        rows.pop()
    result = (await replay(case))["output"]["result"]
    assert result["quality"]["analysis"]["alert_match"]["status"] == "match"
    assert result["result_status"] == "ready"
    assert result["missing_inputs"] == []


@pytest.mark.parametrize("kind", ["xid", "sxid"])
@pytest.mark.parametrize(
    "failure,missing",
    [
        ("no_event", "event_not_found"),
        ("wrong_pci", "event_not_found"),
        ("unknown_state", "unknown_value"),
        ("invalid_check", "unknown_value"),
        ("collection", "observation_degraded"),
    ],
)
async def test_healthy_event_exception_preserves_real_gaps(kind, failure, missing):
    from rca_replay import replay

    case, rows, report = healthy_event_case(kind)
    if failure == "no_event":
        rows.pop(0)
    elif failure == "wrong_pci":
        rows[0][1] = rows[0][1].replace(DEVICES[kind], "PCI:0000:02:00.0")
    elif failure == "unknown_state":
        report["attributes"]["health"] = "Unregistered"
        rows[-1][1] = json.dumps(report)
    elif failure == "invalid_check":
        case["attempt"]["profile"]["health_contracts"]["fleet-component-log-v1"][
            "checks"
        ]["reported"] = "unknown"
    else:
        case["queries"][0]["error"] = True
    result = (await replay(case))["output"]["result"]
    assert missing in result["missing_inputs"]
    assert result["result_status"] != "ready"


@pytest.mark.parametrize("kind", ["xid", "sxid"])
async def test_confirmed_event_cannot_satisfy_explicit_current_health_requirement(kind):
    from agent_common.contracts import content_hash
    from rca_replay import replay

    case, _, _ = healthy_event_case(kind)
    book = case["attempt"]["context"]["runbooks"][0]
    book["content"]["required_evidence"].append("normalized_health")
    book["content_hash"] = book["reviewed_content_hash"] = content_hash(book["content"])
    result = (await replay(case))["output"]["result"]
    assert result["quality"]["analysis"]["alert_match"]["status"] == "match"
    assert "unknown_value" not in result["missing_inputs"]
    assert "normalized_health" in result["missing_inputs"]
    assert result["result_status"] != "ready"
