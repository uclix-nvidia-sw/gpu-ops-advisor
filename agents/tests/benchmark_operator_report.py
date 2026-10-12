"""Compare operator-report defaults with the same synthetic 24h observations.

Extract baseline Ops/shared Python under .local/operator-report/baseline, then run:
PYTHONPATH=.local/operator-report/baseline/shared/python/src:.local/operator-report/baseline/ops-agent/src:agents/tests .venv/bin/python agents/tests/benchmark_operator_report.py --mode previous --output .local/operator-report/before.json
PYTHONPATH=shared/python/src:ops-agent/src:agents/tests .venv/bin/python agents/tests/benchmark_operator_report.py --mode proposed --output .local/operator-report/after.json --compare .local/operator-report/before.json

No network, database or LLM is used. Bytes are uncompressed JSON, not database
storage. Incident context is a fixture; its database retrieval cost is excluded.
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
from benchmark_report_pruning import DATA, START, inputs


async def once(mode, scenario):
    config, metrics, snapshots = inputs()
    # Give the retained hourly graph a low-activity night and active daytime.
    for series in snapshots["D02"]["data"]:
        series["values"] = [
            [at, "2" if (at - START) < 4 * 3600 else "60"] for at, _ in series["values"]
        ]
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

    topics = {
        "basic": ["O01", "O08", "O11"],
        "equipment": ["O01"],
        "incidents": ["O05"],
    }[scenario]
    if scenario == "basic" and mode == "proposed":
        topics.insert(1, "O05")
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
                "job_id": "fixture-operator-benchmark",
                "kind": "report",
                "input": data,
                "versions": {"criteria": "1.3"},
            },
            "context": {
                "data_cutoff_at": data["time_range"]["end"],
                "incidents": [
                    dict(
                        id="11111111-1111-4111-8111-111111111111",
                        cluster_id="cpc-1",
                        occurred_at=data["time_range"]["start"],
                        alarm_status="firing",
                        target={"gpu_uuid": "gpu-1", "node": "node-1"},
                    )
                ],
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
    result = output["result"]
    validate_result(result, output["evidence"])
    retained = {
        t["topic_id"]: dict(
            status=t["status"],
            missing_inputs=t["missing_inputs"],
            metrics=[
                {k: v for k, v in m.items() if k not in {"id", "evidence_refs"}}
                for m in t["metrics"]
            ],
        )
        for t in result["topics"]
        if scenario != "basic" or t["topic_id"] in {"O01", "O08", "O11"}
    }
    return dict(
        mode=mode,
        scenario=scenario,
        report_seconds=elapsed,
        collection_seconds=result["quality"]["collection"]["elapsed_seconds"],
        query_calls=len(calls),
        query_ids=sorted(set(q for q, _ in calls)),
        response_json_bytes=sum(size for _, size in calls),
        d06_response_json_bytes=sum(size for q, size in calls if q == "D06"),
        evidence_snapshot_bytes=sum(
            len(go_json(e["snapshot"])) for e in output["evidence"]
        ),
        result_json_bytes=len(go_json(result)),
        narrative_json_bytes=len(go_json(result.get("narrative", []))),
        narrative_characters=sum(
            len(s.get("text", "")) for s in result.get("narrative", [])
        ),
        findings_count=sum(len(t.get("findings", [])) for t in result["topics"]),
        retained=retained,
    )


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("previous", "proposed"), required=True)
    parser.add_argument(
        "--scenario", choices=("basic", "equipment", "incidents"), default="basic"
    )
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    samples = [await once(args.mode, args.scenario) for _ in range(args.repeats)]
    result = {
        k: statistics.median(s[k] for s in samples)
        if k.endswith("_seconds")
        else samples[0][k]
        for k in samples[0]
    }
    if args.compare:
        before = json.loads(args.compare.read_text(encoding="utf-8"))
        assert before["retained"] == result["retained"], (
            "shared topic calculations changed"
        )
        result["retained_calculations_match"] = True
    result.update(
        repeats=args.repeats,
        hours=24,
        pods_in_gpu_namespace=100,
        scope="synthetic observations/context; no DB, network, MCP transport or LLM",
    )
    args.output.write_text(
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
