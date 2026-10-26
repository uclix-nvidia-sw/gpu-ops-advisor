"""Ops-owned PromQL. No RCA D registry or observation parser is consulted."""

import asyncio
import json
import time
import re
from collections import defaultdict, deque
from uuid import uuid4

from agent_common.contracts import timestamp
from agent_common.discovery import Discovery
from agent_common.grafana_time import mcp_time
from agent_common.observation import evidence_stamp, unwrap

from .report_contract import MAX_BYTES, MAX_POINTS, VERSION, iso
from .identity_transitions import (
    VERSION as TRANSITION_VERSION,
    identity,
    sample_bounds,
    verified_transitions,
)
from .collector_identity import groups, source_values, verified, JOB_FIELDS


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


def memory_queries(cluster):
    parts = []
    for field, metric in (
        ("used", "DCGM_FI_DEV_FB_USED"),
        ("free", "DCGM_FI_DEV_FB_FREE"),
    ):
        gpu = selector(metric, cluster)
        for measure, function in (
            ("sum", "sum_over_time"),
            ("count", "count_over_time"),
            ("min", "min_over_time"),
            ("max", "max_over_time"),
        ):
            parts.append(
                f'label_replace({function}({gpu}[1h] offset 1ms), "measure", "{field}_{measure}", "", "")'
            )
    return {"hourly_gpu_memory": " or ".join(parts)}


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
        self.collector_calls = 0
        self.collector_deadline = None
        self.transition_calls = 0
        self.transition_deadline = None

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

    async def collect(self, cluster, period, *, queries=None, uid=None):
        evidence = []
        if queries is None:
            try:
                uid, _ = await self.discovery.resolve(
                    "prometheus",
                    cluster["cluster_id"],
                    period,
                    cluster_labels=("cluster_id",),
                )
            except Exception:
                uid = None
        for name, expr in (
            hourly_queries(cluster) if queries is None else queries
        ).items():
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

    async def check_transitions(self, groups, *, reserved_calls=0):
        """Share bounded verification across clusters, current period before previous."""
        output = []
        for current in (True, False):
            batches = deque(
                self.transition_batches(*group, reserved_calls=reserved_calls)
                for group in groups
                if (group[1] == self.data["time_range"]) == current
            )
            while batches:
                stream = batches.popleft()
                try:
                    output.append(await anext(stream))
                except StopAsyncIteration:
                    continue
                batches.append(stream)
        return output

    async def transition_batches(
        self, cluster, period, uid, evidence, *, reserved_calls=0
    ):
        activity, _, counts = evidence
        audit = activity["quality"]["transition_verification"] = []
        if not uid or any(e["tool_status"] != "ok" for e in evidence):
            activity["quality"]["transition_skip_reason"] = "base_query_unavailable"
            return
        if self.transition_deadline is None:
            self.transition_deadline = min(self.deadline - 30, time.monotonic() + 60)
        selected = {
            (float(at), s["metric"].get("UUID"))
            for s in activity["snapshot"]["series"]
            if s["metric"].get("namespace") and s["metric"].get("pod")
            for at, _ in s["values"]
        }
        hours = defaultdict(dict)
        for s in counts["snapshot"]["series"]:
            gpu = s["metric"].get("UUID")
            for at, value in s["values"]:
                if gpu and float(value) > 1 and (float(at), gpu) in selected:
                    hours[float(at)][gpu] = float(value)
        for at, expected in sorted(hours.items()):
            gpu_ids = sorted(expected)
            # Bound exceptional raw reads; normal hours keep the three aggregate queries.
            for offset in range(0, len(gpu_ids), 16):
                batch = gpu_ids[offset : offset + 16]
                entry = dict(hour_end=iso(at), gpu_ids=batch, status="not_checked")
                audit.append(entry)
                if self.transition_calls + 2 > 32:
                    entry["reason"] = "transition_query_budget_exhausted"
                    continue
                if time.monotonic() >= self.transition_deadline:
                    entry["reason"] = "transition_deadline_exhausted"
                    continue
                if reserved_calls and self.calls + 2 + reserved_calls > 80:
                    entry["reason"] = (
                        "report_query_limit_exceeded"
                        if self.calls + 2 > 80
                        else "transition_query_budget_reserved"
                    )
                    continue
                pod_names = sorted(
                    {
                        s["metric"]["pod"]
                        for s in activity["snapshot"]["series"]
                        if s["metric"].get("UUID") in batch
                        and s["metric"].get("pod")
                        and any(float(t) == at for t, _ in s["values"])
                    }
                )

                def restrict(metric, label, names, namespace=True):
                    base = selector(metric, cluster, namespace=namespace)
                    pattern = json.dumps("|".join(re.escape(n) for n in names))
                    return base[:-1] + f",{label}=~{pattern}}}[1h] offset 1ms"

                expressions = [
                    restrict("DCGM_FI_DEV_GPU_UTIL", "UUID", batch, False),
                    restrict("kube_pod_info", "pod", pod_names),
                ]
                inputs, bounds, checks, reason = [], [], [], None
                rejected = []
                before = time.monotonic()
                try:
                    for expr in expressions:
                        args = dict(
                            datasourceUid=uid,
                            expr=expr,
                            queryType="instant",
                            endTime=mcp_time(iso(at)),
                        )
                        inputs.append(args)
                        self.transition_calls += 1
                        async with asyncio.timeout_at(self.transition_deadline):
                            rows = matrix(await self.call("query_prometheus", args))
                        bounds.append(sample_bounds(rows, at, cluster["cluster_id"]))
                    checks = verified_transitions(
                        bounds[0],
                        bounds[1],
                        at,
                        {g: expected[g] for g in batch},
                        cluster.get("namespaces"),
                        rejected=rejected,
                    )
                except Exception:
                    reason = "transition_verification_unavailable"
                entry.update(
                    status="query_failed" if reason else "checked",
                    reason=reason,
                    rejected=rejected,
                )
                yield dict(
                    id=str(uuid4()),
                    query_id="gpu_identity_transitions",
                    query_version=TRANSITION_VERSION,
                    cluster_id=cluster["cluster_id"],
                    scope={"clusters": [cluster]},
                    time_range=period,
                    input={"queries": inputs},
                    tool_status="unavailable" if reason else "ok",
                    snapshot={"checks": checks},
                    quality={
                        "reason": reason,
                        "hour_end": iso(at),
                        "gpu_count": len(batch),
                        "elapsed_seconds": time.monotonic() - before,
                        "raw_samples_stored": False,
                    },
                    **evidence_stamp(),
                )

    async def check_collectors(self, cluster, period, uid, evidence):
        # Optional raw reads stay inside the existing total call/byte/deadline limits.
        if self.collector_deadline is None:
            self.collector_deadline = min(self.deadline - 30, time.monotonic() + 20)
        stop = self.collector_deadline
        for e in evidence:
            if e["tool_status"] != "ok":
                continue
            ambiguous = defaultdict(list)
            for (at, key), rows in groups(e).items():
                sources = source_values(rows, e["query_id"])
                if sources and len(sources) > 1:
                    ambiguous[at].append((key, rows))
            for at, items in sorted(ambiguous.items()):
                if self.collector_calls >= 4 or time.monotonic() >= stop:
                    return
                query = e["query_id"]
                label = "pod" if query == "hourly_pod_identity" else "job_name"
                # Bound exceptional targets; skipped targets remain conservatively excluded.
                names = sorted({dict(key).get(label, "") for key, _ in items})[:64]
                metric = (
                    "kube_pod_info"
                    if query == "hourly_pod_identity"
                    else "kube_job_created"
                )
                expr = selector(metric, cluster)
                if query == "hourly_gpu_jobs":
                    expr = expr.replace(
                        "kube_job_created{",
                        '{__name__=~"' + "|".join(JOB_FIELDS) + '",',
                        1,
                    )
                expr = (
                    expr[:-1]
                    + f",{label}=~{json.dumps('|'.join(re.escape(n) for n in names))}}}[1h] offset 1ms"
                )
                args = dict(
                    datasourceUid=uid,
                    expr=expr,
                    queryType="instant",
                    endTime=mcp_time(iso(at)),
                )
                audit = dict(
                    hour_end=iso(at),
                    reason=None,
                    verified_groups=0,
                    raw_samples_stored=False,
                )
                e["quality"].setdefault("collector_verification", []).append(audit)
                self.collector_calls += 1
                try:
                    async with asyncio.timeout_at(stop):
                        raw = matrix(await self.call("query_prometheus", args))
                    bounds = []
                    for row in raw:
                        checked = sample_bounds([row], at, cluster["cluster_id"])[0]
                        checked["metric_name"] = row["metric"].get("__name__", metric)
                        bounds.append(checked)
                    for key, rows in items:
                        expected = {identity(labels) for labels, _ in rows}
                        selected = [
                            b for b in bounds if identity(b["labels"]) in expected
                        ]
                        if verified(at, rows, query, selected):
                            e["quality"].setdefault("collector_handoffs", []).append(
                                dict(at=at, identity=key, bounds=selected)
                            )
                            audit["verified_groups"] += 1
                except Exception:
                    audit["reason"] = "collector_verification_unavailable"
