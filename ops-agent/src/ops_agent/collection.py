"""Report-only planning around the unchanged shared observation collector."""

import asyncio
from copy import deepcopy
import math
import time

from agent_common.contracts import timestamp
from agent_common.observation import Observation
from agent_common.parallel import run_bounded

from .namespace_usage import pod_namespace_scope


REPORT_LIMITS = {"max_queries", "chunk_seconds", "max_rows", "max_concurrency"}


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
        for q in dict.fromkeys(order)
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


def dependencies(tasks, profile, namespace_only):
    """Order response reuse and namespace narrowing before dispatch, not by timing."""
    for index, task in enumerate(tasks):
        definition = profile["queries"].get(task["query_id"], {})
        # Same metric requests run in order so the collector can reuse complete
        # responses. The exact scope/period/arguments cache still decides reuse.
        task["depends_on"] = [
            previous["sub_agent_id"]
            for previous in tasks[:index]
            if previous["cluster"] == task["cluster"]
            and previous["period"] == task["period"]
            and definition.get("source") == "mimir"
            and profile["queries"].get(previous["query_id"], {}).get("metric")
            == definition.get("metric")
        ]
        if namespace_only and task["query_id"] == "D06":
            task["depends_on"] += [
                previous["sub_agent_id"]
                for previous in tasks
                if previous["cluster"] == task["cluster"]
                and previous["period"] == task["period"]
                and previous["query_id"] in ("D01", "D08")
            ]


async def collect_report(tools, profile, data, deadline, order, namespace_only):
    profile = report_profile(profile)
    limits = profile["limits"]
    concurrency = limits.get("max_concurrency", 3)
    if type(concurrency) is not int or concurrency < 1:
        raise ValueError("positive observation concurrency required")
    tasks, rejected = collection_plan(profile, data, order)
    for index, task in enumerate(tasks):
        task["sub_agent_id"] = f"report-observation-{index}"
        task["plan_order"] = index
    dependencies(tasks, profile, namespace_only)
    collected, evidence, summaries = {}, [], []
    calls = discovery_calls = 0
    finished = {}
    pending = list(tasks)
    collection_start = time.monotonic()

    async def observe(task):
        query, cluster, period = task["query_id"], task["cluster"], task["period"]
        child_profile = deepcopy(profile)
        child_profile["limits"].update(
            max_queries=task["reserved_calls"],
            max_discovery_calls=task["reserved_discovery_calls"],
        )
        obs = Observation(
            tools,
            child_profile,
            {**deepcopy(data), "scope": {"clusters": [deepcopy(cluster)]}},
            deadline,
            reuse_queries=True,
        )
        # Copy only completed caches. Running tasks never share mutable collectors.
        for previous in finished.values():
            if previous.data["scope"]["clusters"] == [cluster]:
                obs.responses.update(previous.responses)
                obs.discovery.cache.update(
                    {
                        key: value
                        for key, value in previous.discovery.cache.items()
                        if not isinstance(value, Exception)
                    }
                )
        started = time.monotonic()
        obs.deadline = min(deadline, started + task["time_budget_seconds"])
        try:
            if rejected:
                obs._evidence(
                    query,
                    cluster["cluster_id"],
                    period,
                    {},
                    "unavailable",
                    {"reason": rejected},
                )
            else:
                narrowed = (
                    pod_namespace_scope(collected)
                    if namespace_only and query == "D06"
                    else None
                )
                async with asyncio.timeout(max(0, obs.deadline - time.monotonic())):
                    await obs.collect(query, period, namespace_scope=narrowed)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            obs._evidence(
                query,
                cluster["cluster_id"],
                period,
                {},
                "unavailable",
                {
                    "reason": "collection_task_deadline_exhausted"
                    if isinstance(exc, TimeoutError)
                    else "sub_agent_failed",
                    "error_type": type(exc).__name__,
                },
            )
        elapsed = time.monotonic() - started
        for e in obs.evidence:
            e["quality"].update(
                sub_agent_id=task["sub_agent_id"], plan_order=task["plan_order"]
            )
            if e["quality"].get("reason") == "budget_exhausted":
                e["quality"]["reason"] = (
                    "collection_task_deadline_exhausted"
                    if time.monotonic() >= obs.deadline
                    else "collection_task_budget_exhausted"
                )
        batch = [e for e in obs.evidence if e["query_id"] == query]
        requested = timestamp(period["end"]) - timestamp(period["start"])
        completed = covered_ranges(batch, {"ok", "empty"})
        summary = dict(
            query_id=query,
            cluster_id=cluster["cluster_id"],
            requested_range=period,
            sub_agent_id=task["sub_agent_id"],
            depends_on=task["depends_on"],
            planned_calls=task["planned_calls"],
            reserved_calls=task["reserved_calls"],
            reserved_discovery_calls=task["reserved_discovery_calls"],
            discovery_calls=obs.discovery_calls,
            query_calls=obs.calls,
            started_offset_seconds=started - collection_start,
            elapsed_seconds=elapsed,
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
        return task, obs, batch, summary

    while pending:
        ready = [t for t in pending if all(key in finished for key in t["depends_on"])][
            :concurrency
        ]
        if not ready:
            raise ValueError("cyclic report observation plan")
        spare = max(
            0, limits["max_queries"] - calls - sum(t["planned_calls"] for t in pending)
        )
        discovery_left = max(0, limits.get("max_discovery_calls", 64) - discovery_calls)
        # ponytail: batch barriers can delay ready work behind a slow sibling;
        # use a completion-driven queue only if measured throughput needs it.
        # Reserve the full pending plan before siblings start. Only reaped batches
        # release unused reservations; later tasks keep their initial query budget.
        for index, task in enumerate(ready):
            task["reserved_calls"] = (
                0
                if rejected
                else task["planned_calls"]
                + spare // len(pending)
                + (index < spare % len(pending))
            )
            task["reserved_discovery_calls"] = discovery_left // len(pending) + (
                index < discovery_left % len(pending)
            )
            task["time_budget_seconds"] = max(
                0, deadline - time.monotonic()
            ) / math.ceil(len(pending) / concurrency)
        outcomes = await run_bounded(ready, observe, concurrency)
        for task, obs, batch, summary in outcomes:
            calls += obs.calls
            discovery_calls += obs.discovery_calls
            collected.setdefault(task["key"], []).extend(batch)
            evidence.extend(obs.evidence)
            summaries.append(summary)
            finished[task["sub_agent_id"]] = obs
            pending.remove(task)
    positions = {t["sub_agent_id"]: i for i, t in enumerate(tasks)}
    summaries.sort(key=lambda s: positions[s["sub_agent_id"]])
    evidence.sort(
        key=lambda e: (
            e["query_id"],
            e["cluster_id"] or "",
            e["time_range"]["start"],
            e["time_range"]["end"],
        )
    )
    summary = dict(
        plan_status="rejected" if rejected else "accepted",
        plan_reason=rejected,
        limits=limits,
        concurrency=concurrency,
        elapsed_seconds=time.monotonic() - collection_start,
        query_calls=calls,
        query_limit=limits["max_queries"],
        discovery_calls=discovery_calls,
        planned_calls=sum(t["planned_calls"] for t in tasks),
        complete=not rejected and all(s["incomplete_seconds"] == 0 for s in summaries),
        tasks=summaries,
    )
    return collected, evidence, summary
