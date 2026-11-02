"""Catalog descriptions must not manufacture a second incident code."""

import pytest

from rcca_agent.incident import alert_clues
from rcca_agent.fleet_events import event_selector, match_alert
from rcca_agent.retrieval import incident_terms
from rcca_agent.requirement_diagnostics import reported_facts
from test_fleet_rca import kmsg_event


DESCRIPTION = (
    "Additional to Xid 48 providing more details on particulars of fault "
    "to differentiate DRAM/SRAM"
)


@pytest.mark.parametrize("code", [171, 172])
def test_catalog_cross_reference_preserves_primary_event_and_raw_reason(code):
    reason = (
        f"[Warning] accelerator-nvidia-error-xid: XID {code} "
        f"UNCORRECTABLE_SRAM_ERROR {DESCRIPTION} detected on GPU PCI:0000:01:00"
    )
    source = {
        "summary": "GPU memory alert",
        "alert": {
            "labels": {
                "component": "accelerator-nvidia-error-xid",
                "reason": reason,
                "machine_id": "machine-1",
                "k8s_node_name": "node-1",
            }
        },
    }
    clues = alert_clues(source)
    assert clues["reason"] == reason
    assert clues["error_codes"] == [f"xid:{code}"]
    assert event_selector(clues)["error_code"] == f"xid:{code}"
    assert "xid:48" not in incident_terms(source)
    assert f"xid:{code}" in incident_terms(source)
    event = kmsg_event(error_code=f"xid:{code}")
    assert match_alert(clues, [], [event])["status"] == "match"
    event.update(cluster_id="cluster-a", status="reported_event")
    data = {
        "incident_snapshot": source,
        "scope": {"clusters": [{"cluster_id": "cluster-a"}]},
        "target": {"node": "node-1", "machine_id": "machine-1"},
    }
    # A matching event restores the Runbook requirement, not current GPU health.
    facts = reported_facts([], [event], data)
    assert facts["reported_error_code"] == f"xid:{code}"
    assert "reported_normalized_health" not in facts


@pytest.mark.parametrize(
    "reason",
    [
        "XID 171 and Xid 48 detected on GPU PCI:0000:01:00",
        f"XID 171 {DESCRIPTION}; Xid 48 detected on GPU PCI:0000:01:00",
        f"XID 79 {DESCRIPTION} detected on GPU PCI:0000:01:00",
    ],
)
def test_real_or_unrecognized_multiple_codes_remain_ambiguous(reason):
    source = {
        "alert": {
            "labels": {"component": "accelerator-nvidia-error-xid", "reason": reason}
        }
    }
    clues = alert_clues(source)
    assert len(clues["error_codes"]) == 2
    assert not event_selector(clues)
    assert "xid:48" in incident_terms(source)
