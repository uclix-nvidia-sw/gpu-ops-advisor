"""Fixed O08 observations; no production data or namespace consumption claims."""

import copy
import time
from types import SimpleNamespace

import pytest

from agent_common.contracts import validate_result
from agent_common.runtime import attempt_context
from ops_agent.workflow import calculate, run
from test_report_observation import DATA, START, END, evidence, profile, row


def observations(*workloads):
    rows = []
    for namespace, gpu, start, end, value in workloads:
        rows.append(
            row(
                {
                    "uuid": gpu,
                    "namespace": namespace,
                    "pod": namespace + "-pod",
                    "pod_uid": namespace + "-uid",
                    "node": "node-1",
                    "modelName": "fixture-gpu",
                },
                str(value),
                start,
                end - 15,
            )
        )
    result = {q: [evidence(q, copy.deepcopy(rows))] for q in ("D01", "D02")}
    for es in result.values():
        es[0]["quality"].update(unit="percent", max_hold_seconds=15, complete=True)
    return result


def report(source, data=None):
    data = data or dict(DATA, group_by=["namespace"])
    return calculate("O08", data, source, {}, {}, criteria_version="1.2")


def values(topic, namespace, cluster="cpc-1"):
    return {
        m["id"].split(".")[1]: m["value"]
        for m in topic["metrics"]
        if m["target"] == {"cluster_id": cluster, "namespace": namespace}
    }


def test_weighted_gpu_time_and_zero_are_not_sample_or_device_averages():
    source = observations(
        ("a", "gpu-1", START, END, 80),
        ("a", "gpu-2", START, START + 1800, 20),
        ("b", "gpu-3", START, END, 0),
    )
    topic = report(source)
    assert values(topic, "a") == {
        "namespace_connected_gpu_count": 2,
        "observed_namespace_hours": 1.5,
        "namespace_activity_valid_hours": 1.5,
        "namespace_connected_gpu_util": 60,
    }
    assert values(topic, "b")["namespace_connected_gpu_util"] == 0
    assert topic["status"] == "partial"
    assert topic["recommendations"] == []
    assert topic["quality"]["applied_group_by"] == ["namespace"]


def test_one_gpu_changes_namespace_without_losing_the_whole_period():
    topic = report(
        observations(
            ("a", "gpu-1", START, START + 1800, 20),
            ("b", "gpu-1", START + 1800, END, 80),
        )
    )
    for namespace, mean in [("a", 20), ("b", 80)]:
        assert values(topic, namespace)["observed_namespace_hours"] == 0.5
        assert values(topic, namespace)["namespace_connected_gpu_util"] == mean


def test_simultaneous_namespaces_have_connections_but_no_attributed_activity():
    topic = report(
        observations(
            ("a", "gpu-1", START, END, 80),
            ("b", "gpu-1", START, END, 80),
        )
    )
    assert "shared_gpu_attribution_unverified" in topic["missing_inputs"]
    for namespace in ("a", "b"):
        assert values(topic, namespace)["observed_namespace_hours"] == 1
        assert values(topic, namespace)["namespace_connected_gpu_util"] is None


def test_overlapping_different_timestamps_conflict_only_during_overlap():
    source = observations(("a", "gpu-1", START, START + 60, 0))
    first = source["D02"][0]["snapshot"]["data"][0]
    first["values"] = [[START, "10"]]
    second = copy.deepcopy(first)
    second["metric"]["producer"] = "second"
    second["values"] = [[START + 5, "90"]]
    source["D02"][0]["snapshot"]["data"].append(second)
    source["D02"][0]["quality"]["max_hold_seconds"] = 30
    topic = report(source)
    assert values(topic, "a")["namespace_connected_gpu_util"] == 50
    assert values(topic, "a")["namespace_activity_valid_hours"] == pytest.approx(
        10 / 3600
    )
    assert "conflicting_gpu_activity" in topic["missing_inputs"]


def test_duplicate_container_series_count_physical_gpu_time_once():
    source = observations(("a", "gpu-1", START, END, 20))
    for es in source.values():
        duplicate = copy.deepcopy(es[0]["snapshot"]["data"][0])
        duplicate["metric"]["container"] = "second"
        es[0]["snapshot"]["data"].append(duplicate)
    assert values(report(source), "a") == {
        "namespace_connected_gpu_count": 1,
        "observed_namespace_hours": 1,
        "namespace_activity_valid_hours": 1,
        "namespace_connected_gpu_util": 20,
    }


@pytest.mark.parametrize(
    "problem, reason",
    [
        ("missing", "gpu_activity_missing"),
        ("partial", "gpu_activity_missing"),
        ("unit", "source_unit_unverified"),
        ("invalid", "invalid_gpu_activity"),
        ("shared", "shared_gpu_attribution_unverified"),
        ("mig", "gpu_activity_identity_unverified"),
    ],
)
def test_missing_invalid_and_shared_activity_never_becomes_zero(problem, reason):
    source = observations(("a", "gpu-1", START, END, 20))
    if problem == "missing":
        source.pop("D02")
    elif problem == "partial":
        source["D02"][0]["quality"]["complete"] = False
    elif problem == "unit":
        source["D02"][0]["quality"]["unit"] = "ratio"
    elif problem == "invalid":
        source["D02"][0]["snapshot"]["data"][0]["values"] = [[START, "101"]]
    elif problem == "shared":
        allocation = copy.deepcopy(source["D01"][0])
        allocation["id"] = allocation["query_id"] = "D08"
        allocation["snapshot"]["data"][0]["metric"]["allocation_mode"] = "shared"
        source["D08"] = [allocation]
    else:
        source["D02"][0]["snapshot"]["data"][0]["metric"]["GPU_I_ID"] = "0"
    topic = report(source)
    assert values(topic, "a")["namespace_connected_gpu_util"] is None
    assert reason in topic["missing_inputs"]


def test_pod_uid_ambiguity_is_not_a_zero_or_a_normal_group():
    source = observations(("a", "gpu-1", START, END, 20))
    for es in source.values():
        del es[0]["snapshot"]["data"][0]["metric"]["pod_uid"]
    pods = [
        row({"namespace": "a", "pod": "a-pod", "node": "node-1", "uid": uid}, "1")
        for uid in ("old", "new")
    ]
    source["D06"] = [evidence("D06", pods)]
    topic = report(source)
    assert topic["status"] == "blocked"
    assert all(v is None for v in values(topic, "a").values())
    assert "gpu_pod_identity_missing" in topic["missing_inputs"]


def test_activity_from_recreated_pod_is_not_assigned_using_its_reused_name():
    source = observations(("a", "gpu-1", START, END, 20))
    source["D02"][0]["snapshot"]["data"][0]["metric"]["pod_uid"] = "new-uid"
    topic = report(source)
    assert values(topic, "a")["namespace_connected_gpu_util"] is None
    assert "gpu_activity_identity_unverified" in topic["missing_inputs"]


def test_mig_instance_uuid_is_not_counted_as_a_physical_gpu():
    topic = report(observations(("a", "MIG-instance", START, END, 20)))
    assert all(v is None for v in values(topic, "a").values())
    assert topic["quality"]["unattributed_series_count"] == 1


def test_partial_activity_keeps_its_valid_mean_and_explicit_smaller_denominator():
    source = observations(("a", "gpu-1", START, END, 20))
    activity = source["D02"][0]["snapshot"]["data"][0]
    activity["values"] = [v for v in activity["values"] if v[0] < START + 1800]
    topic = report(source)
    assert values(topic, "a")["namespace_connected_gpu_util"] == 20
    assert values(topic, "a")["namespace_activity_valid_hours"] == 0.5
    metric = next(
        m for m in topic["metrics"] if "namespace_connected_gpu_util" in m["id"]
    )
    assert metric["denominator"] == {"value": 1800, "unit": "GPU-seconds"}
    assert "gpu_activity_missing" in topic["missing_inputs"]


def test_cluster_identity_and_explicit_empty_namespace():
    source = observations(("a", "gpu-1", START, END, 20))
    for query, es in list(source.items()):
        other = copy.deepcopy(es[0])
        other["id"] = query + "cpc-2"
        other["cluster_id"] = "cpc-2"
        other["snapshot"]["data"][0]["values"] = [[START, "80"]]
        es.append(other)
    data = dict(
        DATA,
        group_by=["cluster", "namespace"],
        scope={
            "clusters": [
                {"cluster_id": "cpc-1", "namespaces": ["a", "empty"]},
                {"cluster_id": "cpc-2", "namespaces": ["a"]},
            ]
        },
    )
    topic = report(source, data)
    assert values(topic, "a")["namespace_connected_gpu_util"] == 20
    assert values(topic, "a", "cpc-2")["namespace_connected_gpu_util"] == 80
    assert all(v is None for v in values(topic, "empty").values())


def test_different_models_are_not_averaged_and_unattributed_series_are_visible():
    source = observations(
        ("a", "gpu-1", START, END, 20), ("a", "gpu-2", START, END, 80)
    )
    source["D02"][0]["snapshot"]["data"][1]["metric"]["modelName"] = "other-model"
    source["D01"][0]["snapshot"]["data"].append(row({"uuid": "unassigned"}))
    topic = report(source)
    assert values(topic, "a")["namespace_connected_gpu_util"] is None
    assert "gpu_model_comparison_unverified" in topic["missing_inputs"]
    assert topic["quality"]["unattributed_series_count"] == 1
    assert all(m["target"]["namespace"] == "a" for m in topic["metrics"])


@pytest.mark.parametrize(
    "axes, reason",
    [
        (["model"], "unsupported_group_by"),
        (["namespace", "node"], "unsupported_group_by"),
        (["pod"], "group_by_not_implemented"),
    ],
)
def test_no_silent_group_fallback(axes, reason):
    topic = report({}, dict(DATA, group_by=axes))
    assert topic["status"] == "blocked"
    assert topic["metrics"] == []
    assert topic["missing_inputs"] == [reason]


@pytest.mark.parametrize("criteria", ["1.1", "unconfigured", "1.2"])
@pytest.mark.asyncio
async def test_workflow_collects_d02_only_for_new_criteria_and_validates_result(
    criteria,
):
    source = observations(("a", "gpu-1", START, END, 20))
    config = profile()
    for query in ("D01", "D02"):
        config["queries"][query]["metric"] = query
        config["queries"][query]["max_hold_seconds"] = 15
    calls = []

    async def query(args):
        calls.append(args["expr"])
        q = args["expr"].split("{", 1)[0]
        return {"data": source[q][0]["snapshot"]["data"] if q in source else []}

    data = dict(DATA, topic_ids=["O08", "O09"], group_by=["namespace"], timezone="UTC")
    token = attempt_context.set(
        {
            "claim": {
                "job_id": "fixture",
                "kind": "report",
                "input": data,
                "versions": {"criteria": criteria},
            },
            "context": {"data_cutoff_at": data["time_range"]["end"]},
            "profile": config,
            "deadline": time.monotonic() + 30,
            "llm": SimpleNamespace(configured=False, usage={}),
        }
    )
    try:
        output = await run({"query_prometheus": query})
    finally:
        attempt_context.reset(token)
    result = output["result"]
    validate_result(result, output["evidence"])
    assert any(expr.startswith("D02{") for expr in calls) == (criteria == "1.2")
    assert result["versions"]["criteria"] == criteria
    assert result["narrative_status"] == "omitted"
    topic = result["topics"][0]
    if criteria == "1.2":
        assert values(topic, "a")["namespace_connected_gpu_util"] == 20
    else:
        assert not any(
            "namespace_connected_gpu_util" in m["id"] for m in topic["metrics"]
        )
    assert result["topics"][1]["topic_id"] == "O09"


def test_eight_gpus_for_one_hour_keep_unobserved_start_out_of_gpu_hours():
    source = observations(*[("a", f"gpu-{i}", START, END, 10) for i in range(8)])
    for es in source.values():
        for r in es[0]["snapshot"]["data"]:
            r["values"] = [[START + 6.113 + 15 * i, "10"] for i in range(240)]
    v = values(report(source), "a")
    assert v["namespace_connected_gpu_count"] == 8
    assert v["observed_namespace_hours"] == pytest.approx(8 * (3600 - 6.113) / 3600)
    assert v["namespace_activity_valid_hours"] == v["observed_namespace_hours"]
    assert v["namespace_connected_gpu_util"] == 10


def test_pod_scope_keeps_allocation_namespaces_and_falls_back_on_incomplete_inputs():
    from ops_agent.namespace_usage import pod_namespace_scope

    source = observations(("a", "gpu-1", START, END, 20))
    source["D08"] = observations(("b", "gpu-2", START, END, 20))["D01"]
    assert pod_namespace_scope(source) == {"cpc-1": ["a", "b"]}
    source["D08"][0]["quality"]["complete"] = False
    assert pod_namespace_scope(source) == {}
    source["D08"] = []
    assert pod_namespace_scope(source) == {}


@pytest.mark.parametrize("topics", [["O08"], ["O08", "O07"]])
@pytest.mark.asyncio
async def test_namespace_only_narrows_pods_but_mixed_reports_keep_full_scope(topics):
    source = observations(("a", "gpu-1", START, END, 20))
    config = profile()
    calls = []

    async def query(args):
        calls.append(args["expr"])
        if args["expr"].startswith("DCGM_FI_DEV_GPU_UTIL{"):
            return source["D01"][0]["snapshot"]
        return {"data": []}

    data = dict(DATA, topic_ids=topics, group_by=["namespace"], timezone="UTC")
    token = attempt_context.set(
        {
            "claim": {
                "job_id": "fixture",
                "kind": "report",
                "input": data,
                "versions": {"criteria": "1.2"},
            },
            "context": {"data_cutoff_at": data["time_range"]["end"]},
            "profile": config,
            "deadline": time.monotonic() + 30,
            "llm": SimpleNamespace(configured=False, usage={}),
        }
    )
    try:
        output = await run({"query_prometheus": query})
    finally:
        attempt_context.reset(token)
    validate_result(output["result"], output["evidence"])
    pod_query = next(expr for expr in calls if expr.startswith("kube_pod_info{"))
    assert ('namespace=~"a"' in pod_query) == (topics == ["O08"])
    assert sum(expr.startswith("DCGM_FI_DEV_GPU_UTIL{") for expr in calls) == 1
    assert (
        values(output["result"]["topics"][0], "a")["namespace_connected_gpu_util"] == 20
    )
