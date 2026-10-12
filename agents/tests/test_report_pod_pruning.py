"""Report-only query pruning: identities, uncertainty and calculations survive."""

import copy
import json
import re
import time

import pytest

from agent_common.observation import Observation
from ops_agent.namespace_usage import gpu_pod_scope
from ops_agent import workflow
from ops_agent import collection
from ops_agent.additional_inputs import ADDITIONS
from test_report_minimization import fixture_collection, execute_fixture
from test_report_observation import DATA, START, END, evidence, row


def semantic(topic):
    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k != "evidence_refs"}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    return strip(
        {k: topic[k] for k in ("metrics", "facts", "status", "missing_inputs")}
    )


@pytest.mark.parametrize(
    "case",
    [
        "complete",
        "uid_conflict",
        "recreated",
        "moved",
        "gap",
        "missing_label",
        "partial",
        "regex",
    ],
)
async def test_same_namespace_pruning_preserves_results(monkeypatch, case):
    config, metrics, snapshots = fixture_collection()
    gpu = snapshots["D02"]["data"][0]
    pod = snapshots["D06"]["data"][0]
    snapshots["D06"]["data"] += [
        row(
            dict(namespace="gpu-jobs", pod=f"cpu-{i}", uid=f"cpu-{i}", node="node-1"),
            "1",
            end=END - 15,
        )
        for i in range(10)
    ]
    if case == "uid_conflict":
        other = copy.deepcopy(pod)
        other["metric"]["uid"] = "other"
        snapshots["D06"]["data"].append(other)
    elif case == "recreated":
        other = copy.deepcopy(pod)
        middle = START + 1800
        pod["values"] = [v for v in pod["values"] if v[0] < middle]
        other["values"] = [v for v in other["values"] if v[0] >= middle]
        other["metric"]["uid"] = "recreated"
        gpu["metric"].pop("uid")
        snapshots["D06"]["data"].append(other)
    elif case == "moved":
        other = copy.deepcopy(gpu)
        other["metric"]["node"] = "node-2"
        other["values"] = other["values"][120:]
        gpu["values"] = gpu["values"][:120]
        other_pod = copy.deepcopy(pod)
        other_pod["metric"]["node"] = "node-2"
        snapshots["D02"]["data"].append(other)
        snapshots["D06"]["data"].append(other_pod)
    elif case == "gap":
        pod["values"] = pod["values"][:50] + pod["values"][90:]
    elif case == "missing_label":
        gpu["metric"].pop("node")
    elif case == "partial":
        snapshots["D02"]["warnings"] = ["incomplete"]
    elif case == "regex":
        gpu["metric"]["pod"] = pod["metric"]["pod"] = "gpu.pod+[a]"
    topics = ["O01", "O08", "O11"]
    after, calls = await execute_fixture(config, metrics, snapshots, topics)
    expr = next(e for q, e in calls if q == "D06")
    assert ("pod=~" in expr) == (case not in {"missing_label", "partial"})
    monkeypatch.setattr(collection, "gpu_pod_scope", lambda *args: {})
    before, _ = await execute_fixture(config, metrics, snapshots, topics)
    assert [semantic(t) for t in after["result"]["topics"]] == [
        semantic(t) for t in before["result"]["topics"]
    ]

    def size(out):
        return sum(
            len(json.dumps(e["snapshot"]))
            for e in out["evidence"]
            if e["query_id"] == "D06"
        )

    assert size(after) <= size(before)
    if case not in {"missing_label", "partial"}:
        assert size(after) < size(before) / 3


@pytest.mark.parametrize(
    "failure",
    ["gap", "empty", "node", "pod", "namespace", "gpu_uuid", "large", "partial"],
)
def test_incomplete_identity_falls_back(failure):
    config, _, _ = fixture_collection()
    labels = dict(gpu_uuid="gpu", namespace="ns", pod="pod", node="node")
    item = evidence("D02", [row(labels)])
    item["quality"]["complete"] = True
    item["time_range"] = dict(DATA["time_range"])
    if failure == "gap":
        item["time_range"]["start"] = item["time_range"]["end"]
    elif failure == "empty":
        item["snapshot"]["data"] = []
    elif failure == "large":
        labels["pod"] = "a" * 4097
    elif failure == "partial":
        item["quality"]["complete"] = False
    else:
        labels.pop(failure)
    assert gpu_pod_scope({"D02": [item]}, config, DATA["time_range"]) == {}


async def test_collector_cache_includes_pod_scope_and_rca_default_is_broad():
    config, metrics, _ = fixture_collection()
    calls = []

    async def query(args):
        calls.append(args["expr"])
        return {"data": []}

    obs = Observation({"query_prometheus": query}, config, DATA, time.monotonic() + 30)
    await obs.collect("D06")
    await obs.collect("D06", pod_scope={"cpc-1": ["pod.a"]})
    await obs.collect("D06", pod_scope={"cpc-1": ["pod.b"]})
    await obs.collect("D06", pod_scope={"cpc-1": ["pod.a"]})
    assert len(calls) == 3 and "pod=~" not in calls[0]
    assert json.loads(re.search(r'pod=~("(?:[^"\\]|\\.)*")', calls[1])[1]) == r"pod\.a"
    with pytest.raises(ValueError):
        await obs.collect("D02", pod_scope={"cpc-1": ["pod"]})


@pytest.mark.parametrize("topic", ["O05", "O06", "O10"])
def test_pruned_logs_never_change_calculations(monkeypatch, topic):
    from test_report_observation import collected

    observed = collected()
    context = dict(
        incidents=[
            dict(
                id="incident",
                cluster_id="cpc-1",
                occurred_at=DATA["time_range"]["start"],
                target={"gpu_uuid": "GPU-1"},
            )
        ],
        rca_results=[],
        actions=[],
    )
    data = copy.deepcopy(DATA)
    data.update(action_record_ids=["action"], comparison_range=dict(DATA["time_range"]))
    context["actions"] = [dict(id="action", body={"execution": "performed"})]
    observed["D08"] = [
        evidence(
            "D08",
            [
                row(
                    dict(
                        gpu_uuid="GPU-1",
                        namespace="training",
                        pod="worker",
                        node="node-1",
                        uid="pod-1",
                        allocation_mode="exclusive",
                    ),
                    "1",
                )
            ],
        )
    ]
    observed["D11"] = [evidence("D11", [row(dict(gpu_uuid="GPU-1"), "100")])]
    observed["D11"][0]["quality"]["unit"] = "W"
    observed["comparison.D11"] = copy.deepcopy(observed["D11"])
    db = {"id": "db"}
    observed["D09"] = [evidence("D09", [])]
    observed["D13"] = [evidence("D13", [])]
    new = workflow.calculate(topic, data, observed, context, db)
    monkeypatch.setitem(workflow.PLAN, topic, (*workflow.PLAN[topic], "D09", "D13"))
    monkeypatch.setitem(ADDITIONS, topic, (*ADDITIONS[topic], "D09"))
    old = workflow.calculate(topic, data, observed, context, db)
    assert semantic(new) == semantic(old)
    assert any(m["value"] is not None for m in new["metrics"])
    assert not set(new["evidence_refs"]) & {"D09cpc-1", "D13cpc-1"}
