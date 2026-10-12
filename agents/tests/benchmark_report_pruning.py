"""Fixture-only Ops comparison: same 24h observations, no network, DB or LLM.

Extract the baseline's ops-agent/ and shared/python/ under a local directory. Run
this file twice, with PYTHONPATH pointing to baseline then current package src:

PYTHONPATH=.local/report-pruning/baseline/shared/python/src:.local/report-pruning/baseline/ops-agent/src:rcca-agent/src .venv/bin/python agents/tests/benchmark_report_pruning.py --output .local/report-pruning/ops-before.json
PYTHONPATH=shared/python/src:ops-agent/src:rcca-agent/src .venv/bin/python agents/tests/benchmark_report_pruning.py --output .local/report-pruning/ops-after.json

Pass --compare .local/report-pruning/ops-before.json on the current run to assert
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
from datetime import datetime, timezone

from agent_common.contracts import go_json, validate_result
from agent_common.runtime import attempt_context
from ops_agent.workflow import run
from test_report_minimization import fixture_collection
from test_report_observation import DATA as SOURCE_DATA, START, row
from test_binding_contract import verified

DATA = copy.deepcopy(SOURCE_DATA)
END = START + 86400
DATA["time_range"]["end"] = datetime.fromtimestamp(END, tz=timezone.utc).isoformat()


def inputs():
    config, metrics, snapshots = fixture_collection()
    # One GPU Pod and 99 CPU Pods in the same namespace defeat namespace-only pruning.
    gpu = snapshots["D02"]["data"][0]["metric"]
    snapshots["D06"]["data"] = snapshots["D06"]["data"][:1] + [
        row(
            dict(namespace="gpu-jobs", pod=f"cpu-{i}", uid=f"cpu-{i}", node="node-1"),
            "1",
        )
        for i in range(99)
    ]
    binding = verified(config, "D11", unit="W", cluster="cpc-1")
    metrics[binding["metric"]] = "D11"
    snapshots["D11"] = {"data": [row(gpu, "100")]}
    for query in ("D09", "D13"):
        binding = verified(
            config, query, unit="log", sample_type="log", cluster="cpc-1"
        )
        binding.update(
            timestamp_basis="loki_recorded_at",
            event_timestamp_rule="loki_recorded_at",
            json_target_fields={"node": "node"},
        )
        binding["environment"]["selector"]["job"] = f"fixture-{query}"
        for key in ("sample_interval", "invalid_values", "counter_reset"):
            binding[key] = {"mode": "not_applicable", "reason": "log fixture"}
    for query, snapshot in snapshots.items():
        snapshot["data"] = [
            row(
                r["metric"],
                r["values"][0][1],
                start=START - 86400 if query == "D11" else START,
                end=END - 15,
            )
            for r in snapshot["data"]
        ]
    return config, metrics, snapshots


async def once(scenario):
    config, metrics, snapshots = inputs()
    calls = []

    async def query(args):
        name = metrics[args["expr"].split("{")[0]]
        selected = snapshots[name]["data"]
        for label in ("namespace", "pod"):
            match = re.search(label + r'=~("(?:[^"\\]|\\.)*")', args["expr"])
            if name == "D06" and match:
                selected = [
                    r
                    for r in selected
                    if re.fullmatch(json.loads(match[1]), r["metric"].get(label, ""))
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

    async def logs(args):
        query_id = "D09" if "D09" in args["logql"] else "D13"
        response = {
            "data": {
                "result": [
                    {
                        "stream": {"node": "node-1"},
                        "values": [
                            [
                                str(int(START * 1e9) + i),
                                "fixture raw context " + "x" * 200,
                            ]
                            for i in range(1000)
                        ],
                    }
                ]
            }
        }
        calls.append((query_id, len(go_json(response))))
        return response

    topics = ["O01", "O08", "O11"] if scenario == "basic" else ["O05", "O06", "O10"]
    data = dict(
        DATA,
        group_by=["namespace"],
        topic_group_by={
            t: ["namespace"] if t == "O08" else ["cluster"] for t in topics
        },
        topic_ids=topics,
        timezone="UTC",
    )
    if scenario == "extended":
        data["action_record_ids"] = ["action"]
        data["comparison_range"] = {
            "start": datetime.fromtimestamp(START - 86400, tz=timezone.utc).isoformat(),
            "end": data["time_range"]["start"],
        }
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
                "incidents": [
                    dict(
                        id="incident",
                        cluster_id="cpc-1",
                        occurred_at=DATA["time_range"]["start"],
                        target={"gpu_uuid": "gpu-1"},
                    )
                ],
                "rca_results": [],
                "actions": [dict(id="action", body={"execution": "performed"})],
            },
            "profile": config,
            "deadline": time.monotonic() + 180,
            "llm": SimpleNamespace(configured=False, usage={}),
        }
    )
    started = time.perf_counter()
    try:
        output = await run({"query_prometheus": query, "query_loki_logs": logs})
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
        scenario=scenario,
        hours=24,
        pods_in_gpu_namespace=100,
        retained=retained,
    )


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--scenario", choices=("basic", "extended"), default="basic")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    results = [await once(args.scenario) for _ in range(args.repeats)]
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
