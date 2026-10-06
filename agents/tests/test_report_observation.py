import copy
import json
import re
import time

import pytest

from agent_common.contracts import timestamp
from agent_common.normalize import allocations
from agent_common.observation import Observation, series
from ops_agent.workflow import calculate


PERIOD = {"start": "2026-09-18T03:57:00Z", "end": "2026-09-18T04:57:00Z"}
START, END = timestamp(PERIOD["start"]), timestamp(PERIOD["end"])
DATA = {
    "scope": {"clusters": [{"cluster_id": "cpc-1", "namespaces": None}]},
    "time_range": PERIOD,
}


def profile():
    with open("agents/config.example.json", encoding="utf-8") as file:
        config = json.load(file)
    config["clusters"] = {
        "cpc-1": {"mimir_uid": "metrics", "metric_selector": {"cluster_id": "cpc-1"}}
    }
    return config


def evidence(query, rows, cluster="cpc-1"):
    return {
        "id": query + cluster,
        "query_id": query,
        "cluster_id": cluster,
        "tool_status": "ok" if rows else "empty",
        "quality": {"original_samples": True, "max_hold_seconds": 30},
        "snapshot": {"data": rows},
    }


def row(labels, value="0", start=START, end=END):
    return {
        "metric": labels,
        "values": [[t, value] for t in range(int(start), int(end) + 1, 15)],
    }


@pytest.mark.asyncio
async def test_large_pod_history_is_split_without_losing_original_samples():
    calls = []

    # Same scale as the affected CPC: 286 series and a one-hour range vector.
    async def query(args):
        calls.append(args)
        stop = timestamp(args["endTime"])
        length = int(re.search(r"\[(\d+)s\]$", args["expr"])[1])
        return {
            "data": [
                {
                    "metric": {"uid": f"pod-{i}"},
                    "values": [
                        [t, "1"]
                        for t in range(int(START), int(END) + 1, 15)
                        if stop - length < t <= stop
                    ],
                }
                for i in range(286)
            ]
        }

    obs = Observation(
        {"query_prometheus": query}, profile(), DATA, time.monotonic() + 30
    )
    result = await obs.collect("D06")
    assert len(calls) > 1
    assert len(calls) <= profile()["limits"]["max_queries"]
    assert all(
        e["tool_status"] == "ok" and e["quality"]["sample_count"] <= 5000
        for e in result
    )
    assert all('cluster_id="cpc-1"' in args["expr"] for args in calls)
    merged = series(result)
    assert len(merged) == 286
    assert {t for t, _ in merged[0]["samples"]} == set(
        range(int(START), int(END) + 1, 15)
    )


@pytest.mark.asyncio
async def test_split_queries_respect_budget_and_source_warnings():
    config = profile()
    config["limits"]["max_queries"] = 1

    async def large(args):
        return {"data": [row({"uid": str(i)}) for i in range(30)]}

    obs = Observation({"query_prometheus": large}, config, DATA, time.monotonic() + 30)
    result = await obs.collect("D06")
    assert obs.calls == 1
    assert result[-1]["quality"]["reason"] == "budget_exhausted"

    async def warning(args):
        return {"data": [row({"uid": "a"})], "warnings": ["partial upstream response"]}

    obs = Observation(
        {"query_prometheus": warning}, profile(), DATA, time.monotonic() + 30
    )
    result = await obs.collect("D06")
    assert result[0]["tool_status"] == "partial"
    assert not series(result)


@pytest.mark.asyncio
async def test_byte_limit_splits_and_single_oversized_sample_stays_partial():
    config = profile()
    config["limits"]["max_bytes"] = 3000

    async def query(args):
        stop = timestamp(args["endTime"])
        length = int(re.search(r"\[(\d+)s\]$", args["expr"])[1])
        return {
            "data": [
                {
                    "metric": {"uid": "pod"},
                    "values": [
                        [t, "1"]
                        for t in range(int(START), int(END) + 1, 15)
                        if stop - length < t <= stop
                    ],
                }
            ]
        }

    obs = Observation({"query_prometheus": query}, config, DATA, time.monotonic() + 30)
    result = await obs.collect("D06")
    assert obs.calls > 1
    assert all(e["tool_status"] == "ok" for e in result)
    config["limits"]["chunk_seconds"] = 1
    config["limits"]["max_queries"] = 2

    async def huge(args):
        return {"data": [row({"uid": "x" * 4000}, end=START)]}

    obs = Observation({"query_prometheus": huge}, config, DATA, time.monotonic() + 30)
    result = await obs.collect("D06")
    assert obs.calls == 2
    assert result[0]["quality"]["reason"] == "response_byte_limit"
    assert not series(result)


def collected():
    gpu = row(
        {"uuid": "GPU-1", "namespace": "training", "pod": "worker", "node": "node-1"}
    )
    pod = row(
        {"uid": "pod-1", "namespace": "training", "pod": "worker", "node": "node-1"},
        "1",
    )
    return {
        "D01": [evidence("D01", [gpu])],
        "D06": [evidence("D06", [pod])],
        "D08": [evidence("D08", [])],
    }


@pytest.mark.parametrize("topic", ["O02", "O08"])
def test_real_dcgm_pod_mapping_produces_facts_without_inventing_exclusivity(topic):
    result = calculate(topic, DATA, collected(), {}, {})
    metrics = {m["id"].split(".", 1)[1]: m for m in result["metrics"]}
    assert result["status"] == "partial"
    assert result["facts"]
    assert metrics["observed_gpu_count"]["value"] == 1
    assert metrics["mapped_gpu_hours"]["value"] == 1
    assert metrics["mapped_gpu_count"]["value"] == 1
    assert metrics["current_allocated_gpu"]["value"] is None
    assert metrics["allocated_gpu_hours"]["value"] is None
    assert set(metrics["mapped_gpu_hours"]["evidence_refs"]) == {"D01cpc-1", "D06cpc-1"}
    if topic == "O08":
        assert metrics["observed_namespace_hours.0"]["target"] == {
            "cluster_id": "cpc-1",
            "namespace": "training",
        }


def test_reused_pod_name_does_not_join_ambiguous_uids_or_other_clusters():
    source = collected()
    old = copy.deepcopy(source["D06"][0]["snapshot"]["data"][0])
    old["metric"]["uid"] = "old-pod"
    old["values"] = [[START + i * 15, "1"] for i in range(119)]
    source["D06"][0]["snapshot"]["data"].append(old)
    mapping = allocations(source["D01"], PERIOD, source["D06"], observed=True)
    assert mapping and all(
        m["start"] >= START + 1800 and m["pod_uid"] == "pod-1" for m in mapping
    )
    source["D06"][0]["cluster_id"] = "another-cluster"
    assert not allocations(source["D01"], PERIOD, source["D06"], observed=True)


def test_normalized_allocation_zero_is_not_an_active_allocation():
    e = evidence(
        "D08",
        [
            row(
                {
                    "gpu_uuid": "GPU-1",
                    "pod": "worker",
                    "pod_uid": "pod-1",
                    "allocation_mode": "exclusive",
                }
            )
        ],
    )
    assert not allocations([e], PERIOD)
    e["snapshot"]["data"][0]["values"] = [[START, "1"]]
    assert allocations([e], PERIOD)[0]["mode"] == "exclusive"


def test_unknown_allocation_mode_never_becomes_zero_exclusive_usage():
    source = collected()
    source["D08"] = [
        evidence(
            "D08",
            [row({"gpu_uuid": "GPU-1", "pod": "worker", "pod_uid": "pod-1"}, "1")],
        )
    ]
    result = calculate("O08", DATA, source, {}, {})
    assert all(
        m["value"] is None
        for m in result["metrics"]
        if m["id"].split(".")[1] in {"current_allocated_gpu", "allocation_group"}
    )


@pytest.mark.parametrize("reuse, expected_calls", [(False, 2), (True, 1)])
@pytest.mark.asyncio
async def test_identical_report_queries_reuse_samples_with_separate_evidence(
    reuse, expected_calls
):
    calls = []

    async def query(args):
        calls.append(args)
        return {"data": [row({"uuid": "gpu-1"})]}

    config = profile()
    config["limits"]["max_queries"] = expected_calls
    obs = Observation(
        {"query_prometheus": query},
        config,
        DATA,
        time.monotonic() + 30,
        reuse_queries=reuse,
    )
    first = await obs.collect("D01")
    second = await obs.collect("D02")
    assert obs.calls == len(calls) == expected_calls
    assert first[0]["id"] != second[0]["id"]
    assert second[0]["query_id"] == "D02"
    assert second[0]["snapshot"] == first[0]["snapshot"]
    assert ("reused_from_evidence" in second[0]["quality"]) == reuse


@pytest.mark.asyncio
async def test_response_reuse_does_not_cross_scope_period_or_failed_response():
    calls = []

    async def query(args):
        calls.append(args)
        return (
            {"data": [row({"uuid": "gpu-1"})], "warnings": ["partial"]}
            if len(calls) == 1
            else {"data": []}
        )

    obs = Observation(
        {"query_prometheus": query},
        profile(),
        DATA,
        time.monotonic() + 30,
        reuse_queries=True,
    )
    await obs.collect("D01")
    await obs.collect("D02")
    assert obs.calls == 2  # Incomplete response must not be reused.
    narrowed = await obs.collect("D02", namespace_scope={"cpc-1": ["a.b"]})
    assert obs.calls == 3
    assert narrowed[0]["quality"]["queried_namespaces"] == ["a.b"]
    assert r'namespace=~"a\\.b"' in calls[-1]["expr"]
    await obs.collect("D02", {"start": PERIOD["start"], "end": "2026-09-18T04:27:00Z"})
    assert obs.calls == 4
    assert DATA["scope"]["clusters"][0]["namespaces"] is None
    restricted = dict(
        DATA, scope={"clusters": [{"cluster_id": "cpc-1", "namespaces": ["allowed"]}]}
    )
    obs = Observation(
        {"query_prometheus": query}, profile(), restricted, time.monotonic() + 30
    )
    with pytest.raises(ValueError, match="authorized namespace"):
        await obs.collect("D06", namespace_scope={"cpc-1": ["outside"]})


@pytest.mark.asyncio
async def test_scoped_collection_reduces_large_pod_history_without_changing_namespace_metrics():
    from ops_agent.namespace_usage import pod_namespace_scope

    gpu_rows = [
        row(
            {
                "uuid": f"gpu-{i}",
                "namespace": "training",
                "pod": f"pod-{i}",
                "node": "node",
                "modelName": "fixture",
            },
            "10",
        )
        for i in range(8)
    ]
    pod_rows = [
        row(
            {
                "namespace": "training" if i < 8 else "background",
                "pod": f"pod-{i}",
                "node": "node",
                "uid": f"uid-{i}",
            },
            "1",
        )
        for i in range(286)
    ]

    async def query(args):
        expr = args["expr"]
        stop = timestamp(args["endTime"])
        length = int(re.search(r"\[(\d+)s\]$", expr)[1])
        rows = (
            gpu_rows
            if expr.startswith("DCGM_FI_DEV_GPU_UTIL{")
            else pod_rows
            if expr.startswith("kube_pod_info{")
            else []
        )
        if 'namespace=~"training"' in expr:
            rows = [r for r in rows if r["metric"]["namespace"] == "training"]
        return {
            "data": [
                {
                    "metric": r["metric"],
                    "values": [v for v in r["values"] if stop - length < v[0] <= stop],
                }
                for r in rows
            ]
        }

    outputs, calls = [], []
    for optimized in (False, True):
        obs = Observation(
            {"query_prometheus": query},
            profile(),
            DATA,
            time.monotonic() + 30,
            reuse_queries=optimized,
        )
        collected = {}
        for q in ("D01", "D02", "D08", "D06"):
            scope = pod_namespace_scope(collected) if optimized and q == "D06" else None
            collected[q] = await obs.collect(q, namespace_scope=scope)
        topic = calculate(
            "O08",
            dict(DATA, group_by=["namespace"]),
            collected,
            {},
            {},
            criteria_version="1.2",
        )
        outputs.append(
            [(m["id"], m["value"], m["unit"], m["quality"]) for m in topic["metrics"]]
        )
        calls.append(obs.calls)
    assert outputs[0] == outputs[1]
    assert calls[0] > 10
    assert calls[1] == 2  # D01/D02/D08 share the same observed DCGM source.


@pytest.mark.asyncio
async def test_fleet_bindings_preserve_gpu_identity_units_and_sample_gaps():
    data = copy.deepcopy(DATA)
    data["target"] = {"gpu_uuid": "GPU-1", "node": "node-1"}
    observations = {
        "dcgm_fi_dev_gpu_temp": ["40", "80", "0"],
        "dcgm_fi_dev_power_usage": ["100", "200", "0"],
    }

    async def query(args):
        metric = args["expr"].split("{", 1)[0]
        assert 'cluster_id="cpc-1"' in args["expr"]
        assert 'uuid="GPU-1"' in args["expr"]
        assert 'node="node-1"' in args["expr"]
        assert args["queryType"] == "instant"
        assert args["endTime"] == PERIOD["end"]
        return {
            "data": [
                {
                    "metric": {
                        "__name__": metric,
                        "uuid": "GPU-1",
                        "node": "node-1",
                        "job": "fleet-intelligence-agent",
                    },
                    "values": list(
                        zip([START, START + 60, START + 180], observations[metric])
                    ),
                }
            ]
        }

    obs = Observation(
        {"query_prometheus": query}, profile(), data, time.monotonic() + 30
    )
    collected = {q: await obs.collect(q) for q in ("D04", "D11")}
    temperature = calculate("O01", data, collected, {}, [])
    metric = next(m for m in temperature["metrics"] if m["id"] == "O01.temperature.0")
    assert metric["value"] == 40
    assert metric["unit"] == "celsius"
    assert metric["target"] == {"cluster_id": "cpc-1", "gpu_uuid": "GPU-1"}
    power = calculate("O09", data, collected, {}, [])
    assert power["metrics"][0]["value"] == pytest.approx(0.0025)
    assert power["metrics"][0]["unit"] == "kWh"
    # Three 30-second holds, including a real zero; 60/120-second gaps stay unknown.
    assert power["quality"]["observed_gpu_seconds"] == 90
    assert power["quality"]["coverage_scope"] == "observed_devices_only"
    assert set(power["evidence_refs"]) == {e["id"] for e in collected["D11"]}
