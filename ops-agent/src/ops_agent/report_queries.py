"""Ops-owned PromQL. No RCA D registry or observation parser is consulted."""

import asyncio
import json
import time
from uuid import uuid4

from agent_common.contracts import timestamp
from agent_common.discovery import Discovery
from agent_common.grafana_time import mcp_time
from agent_common.observation import evidence_stamp, unwrap

from .report_contract import MAX_BYTES, MAX_POINTS, VERSION, iso


def selector(metric, cluster, *, namespace=True):
    labels = {"cluster_id": cluster["cluster_id"], "collection_path": "alloy-direct"}
    labels["job"] = (
        "nvidia-dcgm-exporter" if metric.startswith("DCGM_") else "kube-state-metrics"
    )
    terms = [f"{key}={json.dumps(value)}" for key, value in labels.items()]
    if namespace and cluster.get("namespaces") is not None:
        # Kubernetes namespaces cannot contain regex syntax; escape at both boundaries.
        import re

        terms.append(
            "namespace=~"
            + json.dumps("|".join(re.escape(n) for n in cluster["namespaces"]))
        )
    return metric + "{" + ",".join(terms) + "}"


def hourly_queries(cluster):
    gpu = selector("DCGM_FI_DEV_GPU_UTIL", cluster)
    # Retain source labels until validation: premature sum-by hides duplicates and Pod changes.
    activity = " or ".join(
        f'label_replace({function}({gpu}[1h] offset 1ms), "measure", "{name}", "", "")'
        for name, function in (
            ("activity_sum", "sum_over_time"),
            ("sample_count", "count_over_time"),
            ("minimum", "min_over_time"),
            ("maximum", "max_over_time"),
        )
    )
    pod = selector("kube_pod_info", cluster)
    all_gpu = selector("DCGM_FI_DEV_GPU_UTIL", cluster, namespace=False)
    identities = (
        f"count by (cluster_id, UUID) (count_over_time({all_gpu}[1h] offset 1ms))"
    )
    # Check other namespaces without returning their identities or observations.
    if cluster.get("namespaces") is not None:
        identities += f" and on (cluster_id, UUID) count by (cluster_id, UUID) (count_over_time({gpu}[1h] offset 1ms))"
    return {
        "hourly_gpu_activity": activity,
        "hourly_pod_identity": f"count_over_time({pod}[1h] offset 1ms) * (min_over_time({pod}[1h] offset 1ms) == 1) * (max_over_time({pod}[1h] offset 1ms) == 1) and on (cluster_id, namespace, pod) count by (cluster_id, namespace, pod) (count_over_time({gpu}[1h] offset 1ms))",
        "hourly_gpu_identity_count": identities,
    }


def matrix(response):
    if not isinstance(response, dict) or response.get("warnings"):
        raise ValueError("partial_or_invalid_prometheus_response")
    data = response.get("data", response)
    if isinstance(data, dict):
        data = data.get("result")
    if not isinstance(data, list) or any(
        not isinstance(row, dict)
        or not isinstance(row.get("metric"), dict)
        or not isinstance(row.get("values"), list)
        for row in data
    ):
        raise ValueError("invalid_prometheus_matrix")
    if sum(len(row["values"]) for row in data) > MAX_POINTS:
        raise ValueError("report_point_limit_exceeded")
    return data


class ReportQueries:
    def __init__(self, tools, data, deadline):
        self.tools, self.data, self.deadline = tools, data, deadline
        self.discovery = Discovery(self.call)
        self.calls = 0
        self.bytes_received = 0

    async def call(self, name, args):
        self.calls += 1
        if self.calls > 80:
            raise ValueError("report_query_limit_exceeded")
        async with asyncio.timeout_at(min(self.deadline, time.monotonic() + 30)):
            response = unwrap(await self.tools[name](args))
        self.bytes_received += len(json.dumps(response).encode())
        if self.bytes_received > MAX_BYTES:
            raise ValueError("report_response_limit_exceeded")
        return response

    async def collect(self, cluster, period):
        evidence = []
        try:
            uid, _ = await self.discovery.resolve(
                "prometheus",
                cluster["cluster_id"],
                period,
                cluster_labels=("cluster_id",),
            )
        except Exception:
            uid = None
        for name, expr in hourly_queries(cluster).items():
            before = time.monotonic()
            args = dict(
                datasourceUid=uid,
                expr=expr,
                queryType="range",
                stepSeconds=3600,
                startTime=mcp_time(iso(timestamp(period["start"]) + 3600)),
                endTime=mcp_time(period["end"]),
            )
            status, rows, reason = "ok", [], None
            try:
                if uid is None:
                    raise ValueError("report_datasource_unavailable")
                rows = matrix(await self.call("query_prometheus", args))
            except Exception as exc:
                # Upstream error text can contain secrets. Only emit owned failure codes.
                status = "unavailable"
                reason = (
                    str(exc)
                    if isinstance(exc, ValueError)
                    and str(exc)
                    in {
                        "report_datasource_unavailable",
                        "report_query_limit_exceeded",
                        "report_response_limit_exceeded",
                        "report_point_limit_exceeded",
                        "invalid_prometheus_matrix",
                        "partial_or_invalid_prometheus_response",
                    }
                    else "report_query_failed"
                )
            evidence.append(
                dict(
                    id=str(uuid4()),
                    query_id=name,
                    query_version=VERSION,
                    cluster_id=cluster["cluster_id"],
                    scope={"clusters": [cluster]},
                    time_range=period,
                    input=args,
                    tool_status=status,
                    snapshot={"series": rows},
                    quality={
                        "reason": reason,
                        "elapsed_seconds": time.monotonic() - before,
                        "aggregation": "hourly",
                        "sampling_interval_seconds": 15,
                        "source_selector": "alloy-direct",
                        "calculation_version": VERSION,
                    },
                    **evidence_stamp(),
                )
            )
        return evidence
