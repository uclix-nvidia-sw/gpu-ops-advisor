"""Basic report minimization preserves core calculations and source evidence."""

import copy
import json
import re
import time
from types import SimpleNamespace

import pytest

from agent_common.contracts import validate_result
from agent_common.runtime import attempt_context
from ops_agent import workflow
from ops_agent.basic_observations import basic_observations
from ops_agent.namespace_usage import pod_namespace_scope
from test_binding_contract import profile, verified
from test_report_observation import DATA, START, END, evidence, row


OMITTED = {"D15", "D18", "D19"}
OMITTED_METRICS = {
    "gpu_memory_free_mean",
    "node_cpu_used_mean",
    "node_load_by_window",
    "recorded_memory_free",
    "recorded_cpu_used",
    "recorded_node_load",
}


def semantic_metrics(topic):
    return [
        {**m, "id": ".".join(m["id"].split(".")[:2])}
        for m in topic["metrics"]
        if m["id"].split(".")[1] not in OMITTED_METRICS
    ]


def test_only_basic_o01_drops_optional_queries_and_empty_outputs():
    config = profile()
    old = set(workflow.query_ids("O01", "1.2", profile=config))
    new = set(workflow.query_ids("O01", "1.3", profile=config))
    assert old - new == OMITTED and not new - old
    for topic in ("O03", "O04"):
        assert "D15" in workflow.query_ids(topic, "1.3", profile=config)
    assert workflow.query_ids("O01", "1.3") == workflow.query_ids("O01", "1.2")
    empty = workflow.calculate(
        "O01", DATA, {}, {}, {}, criteria_version="1.3", profile=config
    )
    assert not {m["id"].split(".")[1] for m in empty["metrics"]} & OMITTED_METRICS
    assert {q["query_id"] for q in empty["quality"]["additional_inputs"]} == {
        "D16",
        "D20",
    }


@pytest.mark.parametrize("state", ["complete", "empty", "failed", "conflict"])
def test_basic_result_keeps_condition_durations_and_raw_evidence_without_interval_copy(
    state,
):
    units = {
        "D03": "MiB",
        "D04": "celsius",
        "D15": "MiB",
        "D16": "MiB",
        "D18": "percent",
        "D19": "load",
        "D20": "boolean",
    }
    collected = {}
    for query, unit in units.items():
        labels = {"gpu_uuid": "gpu-1", "node": "node-1", "window": "1m"}
        if query == "D20":
            labels = {"node": "node-1", "condition": "Ready", "status": "true"}
        rows = [row(labels, "1" if query == "D20" else "25")]
        if query == "D16":
            rows = [row(labels, "100")]
        item = evidence(query, rows)
        item["quality"].update(unit=unit, sample_type="gauge", complete=True)
        item["time_range"] = DATA["time_range"]
        collected[query] = [item]
    if state == "empty":
        collected["D20"][0].update(tool_status="empty", snapshot={"data": []})
    elif state == "failed":
        collected["D20"][0].update(tool_status="unavailable", snapshot={"data": []})
        collected["D20"][0]["quality"].update(complete=False, reason="query_failed")
    elif state == "conflict":
        collected["D20"][0]["snapshot"]["data"][0]["values"].append([START, "0"])
    original = copy.deepcopy(collected)
    config = profile()
    old = workflow.calculate(
        "O01", DATA, collected, {}, {}, criteria_version="1.2", profile=config
    )
    # Reproduce the previous 1.3 addition on top of the preserved 1.2 calculation.
    basic_observations(old, DATA, collected)
    new = workflow.calculate(
        "O01", DATA, collected, {}, {}, criteria_version="1.3", profile=config
    )
    assert semantic_metrics(old) == semantic_metrics(new)
    assert (
        new["facts"] == old["facts"] and new["missing_inputs"] == old["missing_inputs"]
    )
    assert "node_condition_observations" in old["quality"]
    assert "node_condition_observations" not in new["quality"]
    assert collected == original
    assert not set(new["evidence_refs"]) & {
        e["id"] for q in OMITTED for e in collected[q]
    }
    assert collected["D20"][0]["id"] in new["evidence_refs"]


def fixture_collection():
    config = profile()
    units = {
        "D02": "percent",
        "D03": "MiB",
        "D04": "celsius",
        "D06": "info",
        "D10": "boolean",
        "D15": "MiB",
        "D16": "MiB",
        "D18": "percent",
        "D19": "load",
        "D20": "boolean",
        "D22": "seconds",
    }
    metrics = {}
    for query, unit in units.items():
        binding = verified(
            config,
            query,
            unit=unit,
            cluster="cpc-1",
            sample_type="info" if query == "D06" else "gauge",
        )
        binding["target_labels"].update(
            condition="condition", status="status", window="window"
        )
        metrics[binding["metric"]] = query
    gpu = dict(
        UUID="gpu-1",
        namespace="gpu-jobs",
        pod="gpu-pod",
        uid="gpu-pod-uid",
        node="node-1",
        modelName="fixture-gpu",
    )
    snapshots = {query: {"data": []} for query in units}
    snapshots["D02"]["data"] = [row(gpu, "0", end=END - 15)]
    snapshots["D06"]["data"] = [
        row({k: v for k, v in gpu.items() if k != "UUID"}, "1", end=END - 15)
    ] + [
        row(
            dict(namespace="unrelated", pod=f"pod-{i}", uid=f"uid-{i}", node="node-1"),
            "1",
            end=END - 15,
        )
        for i in range(8)
    ]
    for query, value in (("D03", "25"), ("D04", "40"), ("D15", "75"), ("D16", "100")):
        snapshots[query]["data"] = [row(gpu, value, end=END - 15)]
    snapshots["D20"]["data"] = [
        row(dict(node="node-1", condition="Ready", status="true"), "1", end=END - 15)
    ]
    snapshots["D10"]["data"] = [
        row(dict(job="scrape", instance="target"), "1", end=END - 15)
    ]
    snapshots["D22"]["data"] = [
        row(dict(job="scrape", instance="target"), "0.1", end=END - 15)
    ]
    return config, metrics, snapshots


async def execute_fixture(config, metrics, snapshots, topics, criteria="1.3"):
    calls = []

    async def query(args):
        name = metrics[args["expr"].split("{")[0]]
        calls.append((name, args["expr"]))
        response = copy.deepcopy(snapshots[name])
        match = re.search(r'namespace=~"([^"]+)"', args["expr"])
        if name == "D06" and match:
            response["data"] = [
                r
                for r in response["data"]
                if re.fullmatch(
                    json.loads('"' + match[1] + '"'), r["metric"].get("namespace", "")
                )
            ]
        return response

    data = dict(
        DATA,
        group_by=["namespace"],
        topic_group_by={
            t: ["namespace"] if t == "O08" else ["cluster"] for t in topics
        },
        topic_ids=topics,
        timezone="UTC",
    )
    token = attempt_context.set(
        {
            "claim": {
                "job_id": "fixture-minimal",
                "kind": "report",
                "input": data,
                "versions": {"criteria": criteria},
            },
            "context": {
                "data_cutoff_at": data["time_range"]["end"],
                "incidents": [],
                "rca_results": [],
                "actions": [],
            },
            "profile": config,
            "deadline": time.monotonic() + 60,
            "llm": SimpleNamespace(configured=False, usage={}),
        }
    )
    try:
        output = await workflow.run({"query_prometheus": query})
    finally:
        attempt_context.reset(token)
    validate_result(output["result"], output["evidence"])
    return output, calls


@pytest.mark.parametrize(
    "topics,criteria,narrowed",
    [
        (["O01", "O08", "O11"], "1.3", True),
        (["O08", "O01"], "1.3", True),
        (["O11", "O08"], "1.3", True),
        (["O08"], "1.2", True),
        (["O01", "O08", "O11"], "1.2", False),
        (["O08", "O07"], "1.3", False),
        (["O08", "O03"], "1.3", False),
    ],
)
async def test_only_safe_composite_reports_narrow_d06(topics, criteria, narrowed):
    config, metrics, snapshots = fixture_collection()
    output, calls = await execute_fixture(config, metrics, snapshots, topics, criteria)
    pod_expr = next(expr for query, expr in calls if query == "D06")
    assert ("namespace=~" in pod_expr) == narrowed
    if criteria == "1.3" and "O01" in topics:
        assert not {q for q, expr in calls} & OMITTED
    if "O03" in topics:
        assert "D15" in {q for q, expr in calls}
    activity = next(t for t in output["result"]["topics"] if t["topic_id"] == "O08")
    assert any(
        m["value"] == 0
        for m in activity["metrics"]
        if "namespace_connected_gpu_util" in m["id"]
    )
    if criteria == "1.3":
        assert any(
            m["value"] == 3600
            for m in activity["metrics"]
            if "observed_low_activity_seconds" in m["id"]
        )


@pytest.mark.parametrize(
    "case",
    [
        "complete",
        "identity_conflict",
        "missing_pod",
        "activity_gap",
        "incomplete_inventory",
    ],
)
async def test_narrowed_default_keeps_all_retained_calculations_and_reduces_pod_evidence(
    monkeypatch,
    case,
):
    config, metrics, snapshots = fixture_collection()
    if case == "identity_conflict":
        duplicate = copy.deepcopy(snapshots["D06"]["data"][0])
        duplicate["metric"]["uid"] = "conflicting-uid"
        snapshots["D06"]["data"].append(duplicate)
    elif case == "missing_pod":
        snapshots["D06"]["data"] = snapshots["D06"]["data"][1:]
    elif case == "activity_gap":
        snapshots["D02"]["data"][0]["values"] = snapshots["D02"]["data"][0]["values"][
            ::4
        ]
    elif case == "incomplete_inventory":
        snapshots["D02"]["warnings"] = ["fixture partial response"]
    topics = ["O01", "O08", "O11"]
    minimal, _ = await execute_fixture(config, metrics, snapshots, topics)
    collect_report = workflow.collect_report

    async def broad_collection(
        tools, profile, data, deadline, order, namespace_only, core_queries=None
    ):
        return await collect_report(
            tools, profile, data, deadline, order, False, core_queries
        )

    monkeypatch.setattr(workflow, "collect_report", broad_collection)
    broad, _ = await execute_fixture(config, metrics, snapshots, topics)

    def without_refs(topic):
        return [
            {k: v for k, v in m.items() if k != "evidence_refs"}
            for m in topic["metrics"]
        ]

    for new, old in zip(minimal["result"]["topics"], broad["result"]["topics"]):
        assert without_refs(new) == without_refs(old)
        assert (
            new["status"] == old["status"]
            and new["missing_inputs"] == old["missing_inputs"]
        )

    def pod_bytes(output):
        return sum(
            len(json.dumps(e["snapshot"]))
            for e in output["evidence"]
            if e["query_id"] == "D06"
        )

    if case == "incomplete_inventory":
        assert pod_bytes(minimal) == pod_bytes(broad)
    else:
        assert pod_bytes(minimal) < pod_bytes(broad) / 4


@pytest.mark.parametrize("failure", ["missing", "partial", "empty", "unlabeled"])
def test_namespace_narrowing_preserves_full_scope_without_complete_clues(failure):
    config = profile()
    item = evidence(
        "D02", [row(dict(gpu_uuid="gpu-1", namespace="gpu-jobs", pod="gpu-pod"))]
    )
    item["quality"].update(complete=True)
    if failure == "partial":
        item["quality"]["complete"] = False
    elif failure == "empty":
        item.update(tool_status="empty", snapshot={"data": []})
    elif failure == "unlabeled":
        del item["snapshot"]["data"][0]["metric"]["namespace"]
    assert (
        pod_namespace_scope({} if failure == "missing" else {"D02": [item]}, config)
        == {}
    )
