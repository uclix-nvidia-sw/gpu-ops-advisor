"""Manual, read-only Ops collection probe; never starts a Worker or publishes results."""

import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import time
from urllib.parse import urlsplit

from agent_common import observation
from ops_agent import report_queries
from ops_agent.report_contract import MAX_BYTES, previous_period, validate
from ops_agent.report_queries import ReportQueries, memory_queries
from ops_agent.workload_queries import workload_queries
from ops_agent.workload_context import context_queries

TOOLS = ("list_datasources", "list_prometheus_label_values", "query_prometheus")


def write_json(path, value):
    with open(
        path, "x", encoding="utf-8", opener=lambda p, f: os.open(p, f, 0o600)
    ) as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def check_input(data, timeout):
    validate(data)
    if "namespace_usage" not in data["topic_ids"]:
        raise ValueError("namespace_usage_required")
    if not math.isfinite(timeout) or not 0 < timeout <= 900:
        raise ValueError("timeout_must_be_between_zero_and_900")


def source_hashes():
    root = Path(report_queries.__file__).parent
    common = Path(observation.__file__).parent
    files = {"ops_collect_probe.py": Path(__file__)}
    files.update({"ops_agent/" + p.name: p for p in root.glob("*.py")})
    files.update(
        {
            "agent_common/" + name: common / name
            for name in (
                "contracts.py",
                "discovery.py",
                "observation.py",
                "grafana_mcp.py",
                "grafana_time.py",
            )
        }
    )
    return {
        name: hashlib.sha256(p.read_bytes()).hexdigest()
        for name, p in sorted(files.items())
    }


async def collect_evidence(collector, data, evidence, stages):
    """Mirror aggregate_report.run collection order; checked against it with fake MCP."""
    deadline = collector.deadline

    @asynccontextmanager
    async def stage(name):
        start = time.monotonic()
        calls, size = collector.calls, collector.bytes_received
        try:
            yield
        finally:
            stages.append(
                dict(
                    stage=name,
                    seconds=time.monotonic() - start,
                    attempted_calls=collector.calls - calls,
                    bytes_received=collector.bytes_received - size,
                )
            )

    pending = []
    async with stage("base"):
        for cluster in data["scope"]["clusters"]:
            for period in (data["time_range"], previous_period(data)):
                collected = await collector.collect(cluster, period)
                evidence.extend(collected)
                pending.append((cluster, period, collected))
    async with stage("transitions"):
        evidence.extend(
            await collector.check_transitions(
                [(c, p, e[0]["input"]["datasourceUid"], e) for c, p, e in pending],
                reserved_calls=4
                + sum(
                    len(memory_queries(c))
                    + len(workload_queries(c))
                    + len(context_queries(c))
                    for c in data["scope"]["clusters"]
                ),
            )
        )
    for name, queries in (
        ("memory", memory_queries),
        ("workload", workload_queries),
        ("context", context_queries),
    ):
        async with stage(name):
            for cluster, period, collected in pending:
                if period != data["time_range"]:
                    continue
                collector.deadline = min(deadline - 30, time.monotonic() + 20)
                try:
                    evidence.extend(
                        await collector.collect(
                            cluster,
                            period,
                            queries=queries(cluster),
                            uid=collected[0]["input"]["datasourceUid"],
                        )
                    )
                finally:
                    collector.deadline = deadline
    async with stage("collectors"):
        for cluster, period, collected in pending:
            uid = collected[0]["input"]["datasourceUid"]
            if uid:
                await collector.check_collectors(
                    cluster,
                    period,
                    uid,
                    [
                        e
                        for e in evidence
                        if e.get("cluster_id") == cluster["cluster_id"]
                        and e["time_range"] == period
                    ],
                )


async def probe(data, output, tools_context, *, timeout=900):
    """tools_context supplies fake tools in tests or an explicitly opened MCP client."""
    check_input(data, timeout)
    output = Path(output)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    started = time.monotonic()
    evidence, stages, calls = [], [], []
    summary = dict(
        status="started",
        input=data,
        source_hashes=source_hashes(),
        timeout_seconds=timeout,
        stages=stages,
        tool_calls=calls,
        incident_snapshot_collected=False,
        llm_called=False,
        published=False,
    )
    collector = None
    try:
        async with asyncio.timeout(timeout):
            async with tools_context() as tools:

                def measured(name):
                    async def call(args):
                        row = dict(tool=name, status="started")
                        calls.append(row)
                        start = time.monotonic()
                        try:
                            result = await tools[name](args)
                            row["status"] = "returned"
                            return result
                        except asyncio.CancelledError:
                            row["status"] = "cancelled"
                            raise
                        except Exception:
                            row["status"] = "failed"
                            raise
                        finally:
                            row["seconds"] = time.monotonic() - start

                    return call

                collector = ReportQueries(
                    {name: measured(name) for name in TOOLS}, data, started + timeout
                )
                await collect_evidence(collector, data, evidence, stages)
        # Finished describes execution, not valid/complete observation coverage.
        summary["status"] = "finished"
    except (Exception, asyncio.CancelledError) as exc:
        summary.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        summary.update(
            seconds=time.monotonic() - started,
            remote_tool_calls=len(calls),
            query_count=collector.calls if collector else 0,
            bytes_received=collector.bytes_received if collector else 0,
            query_limit=collector.query_limit if collector else None,
            transition_limit=collector.transition_limit if collector else None,
            evidence_count=len(evidence),
            unavailable_evidence=sum(e["tool_status"] != "ok" for e in evidence),
        )
        # Keep the small diagnostic even if the larger evidence write fails.
        write_json(output / "summary.json", summary)
        write_json(output / "evidence.json", evidence)
    return summary


@asynccontextmanager
async def connect_mcp(url, headers=None):
    # Match NAT dict conversion, then reuse the product text/error adapter.
    from agent_common.grafana_mcp import GrafanaMCPClient, _tool_function

    async with GrafanaMCPClient(
        url, tool_call_timeout=timedelta(seconds=30), custom_headers=headers
    ) as client:
        available = await client.get_tools()
        if set(TOOLS) - available.keys():
            raise ValueError("Configured Grafana read tools are unavailable")

        def invoke(tool):
            adapter = _tool_function(tool)

            async def call(value):
                return await adapter(tool.input_schema.model_validate(value))

            return call

        yield {name: invoke(available[name]) for name in TOOLS}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input", type=Path, help="Reviewed aggregate input JSON, not a saved report"
    )
    parser.add_argument(
        "output", type=Path, help="New private local directory; must not exist"
    )
    parser.add_argument(
        "--mcp-url", required=True, help="Approved streamable HTTP MCP endpoint"
    )
    parser.add_argument("--timeout-seconds", type=float, default=900)
    parser.add_argument(
        "--execute", action="store_true", help="Explicitly authorize real MCP reads"
    )
    args = parser.parse_args()
    if not args.execute:
        parser.error("Real reads require --execute and separate operational approval")
    endpoint = urlsplit(args.mcp_url)
    if (
        endpoint.scheme not in {"http", "https"}
        or not endpoint.hostname
        or endpoint.username
        or endpoint.password
        or endpoint.query
        or endpoint.fragment
    ):
        parser.error("Use an HTTP(S) endpoint without credentials, query or fragment")
    try:
        raw = args.input.read_bytes()
        if len(raw) > MAX_BYTES:
            raise ValueError("input_too_large")
        data = json.loads(raw)
        check_input(data, args.timeout_seconds)

        @asynccontextmanager
        async def connect():
            headers = json.loads(os.environ.get("OPS_PROBE_MCP_HEADERS", "{}"))
            if not isinstance(headers, dict) or any(
                not isinstance(k, str) or not isinstance(v, str)
                for k, v in headers.items()
            ):
                raise ValueError("invalid_headers")
            async with connect_mcp(args.mcp_url, headers) as tools:
                yield tools

        asyncio.run(probe(data, args.output, connect, timeout=args.timeout_seconds))
    except (Exception, KeyboardInterrupt) as exc:
        # Only this CLI message is sanitized; SDK logs require private stderr handling.
        print(f"OPS_COLLECTION_PROBE_FAILED {type(exc).__name__}")
        return 1
    print(
        "OPS_COLLECTION_PROBE_FINISHED (inspect evidence coverage; not a published report)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
