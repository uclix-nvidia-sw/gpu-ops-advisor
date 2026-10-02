import copy
from uuid import uuid4

import pytest

from agent_common.contracts import content_hash, incident_source, validate_input


def rca_input(snapshot_fields):
    data = {
        "incident_id": str(uuid4()),
        "evidence_version": 1,
        "analysis_profile_revision": "gpu-alert-v1",
        "scope": {"clusters": [{"cluster_id": "cpc-2", "namespaces": ["dev"]}]},
        "incident_time": "2026-09-18T00:05:00Z",
        "time_range": {"start": "2026-09-18T00:00:00Z", "end": "2026-09-18T00:10:00Z"},
        "purpose_ids": ["R01", "R02"],
    }
    data["incident_snapshot"] = {"input": copy.deepcopy(data), **snapshot_fields}
    return data


def test_incident_alert_is_raw_evidence_and_snapshot_is_unchanged():
    alert = {
        "labels": {"alertname": "GPUAlert", "cluster_id": "cpc-2"},
        "annotations": {"error_code": "Xid 79"},
        "verified_facts": {"error_code": "untrusted", "producer_contract": "untrusted"},
        "symptom": "multi_device",
    }
    data = rca_input({"alert": alert, "analysis_policy": {"revision": "gpu-alert-v1"}})
    snapshot = copy.deepcopy(data["incident_snapshot"])
    validate_input("rca", data)
    source = incident_source(data["incident_snapshot"])
    assert source["alert"] == alert
    assert "verified_facts" not in source
    assert data["incident_snapshot"] == snapshot
    assert content_hash(data["incident_snapshot"]) == content_hash(snapshot)


@pytest.mark.parametrize(
    "evidence", [{"symptom": "gpu_access", "verified_facts": {}}, "legacy raw"]
)
def test_legacy_evidence_snapshots_remain_supported(evidence):
    data = rca_input({"evidence": evidence})
    validate_input("rca", data)
    assert incident_source(data["incident_snapshot"]) == (
        evidence if isinstance(evidence, dict) else {"raw": evidence}
    )


def test_actual_alert_wins_over_legacy_field():
    source = incident_source(
        {
            "alert": {"labels": {}},
            "evidence": {"verified_facts": {"error_code": "untrusted"}},
        }
    )
    assert "verified_facts" not in source


@pytest.mark.parametrize(
    "fields", [{}, {"alert": None}, {"alert": []}, {"alert": "text", "evidence": {}}]
)
def test_missing_or_malformed_alert_is_rejected_during_input_validation(fields):
    with pytest.raises(ValueError, match="incident"):
        validate_input("rca", rca_input(fields))
