"""Trace actual branches without changing RCA conclusions or model calls."""

from copy import deepcopy
import json

import pytest

from rcca_agent.fleet_events import match_alert
from test_fleet_rca import alert, state_report, kmsg_event, match_case


@pytest.mark.parametrize("events", [[], [kmsg_event()]])
def test_trace_is_optional_and_does_not_change_match_result(events):
    health = [state_report(observed_at="2026-01-01T00:01:00Z")]
    original = deepcopy((health, events))
    checks = []
    expected = match_alert(alert(), health, events)
    assert match_alert(alert(), health, events, checks) == expected
    assert (health, events) == original
    event = next(c for c in checks if c["rule"] == "event_missing")
    assert event["inputs"]["matched_event_count"] == len(events)
    assert event["value"] is (not events)
    assert all(c["expression"] for c in checks)


def test_trace_explains_earliest_error_even_when_later_transition_exists():
    health = [
        state_report(observed_at="2026-01-01T00:01:00Z"),
        state_report(
            raw_health="Healthy", reason="ok", observed_at="2026-01-01T00:02:00Z"
        ),
        state_report(observed_at="2026-01-01T00:03:00Z"),
    ]
    checks = []
    assert match_alert(alert(), health, [], checks)["status"] == "event_not_found"
    onset = next(c for c in checks if c["rule"] == "preceding_healthy")
    assert onset["value"] is False
    assert onset["inputs"]["first_unhealthy_at"] == "2026-01-01T00:01:00Z"
    assert onset["inputs"]["last_healthy_at"] is None
    assert onset["inputs"]["preceding_healthy_count"] == 0
    assert not any(c["rule"] == "pci_mismatch" for c in checks)


def test_trace_records_valid_onset_and_early_exit():
    checks = []
    health = [
        state_report(raw_health="Healthy", observed_at="2026-01-01T00:00:00Z"),
        state_report(observed_at="2026-01-01T00:01:00Z"),
    ]
    assert match_alert(alert(), health, [], checks)["status"] == "event_not_exported"
    assert checks[-1]["rule"] == "preceding_healthy"
    assert checks[-1]["value"] is True
    assert checks[-1]["inputs"]["preceding_healthy_count"] == 1
    checks = []
    assert match_alert(alert(), [], [], checks)["status"] == "event_not_found"
    assert any(c["rule"] == "event_missing" and c["value"] for c in checks)


@pytest.mark.parametrize("change", [None, "pci", "no_event"])
async def test_workflow_records_decision_before_model_and_final_status_before_freeze(
    change,
):
    from rca_replay import replay

    case = match_case("pci" if change == "pci" else None)
    if change == "no_event":
        case["queries"][0]["response"]["data"]["result"][0]["values"].pop(0)
    replayed = await replay(case)
    output = replayed["output"]
    result, evidence = output["result"], output["evidence"]
    kinds = [e["query_id"] for e in evidence]
    by_kind = {e["query_id"]: e for e in evidence}
    collection = by_kind["collection_assessment"]
    decision = by_kind["rca_status_decision"]
    frozen = by_kind["rca_result_frozen"]
    assert (
        kinds.index("collection_assessment")
        < kinds.index("evidence_validation")
        < kinds.index("rca_synthesis")
    )
    assert (
        kinds.index("rca_analysis_draft")
        < kinds.index("rca_status_decision")
        < kinds.index("rca_result_frozen")
    )
    assert decision["snapshot"]["outputs"]["result_status"] == result["result_status"]
    assert decision["snapshot"]["outputs"]["missing_inputs"] == result["missing_inputs"]
    assert (
        collection["snapshot"]["outputs"]["alert_match"]
        == result["quality"]["analysis"]["alert_match"]
    )
    assert frozen["snapshot"]["decision_evidence_refs"] == [
        collection["id"],
        decision["id"],
    ]
    assert set(frozen["snapshot"]["decision_evidence_refs"]) <= set(
        result["evidence_refs"]
    )
    assert [c["stage"] for c in replayed["model_calls"]] == [
        "synthesis",
        "report_writing",
    ]
    for call in replayed["model_calls"]:
        assert collection["id"] not in json.dumps(call["input"])
        assert decision["id"] not in json.dumps(call["input"])
    if change == "no_event":
        assert (
            collection["snapshot"]["outputs"]["alert_match"]["status"]
            == "event_not_found"
        )
        assert "event_not_found" in decision["snapshot"]["outputs"]["missing_inputs"]
        assert result["result_status"] == "partial"
    assert not collection["quality"].get("complete")
