"""Report-only planning around the unchanged shared observation collector."""

import math
import time

from agent_common.contracts import timestamp
from agent_common.observation import Observation

from .namespace_usage import pod_namespace_scope


REPORT_LIMITS = {"max_queries", "chunk_seconds", "max_rows"}


def report_profile(profile):
    overrides = profile.get("report", {}).get("limits", {})
    if set(overrides) - REPORT_LIMITS or any(
        type(v) is not int or v <= 0 for v in overrides.values()
    ):
        raise ValueError("invalid report collection limits")
    # Only Ops calls this. Never modify the shared/RCA profile object.
    return {
        **profile,
        "limits": {"chunk_seconds": 3600, **profile["limits"], **overrides},
    }


def collection_plan(profile, data, order):
    limits = profile["limits"]
    tasks = [
        dict(query_id=q, key=q, cluster=c, period=data["time_range"])
        for q in order
        for c in data["scope"]["clusters"]
    ]
    if "O10" in data["topic_ids"] and data.get("comparison_range"):
        tasks += [
            dict(
                query_id="D11",
                key="comparison.D11",
                cluster=c,
                period=data["comparison_range"],
            )
            for c in data["scope"]["clusters"]
        ]
    for task in tasks:
        seconds = timestamp(task["period"]["end"]) - timestamp(task["period"]["start"])
        task["planned_calls"] = math.ceil(seconds / limits["chunk_seconds"])
    reason = None
    if any(t["query_id"] not in profile["queries"] for t in tasks):
        reason = "collection_query_unconfigured"
    elif any(
        not 0
        < timestamp(t["period"]["end"]) - timestamp(t["period"]["start"])
        <= limits["max_range_seconds"]
        for t in tasks
    ):
        reason = "range_budget_exhausted"
    elif sum(t["planned_calls"] for t in tasks) > limits["max_queries"]:
        reason = "collection_plan_budget_exceeded"
    return tasks, reason


def covered_ranges(evidence, statuses):
    spans = sorted(
        (timestamp(e["time_range"]["start"]), timestamp(e["time_range"]["end"]))
        for e in evidence
        if e["tool_status"] in statuses and e["quality"].get("complete") is True
    )
    merged = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return sum(end - start for start, end in merged)


async def collect_report(tools, profile, data, deadline, order, namespace_only):
    profile = report_profile(profile)
    limits = profile["limits"]
    tasks, rejected = collection_plan(profile, data, order)
    collectors = {}
    for cluster in data["scope"]["clusters"]:
        scoped = {**data, "scope": {"clusters": [cluster]}}
        collectors[cluster["cluster_id"]] = Observation(
            tools,
            {**profile, "limits": dict(limits)},
            scoped,
            deadline,
            reuse_queries=True,
        )
    collected, evidence, summaries = {}, [], []
    calls = discovery_calls = 0
    for index, task in enumerate(tasks):
        query, cluster, period = (
            task["query_id"],
            task["cluster"]["cluster_id"],
            task["period"],
        )
        obs = collectors[cluster]
        remaining = tasks[index:]
        # Reserve every later query/cluster's initial plan, then share spare calls.
        spare = max(
            0,
            limits["max_queries"] - calls - sum(t["planned_calls"] for t in remaining),
        )
        allowance = min(
            limits["max_queries"] - calls,
            task["planned_calls"] + spare // len(remaining),
        )
        obs.profile["limits"]["max_queries"] = obs.calls + allowance
        obs.profile["limits"]["max_discovery_calls"] = obs.discovery_calls + max(
            0, limits.get("max_discovery_calls", 64) - discovery_calls
        )
        # A slow source cannot consume all the time reserved for later sources.
        obs.deadline = min(
            deadline,
            time.monotonic() + max(0, deadline - time.monotonic()) / len(remaining),
        )
        before, before_discovery = obs.calls, obs.discovery_calls
        if rejected:
            batch = [
                obs._evidence(
                    query, cluster, period, {}, "unavailable", {"reason": rejected}
                )
            ]
        else:
            narrowed = (
                pod_namespace_scope(collected)
                if namespace_only and query == "D06"
                else None
            )
            batch = await obs.collect(query, period, namespace_scope=narrowed)
        used = obs.calls - before
        calls += used
        discovery_calls += obs.discovery_calls - before_discovery
        for e in batch:
            if e["quality"].get("reason") == "budget_exhausted":
                e["quality"]["reason"] = (
                    "collection_task_deadline_exhausted"
                    if time.monotonic() >= obs.deadline
                    else "collection_task_budget_exhausted"
                )
        evidence.extend(batch)
        collected.setdefault(task["key"], []).extend(batch)
        requested = timestamp(period["end"]) - timestamp(period["start"])
        completed = covered_ranges(batch, {"ok", "empty"})
        summaries.append(
            dict(
                query_id=query,
                cluster_id=cluster,
                requested_range=period,
                planned_calls=task["planned_calls"],
                reserved_calls=allowance,
                query_calls=used,
                requested_seconds=requested,
                completed_seconds=completed,
                data_seconds=covered_ranges(batch, {"ok"}),
                empty_seconds=covered_ranges(batch, {"empty"}),
                incomplete_seconds=max(0, requested - completed),
                ranges=[
                    dict(
                        time_range=e["time_range"],
                        status=e["tool_status"],
                        reason=e["quality"].get("reason"),
                        evidence_id=e["id"],
                    )
                    for e in batch
                ],
            )
        )
    summary = dict(
        plan_status="rejected" if rejected else "accepted",
        plan_reason=rejected,
        limits=limits,
        query_calls=calls,
        query_limit=limits["max_queries"],
        discovery_calls=discovery_calls,
        planned_calls=sum(t["planned_calls"] for t in tasks),
        complete=not rejected and all(s["incomplete_seconds"] == 0 for s in summaries),
        tasks=summaries,
    )
    return collected, evidence, summary
