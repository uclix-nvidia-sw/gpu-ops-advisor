"""Fixture-only Ops comparison: same 1h observations, no network, DB or LLM.

Extract the baseline's ops-agent/ and shared/python/ under a local directory. Run
this file twice, with PYTHONPATH pointing to baseline then current package src:

PYTHONPATH=.local/minimal-report/baseline/shared/python/src:.local/minimal-report/baseline/ops-agent/src:rcca-agent/src .venv/bin/python agents/tests/benchmark_report_minimization.py --output .local/minimal-report/ops-before.json
PYTHONPATH=shared/python/src:ops-agent/src:rcca-agent/src .venv/bin/python agents/tests/benchmark_report_minimization.py --output .local/minimal-report/ops-after.json

Pass --compare .local/minimal-report/ops-before.json on the current run to assert
exact retained metric/status/missing-input equality.
Timings are local collector/calculation medians, not production API latency.
"""

import argparse
import asyncio
import copy
import json
from pathlib import Path
import re
import statistics
import time
from types import SimpleNamespace
from datetime import datetime

from agent_common.contracts import go_json, validate_result
from agent_common.runtime import attempt_context
from ops_agent.workflow import run
from test_report_minimization import fixture_collection, OMITTED_METRICS
from test_report_observation import DATA, END, row


def inputs():
    config, metrics, snapshots = fixture_collection()
    snapshots["D06"]["data"] = snapshots["D06"]["data"][:1] + [
        row(
            dict(namespace="unrelated", pod=f"pod-{i}", uid=f"uid-{i}", node="node-1"),
            "1",
            end=END - 15,
        )
        for i in range(200)
    ]
    snapshots["D20"]["data"] = [
        row(
            dict(node=f"node-{node}", condition=condition, status=status),
            "1" if status == "true" else "0",
            end=END - 15,
        )
        for node in range(17)
        for condition in ("Ready", "MemoryPressure", "DiskPressure")
        for status in ("true", "false", "unknown")
    ]
    snapshots["D18"]["data"] = [row(dict(node="node-1"), "25", end=END - 15)]
    snapshots["D19"]["data"] = [
        row(dict(node="node-1", window=window), "1", end=END - 15)
        for window in ("1m", "5m", "15m")
    ]
    return config, metrics, snapshots


async def once():
    config, metrics, snapshots = inputs()
    calls = []

    async def query(args):
        name = metrics[args["expr"].split("{")[0]]
        selected = snapshots[name]["data"]
        match = re.search(r'namespace=~"([^"]+)"', args["expr"])
        if name == "D06" and match:
            pattern = json.loads('"' + match[1] + '"')
            selected = [
                r
                for r in selected
                if re.fullmatch(pattern, r["metric"].get("namespace", ""))
            ]
        stop = datetime.fromisoformat(
            args["endTime"].replace("Z", "+00:00")
        ).timestamp()
        length = int(re.search(r"\[(\d+)s\]$", args["expr"])[1])
        response = {
            "data": [
                {
                    **r,
                    "values": [p for p in r["values"] if stop - length < p[0] <= stop],
                }
                for r in selected
            ]
        }
        calls.append((name, len(go_json(response))))
        return copy.deepcopy(response)

    topics = ["O01", "O08", "O11"]
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
                "job_id": "fixture-minimal-benchmark",
                "kind": "report",
                "input": data,
                "versions": {"criteria": "1.3"},
            },
            "context": {
                "data_cutoff_at": data["time_range"]["end"],
                "incidents": [],
                "rca_results": [],
                "actions": [],
            },
            "profile": config,
            "deadline": time.monotonic() + 180,
            "llm": SimpleNamespace(configured=False, usage={}),
        }
    )
    started = time.perf_counter()
    try:
        output = await run({"query_prometheus": query})
    finally:
        attempt_context.reset(token)
    elapsed = time.perf_counter() - started
    validate_result(output["result"], output["evidence"])
    started = time.perf_counter()
    encoded = go_json(output["result"])
    serialization = time.perf_counter() - started
    retained = [
        dict(
            topic=t["topic_id"],
            status=t["status"],
            missing_inputs=t["missing_inputs"],
            metrics=[
                {
                    **{k: v for k, v in m.items() if k not in {"id", "evidence_refs"}},
                    "name": m["id"].split(".")[1],
                }
                for m in t["metrics"]
                if m["id"].split(".")[1] not in OMITTED_METRICS
            ],
        )
        for t in output["result"]["topics"]
    ]
    return dict(
        report_seconds=elapsed,
        collection_seconds=output["result"]["quality"]["collection"]["elapsed_seconds"],
        serialization_seconds=serialization,
        query_calls=len(calls),
        query_ids=sorted(set(q for q, size in calls)),
        response_json_bytes=sum(size for q, size in calls),
        d06_response_json_bytes=sum(size for q, size in calls if q == "D06"),
        evidence_snapshot_bytes=sum(
            len(go_json(e["snapshot"])) for e in output["evidence"]
        ),
        result_json_bytes=len(encoded),
        node_condition_series=153,
        node_condition_intervals=153 * 240,
        retained=retained,
    )


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    results = [await once() for _ in range(args.repeats)]
    result = {
        k: statistics.median(r[k] for r in results)
        if k.endswith("_seconds")
        else results[0][k]
        for k in results[0]
    }
    if args.compare:
        previous = json.loads(args.compare.read_text(encoding="utf-8"))
        assert previous["retained"] == result["retained"], (
            "retained calculations changed"
        )
        result["retained_calculations_match"] = True
    result["repeats"] = args.repeats
    result["scope"] = (
        "synthetic local collector/calculation; no real Grafana, MCP transport, LLM or DB"
    )
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "retained"},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
