from copy import deepcopy

import pytest

from rcca_agent.collection_checks import collection_checks, reported_gpu_identity


def test_available_sources_and_missing_fabric_connection_are_distinct():
    profile = {
        "query_contract": "single-query-v3-draft",
        "queries": {q: {} for q in ("D02", "D06", "D09", "D13")},
    }
    rows = {
        q: [dict(id=q, tool_status="ok", quality={"complete": True})]
        for q in profile["queries"]
    }
    original = deepcopy(rows)
    checks = {
        c["key"]: c
        for c in collection_checks(
            profile, list(rows), rows, [{"pod_uid": "pod"}], ["sxid:11001"]
        )
    }
    assert checks["workload_identity"]["status"] == "collected"
    assert checks["workload_identity"]["relation_count"] == 1
    assert checks["raw_log_context"]["status"] == "collected"
    assert checks["fabric_manager_logs"]["status"] == "connection_required"
    assert checks["fabric_topology"]["status"] == "connection_required"
    assert rows == original
    profile["rca"] = {"evidence_roles": {"fabric_manager_logs": "D13"}}
    assert (
        next(
            c
            for c in collection_checks(profile, list(rows), rows, [], ["sxid:11001"])
            if c["key"] == "fabric_manager_logs"
        )["status"]
        == "collected"
    )
    # Merely naming an existing query never grants permission outside the plan.
    assert (
        next(
            c
            for c in collection_checks(profile, ["D09"], rows, [], ["sxid:11001"])
            if c["key"] == "fabric_manager_logs"
        )["status"]
        == "plan_required"
    )


@pytest.mark.parametrize(
    "status,complete,expected",
    [
        ("empty", True, "empty"),
        ("unavailable", False, "failed"),
        ("partial", False, "partial"),
    ],
)
def test_empty_failure_and_partial_never_become_success(status, complete, expected):
    checks = collection_checks(
        {"queries": {"D09": {}}},
        ["D09"],
        {"D09": [dict(id="log", tool_status=status, quality={"complete": complete})]},
        [],
        [],
    )
    assert checks[0]["status"] == expected
    assert checks[0]["evidence_refs"] == ["log"]


def test_scoped_pci_match_can_identify_workload_target_without_asserting_health():
    data = {"scope": {"clusters": [{"cluster_id": "c"}]}, "target": {"node": "server"}}
    row = dict(
        cluster_id="c",
        target={"node": "server"},
        check_status="valid",
        error_code="xid:79",
        pci_inventory_relation="inventory_candidate_only",
        reported_pci_addresses=["0000:07:00"],
        gpu_candidates=[{"gpu_uuid": "GPU-fixture", "bus_id": "0000:07:00.0"}],
        evidence_refs=["log"],
        normalized_health="unknown",
    )
    original = deepcopy(row)
    assert reported_gpu_identity(data, [row]) == ({"gpu_uuid": "GPU-fixture"}, ["log"])
    for edit in (
        {"error_code": "sxid:11001"},
        {"cluster_id": "other"},
        {"target": {"node": "other"}},
        {"check_status": "invalid"},
    ):
        assert reported_gpu_identity(data, [{**row, **edit}]) == ({}, [])
    duplicate = {
        **row,
        "gpu_candidates": [{"gpu_uuid": "GPU-other", "bus_id": "0000:07:00.0"}],
    }
    assert reported_gpu_identity(data, [row, duplicate]) == ({}, [])
    assert reported_gpu_identity({**data, "identity_conflicts": ["node"]}, [row]) == (
        {},
        [],
    )
    assert row == original
