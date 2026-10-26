"""Synthetic transition/overlap regressions; no production endpoints."""

from copy import deepcopy
import asyncio
import time

import pytest

from test_aggregate_report import DATA, fixture
from ops_agent.identity_transitions import sample_bounds, verified_transitions
from ops_agent.namespace_summary import summarize
from ops_agent.report_queries import ReportQueries


def transition_fixture(
    period=None, cluster="cpc-1", namespace="test-dept-service", **kwargs
):
    evidence = fixture(period, cluster=cluster, namespace=namespace, **kwargs)
    at = evidence[0]["snapshot"]["series"][0]["values"][0][0]
    labels = {
        k: v
        for k, v in evidence[0]["snapshot"]["series"][0]["metric"].items()
        if k != "measure"
    }
    unnamed = {k: v for k, v in labels.items() if k not in {"namespace", "pod"}}
    gpu = [
        {
            "metric": unnamed,
            "values": [[at - 3600 + i * 15 + 5, "0"] for i in range(13)],
        },
        {
            "metric": labels,
            "values": [[at - 3600 + i * 15 + 5, "60"] for i in range(13, 240)],
        },
    ]
    pods = [
        {
            "metric": deepcopy(evidence[1]["snapshot"]["series"][0]["metric"]),
            "values": [[at - 3600 + i * 15 + 2, "1"] for i in range(13, 240)],
        }
    ]
    measures = {
        "sample_count": 227,
        "activity_sum": 227 * 60,
        "minimum": 60,
        "maximum": 60,
    }
    for row in evidence[0]["snapshot"]["series"]:
        row["values"][0][1] = str(measures[row["metric"]["measure"]])
    for measure, value in {
        "sample_count": 13,
        "activity_sum": 0,
        "minimum": 0,
        "maximum": 0,
    }.items():
        evidence[0]["snapshot"]["series"].append(
            {"metric": {**unnamed, "measure": measure}, "values": [[at, str(value)]]}
        )
    evidence[1]["snapshot"]["series"][0]["values"][0][1] = "227"
    evidence[2]["snapshot"]["series"][0]["values"][0][1] = "2"
    return evidence, gpu, pods, at


def proof(evidence, gpu, pods, at, *, rejected=None):
    cluster = evidence[0]["cluster_id"]
    checks = verified_transitions(
        sample_bounds(gpu, at, cluster),
        sample_bounds(pods, at, cluster),
        at,
        {"gpu-1": 2},
        None,
        rejected=rejected,
    )
    return {
        **evidence[0],
        "id": "transition-proof",
        "query_id": "gpu_identity_transitions",
        "snapshot": {"checks": checks},
    }


def named(rows):
    return next(r for r in rows if r["namespace"])


def test_verified_start_keeps_only_named_samples():
    evidence, gpu, pods, at = transition_fixture()
    before, _ = summarize(evidence, DATA["time_range"])
    assert named(before)["valid_hours"] == 23
    evidence.append(proof(evidence, gpu, pods, at))
    after, _ = summarize(evidence, DATA["time_range"])
    row = named(after)
    assert row["valid_hours"] == 24
    assert row["activity_percent"] == 60
    assert row["hours"][0]["sample_count"] == 227
    assert row["verified_transition_hours"] == 1
    assert next(r for r in after if not r["namespace"])["activity_percent"] is None


def pending_transition_fixture():
    evidence, gpu, pods, at = transition_fixture()
    pending = deepcopy(pods[0])
    del pending["metric"]["node"]
    pending["values"] = [[at - 3600 + i * 15 + 2, "1"] for i in range(13)]
    pods.insert(0, pending)
    evidence[1]["snapshot"]["series"].append(
        {"metric": deepcopy(pending["metric"]), "values": [[at, "13"]]}
    )
    return evidence, gpu, pods, at


@pytest.mark.parametrize(
    "case,reason",
    [
        ("leading_missing_node", None),
        ("leading_empty_node", None),
        ("pending_ends_at_gpu_start", "pod_node_unverified"),
        ("pending_ends_after_gpu_start", "pod_node_unverified"),
        ("pending_assigned_overlap", "pod_continuity_unverified"),
        ("pending_assigned_gap", "pod_continuity_unverified"),
        ("leading_other_node", "pod_node_unverified"),
        ("leading_other_uid", "pod_uid_unverified"),
        ("unassigned_after_assignment", "pod_node_unverified"),
        ("no_assigned_interval", "pod_node_unverified"),
        ("assignment_starts_too_late", "pod_coverage_unverified"),
    ],
)
def test_pending_to_assigned_transition_requires_safe_prefix(case, reason):
    evidence, gpu, pods, at = pending_transition_fixture()
    gpu_first = gpu[1]["values"][0][0]
    if case == "leading_empty_node":
        pods[0]["metric"]["node"] = ""
    elif case in {"pending_ends_at_gpu_start", "pending_ends_after_gpu_start"}:
        shift = gpu_first - pods[0]["values"][-1][0] + case.endswith("after_gpu_start")
        for sample in pods[0]["values"]:
            sample[0] += shift
        pods[1]["values"] = pods[1]["values"][1:]
    elif case == "pending_assigned_overlap":
        pods[0]["values"][-1][0] = pods[1]["values"][0][0]
    elif case == "pending_assigned_gap":
        pods[0]["values"] = pods[0]["values"][:-2]
    elif case == "leading_other_node":
        pods[0]["metric"]["node"] = "other-node"
    elif case == "leading_other_uid":
        pods[0]["metric"]["uid"] = "other-uid"
    elif case == "unassigned_after_assignment":
        tail = deepcopy(pods[1])
        del tail["metric"]["node"]
        tail["values"] = tail["values"][-7:]
        pods[1]["values"] = pods[1]["values"][:-7]
        pods.append(tail)
    elif case == "no_assigned_interval":
        pods.pop()
    elif case == "assignment_starts_too_late":
        pods[0]["values"][-1][0] = gpu_first - 5
        pods[1]["values"] = [[gpu_first + 20 + i * 15, "1"] for i in range(226)]
    rejected = []
    check = proof(evidence, gpu, pods, at, rejected=rejected)
    rows, _ = summarize(evidence + [check], DATA["time_range"])
    if reason:
        assert not check["snapshot"]["checks"]
        assert rejected == [
            dict(
                gpu_id="gpu-1",
                namespace="test-dept-service",
                pod="test-pod",
                reason=reason,
            )
        ]
        assert named(rows)["valid_hours"] == 23
    else:
        assert rejected == []
        assert check["snapshot"]["checks"][0]["pod_sample_count"] == 227
        assert named(rows)["valid_hours"] == 24


@pytest.mark.parametrize("split_metadata", [False, True])
def test_assigned_pod_count_matches_node_aggregate_after_pending(split_metadata):
    evidence, gpu, pods, at = pending_transition_fixture()
    if split_metadata:
        tail = deepcopy(pods[1])
        tail["metric"]["pod_ip"] = "192.0.2.1"
        tail["values"] = tail["values"][7:]
        pods[1]["values"] = pods[1]["values"][:7]
        pods.append(tail)
        evidence[1]["snapshot"]["series"][0]["values"][0][1] = "7"
        evidence[1]["snapshot"]["series"].append(
            {"metric": deepcopy(tail["metric"]), "values": [[at, "220"]]}
        )
    before, _ = summarize(evidence, DATA["time_range"])
    check = proof(evidence, gpu, pods, at)
    after, _ = summarize(evidence + [check], DATA["time_range"])
    assert check["snapshot"]["checks"][0]["pod_sample_count"] == 227
    assert named(after)["valid_hours"] == 24
    assert named(after)["activity_percent"] == 60
    assert named(after)["hours"][1:] == named(before)["hours"][1:]
    unknown_before = next(r for r in before if not r["namespace"])
    unknown_after = next(r for r in after if not r["namespace"])
    assert {k: v for k, v in unknown_before.items() if k != "evidence_refs"} == {
        k: v for k, v in unknown_after.items() if k != "evidence_refs"
    }
    # A node-only relaxation includes pending samples and cannot satisfy the saved aggregate.
    check["snapshot"]["checks"][0]["pod_sample_count"] = 240
    wrong, _ = summarize(evidence + [check], DATA["time_range"])
    assert named(wrong)["valid_hours"] == 23
    assert "pod_identity_unverified" in named(wrong)["hours"][0]["reasons"]


@pytest.mark.parametrize(
    "condition,value,reason",
    [
        ("min_gap", 14, None),
        ("min_gap", 13.999, "pod_samples_unverified"),
        ("max_gap", 30, None),
        ("max_gap", 30.001, "pod_samples_unverified"),
        ("boundary_gap", 30, None),
        ("boundary_gap", 30.001, "pod_continuity_unverified"),
        ("start_lag", 15, None),
        ("start_lag", 15.001, "pod_coverage_unverified"),
        ("end_lag", 15, None),
        ("end_lag", 15.001, "pod_coverage_unverified"),
        ("pending_value", 0, "pod_samples_unverified"),
        ("pending_uid", "", "pod_uid_unverified"),
    ],
)
def test_pod_transition_bounds_keep_existing_tolerances(condition, value, reason):
    _, gpu, pods, at = pending_transition_fixture()
    gpus = sample_bounds(gpu, at, "cpc-1")
    bounds = sample_bounds(pods, at, "cpc-1")
    if condition in {"min_gap", "max_gap"}:
        bounds[0][condition] = value
    elif condition == "boundary_gap":
        bounds[0]["last"] = bounds[1]["first"] - value
    elif condition == "start_lag":
        bounds[0]["last"] = gpus[1]["first"] - 5
        bounds[1]["first"] = gpus[1]["first"] + value
    elif condition == "end_lag":
        bounds[1]["last"] = gpus[1]["last"] - value
    elif condition == "pending_value":
        bounds[0]["values"]["minimum"] = value
    elif condition == "pending_uid":
        bounds[0]["labels"]["uid"] = value
    rejected = []
    checks = verified_transitions(
        gpus, bounds, at, {"gpu-1": 2}, None, rejected=rejected
    )
    assert bool(checks) is (reason is None)
    assert [r["reason"] for r in rejected] == ([] if reason is None else [reason])


@pytest.mark.parametrize(
    "problem",
    [
        "overlap",
        "interleaved",
        "gap",
        "pod_uid",
        "pod_node",
        "pod_gap",
        "pod_late",
        "pod_duplicate",
        "unexpected_series",
    ],
)
def test_ambiguous_transition_stays_excluded(problem):
    evidence, gpu, pods, at = transition_fixture()
    if problem == "overlap":
        gpu[1]["values"][0][0] = gpu[0]["values"][-1][0]
    if problem == "interleaved":
        gpu[0]["values"][-1][0] += 20
    if problem == "gap":
        gpu[1]["values"][10][0] += 40
    if problem == "pod_uid":
        pods.append(deepcopy(pods[0]))
        pods[-1]["metric"]["uid"] = "different"
    if problem == "pod_node":
        pods[0]["metric"]["node"] = "wrong"
    if problem == "pod_gap":
        del pods[0]["values"][10:20]
    if problem == "pod_late":
        del pods[0]["values"][:3]
    if problem == "pod_duplicate":
        pods.append(deepcopy(pods[0]))
    if problem == "unexpected_series":
        gpu.append(deepcopy(gpu[0]))
    try:
        check = proof(evidence, gpu, pods, at)
    except ValueError:
        return  # Out-of-order samples are rejected before attribution.
    assert not check["snapshot"]["checks"]
    rows, _ = summarize(evidence + [check], DATA["time_range"])
    assert named(rows)["valid_hours"] == 23


def test_pod_metadata_transition_with_same_uid_is_verified():
    evidence, gpu, pods, at = transition_fixture()
    old = deepcopy(pods[0])
    old["values"] = old["values"][:7]
    old["metric"]["host_ip"] = "old"
    pods[0]["values"] = pods[0]["values"][7:]
    pods[0]["metric"]["host_ip"] = "new"
    pods.append(old)
    row = evidence[1]["snapshot"]["series"][0]
    row["metric"]["host_ip"] = "new"
    row["values"][0][1] = "220"
    evidence[1]["snapshot"]["series"].append(
        {"metric": old["metric"], "values": [[at, "7"]]}
    )
    after, _ = summarize(
        evidence + [proof(evidence, gpu, pods, at)], DATA["time_range"]
    )
    assert named(after)["valid_hours"] == 24


def test_outside_selected_namespace_still_participates_in_overlap_check():
    evidence, gpu, pods, at = transition_fixture()
    gpu[0]["metric"].update(namespace="other", pod="other-pod")
    bounds = sample_bounds(gpu, at, "cpc-1")
    checked = verified_transitions(
        bounds,
        sample_bounds(pods, at, "cpc-1"),
        at,
        {"gpu-1": 2},
        ["test-dept-service"],
    )
    assert (
        len(checked) == 1 and checked[0]["labels"]["namespace"] == "test-dept-service"
    )
    bounds[0]["last"] = bounds[1]["first"]
    assert not verified_transitions(
        bounds,
        sample_bounds(pods, at, "cpc-1"),
        at,
        {"gpu-1": 2},
        ["test-dept-service"],
    )


@pytest.mark.parametrize(
    "problem", ["sum", "count", "uid", "mig", "cluster", "namespace"]
)
def test_proof_cannot_override_changed_aggregates_or_attribution_guards(problem):
    evidence, gpu, pods, at = transition_fixture()
    check = proof(evidence, gpu, pods, at)
    if problem == "sum":
        check["snapshot"]["checks"][0]["values"]["activity_sum"] += 1
    if problem == "count":
        evidence[2]["snapshot"]["series"][0]["values"][0][1] = "3"
    if problem == "uid":
        check["snapshot"]["checks"][0]["pod_uid"] = "other"
    if problem == "mig":
        for row in evidence[0]["snapshot"]["series"]:
            row["metric"]["GPU_I_ID"] = "0"
        check["snapshot"]["checks"][0]["labels"]["GPU_I_ID"] = "0"
    if problem == "cluster":
        check["cluster_id"] = "other"
    if problem == "namespace":
        check["scope"] = {
            "clusters": [{"cluster_id": "cpc-1", "namespaces": ["other"]}]
        }
    if problem in {"cluster", "namespace"}:
        with pytest.raises(ValueError):
            summarize(evidence + [check], DATA["time_range"])
    else:
        rows, _ = summarize(evidence + [check], DATA["time_range"])
        assert named(rows)["hours"][0]["activity_percent"] is None


def test_boundary_and_nonfinite_samples_are_rejected():
    _, gpu, _, at = transition_fixture()
    for value in [at, at - 3601, float("nan")]:
        bad = deepcopy(gpu)
        bad[0]["values"][0][0] = value
        with pytest.raises(ValueError):
            sample_bounds(bad, at, "cpc-1")


@pytest.mark.parametrize("failure", [False, True])
def test_collector_uses_bounded_instant_queries_and_saves_no_raw_samples(failure):
    evidence, gpu, pods, at = transition_fixture()
    calls = []

    async def query(args):
        calls.append(args)
        assert args["queryType"] == "instant" and "endTime" in args
        assert "stepSeconds" not in args and "[1h] offset 1ms" in args["expr"]
        if failure:
            raise RuntimeError("private upstream error")
        return {"data": {"result": pods if "kube_pod_info" in args["expr"] else gpu}}

    c = ReportQueries({"query_prometheus": query}, DATA, time.monotonic() + 60)
    out = asyncio.run(
        c.check_transitions(
            [(DATA["scope"]["clusters"][0], DATA["time_range"], "mimir", evidence)]
        )
    )
    assert len(calls) == (1 if failure else 2)
    assert "series" not in out[0]["snapshot"]
    rows, _ = summarize(evidence + out, DATA["time_range"])
    assert named(rows)["valid_hours"] == (23 if failure else 24)
    c.transition_calls = 31
    assert (
        asyncio.run(
            c.check_transitions(
                [(DATA["scope"]["clusters"][0], DATA["time_range"], "mimir", evidence)]
            )
        )
        == []
    )


def test_unchanged_hours_do_not_trigger_raw_queries():
    async def query(args):
        raise AssertionError("unexpected query")

    c = ReportQueries({"query_prometheus": query}, DATA, time.monotonic() + 60)
    assert (
        asyncio.run(
            c.check_transitions(
                [(DATA["scope"]["clusters"][0], DATA["time_range"], "mimir", fixture())]
            )
        )
        == []
    )


def test_many_changed_hours_stop_at_verification_budget():
    evidence, gpu, pods, at = transition_fixture()
    # Repeat ambiguity over a day: at most 16 two-query verifications, never 24 raw hours.
    for sample in evidence[2]["snapshot"]["series"][0]["values"]:
        sample[1] = "2"
    calls = []

    async def query(args):
        calls.append(args)
        return {"data": {"result": []}}

    c = ReportQueries({"query_prometheus": query}, DATA, time.monotonic() + 60)
    out = asyncio.run(
        c.check_transitions(
            [(DATA["scope"]["clusters"][0], DATA["time_range"], "mimir", evidence)]
        )
    )
    assert len(calls) == 32 and len(out) == 16
    assert all(not e["snapshot"]["checks"] for e in out)


def test_unselected_shared_identity_and_physical_conflicts_are_not_recovered():
    evidence, gpu, pods, at = transition_fixture()
    for key, value in [
        ("allocation_mode", "shared"),
        ("GPU_I_ID", "0"),
        ("Hostname", "other-node"),
        ("modelName", "other-model"),
        ("uuid", "other-id"),
    ]:
        bad = deepcopy(gpu)
        bad[0]["metric"][key] = value
        assert not proof(evidence, bad, pods, at)["snapshot"]["checks"]


def test_optional_verification_reserves_time_for_publication():
    evidence, _, _, _ = transition_fixture()

    async def query(args):
        raise AssertionError("no time for optional reads")

    c = ReportQueries({"query_prometheus": query}, DATA, time.monotonic() + 20)
    assert (
        asyncio.run(
            c.check_transitions(
                [(DATA["scope"]["clusters"][0], DATA["time_range"], "mimir", evidence)]
            )
        )
        == []
    )
