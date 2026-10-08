import copy

import pytest

from rcca_agent.requirement_diagnostics import reported_facts, unmet_requirements


def fixture():
    data = {
        "target": {"k8s_node_name": "node-a", "machine_id": "machine-a"},
        "scope": {"clusters": [{"cluster_id": "cluster-a"}]},
    }
    row = {
        "target": {"node": "node-a", "machine_id": "machine-a"},
        "cluster_id": "cluster-a",
        "check_status": "valid",
        "error_code": "xid:79",
        "normalized_health": "unhealthy",
        "producer_contract": "fleet-component-log-v1",
        "fact_eligible": False,
        "evidence_refs": ["log"],
    }
    return data, row


def test_reported_does_not_satisfy_current_health_or_cause():
    data, row = fixture()
    before = copy.deepcopy(row)
    result = unmet_requirements(
        ["error_code", "normalized_health", "causal_confirmation_evidence"],
        [row],
        [],
        data,
    )
    assert all(r["status"] == "unmet" for r in result)
    assert next(r for r in result if r["requirement"] == "error_code")[
        "evidence_refs"
    ] == ["log"]
    assert (
        next(r for r in result if r["requirement"] == "causal_confirmation_evidence")[
            "reason"
        ]
        == "cause_not_confirmed"
    )
    assert row == before


@pytest.mark.parametrize(
    "mismatch", ["cluster", "node", "machine", "invalid", "conflict", "no_identity"]
)
def test_unrelated_or_invalid_rows_do_not_claim_reported_evidence(mismatch):
    data, row = fixture()
    if mismatch == "cluster":
        row["cluster_id"] = "other"
    if mismatch == "node":
        row["target"]["node"] = "other"
    if mismatch == "machine":
        row["target"]["machine_id"] = "other"
    if mismatch == "invalid":
        row["check_status"] = "unknown"
    if mismatch == "conflict":
        data["identity_conflicts"] = ["node"]
    if mismatch == "no_identity":
        data["target"] = {}
    result = unmet_requirements(["error_code"], [row], [], data)
    assert result[0]["reason"] == "required_fact_not_established"
    assert result[0]["evidence_refs"] == []


def test_historical_event_explains_code_only_not_current_health():
    data, row = fixture()
    row.update(status="reported_event")
    result = unmet_requirements(["error_code", "normalized_health"], [], [row], data)
    assert result[0]["reason"] == "reported_but_required_semantics_unverified"
    assert result[1]["reason"] == "required_fact_not_established"


def test_reported_facts_preserve_state_boundary():
    data, row = fixture()
    assert reported_facts([row], [], data) == {
        "reported_error_code": "xid:79",
        "reported_producer_contract": "fleet-component-log-v1",
    }


def test_same_snapshot_reference_cannot_import_other_target():
    data, row = fixture()
    other = copy.deepcopy(row)
    other["target"]["node"] = "other"
    other["error_code"] = "xid:31"
    assert reported_facts([row, other], [], data)["reported_error_code"] == "xid:79"
    assert reported_facts([other], [], data) == {}


def test_conflicting_reported_codes_remain_unknown():
    data, row = fixture()
    other = dict(row, error_code="xid:31")
    assert "reported_error_code" not in reported_facts([row, other], [], data)


def test_other_component_cannot_satisfy_reported_fact():
    data, row = fixture()
    data["target"]["component"] = "cpu"
    row["component"] = "accelerator-nvidia-error-xid"
    assert reported_facts([row], [], data) == {}


def test_requirement_groups_keep_separate_gates():
    from rcca_agent.requirement_diagnostics import requirement_groups

    content = {
        "required_evidence": ["reported_error_code", "normalized_health"],
        "recommendations": [
            {"preconditions": [{"field": "action_policy", "equals": "approved"}]}
        ],
    }
    before = copy.deepcopy(content)
    assert requirement_groups(content) == {
        "reported_facts": ["reported_error_code"],
        "device_state": ["normalized_health"],
        "cause": ["causal_confirmation_evidence"],
        "action_conditions": ["action_policy"],
    }
    assert content == before


def test_report_only_runbook_compatibility_does_not_create_health_facts():
    from rcca_agent.workflow import matching_runbooks

    facts = {
        "reported_error_code": "xid:79",
        "reported_producer_contract": "fleet-component-log-v1",
    }
    book = {
        "compatibility": {"producer_contract": "fleet-component-log-v1"},
        "content": {
            "schema": "gpu-rca-runbook/1.0",
            "investigation_only": True,
            "required_evidence": list(facts),
            "exclusion_conditions": [],
        },
    }
    data, _ = fixture()
    assert matching_runbooks([book], facts, facts, data) == ([book], [])
    assert "producer_contract" not in facts
    assert "normalized_health" not in facts
    book["content"]["required_evidence"] = ["producer_contract", "normalized_health"]
    assert matching_runbooks([book], facts, facts, data) == ([], [book])
