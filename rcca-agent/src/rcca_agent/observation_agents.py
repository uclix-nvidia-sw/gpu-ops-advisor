"""In-process observation sub-agents owned by one NAT workflow and JC lease."""

import asyncio
from copy import deepcopy
import json
import time

from agent_common.observation import Observation


async def collect_round(parent, query_ids, budget, *, round_no, concurrency=3):
    queries = list(dict.fromkeys(query_ids))
    if not queries:
        return {}
    if type(concurrency) is not int or concurrency < 1:
        raise ValueError("positive observation concurrency required")
    # Reserve before spawning. Unspent reservations become available only after
    # every sibling is reaped; issued calls (including failures) are never refunded.
    reserve = {
        key: (value + 1) // 2 if round_no == 0 else value
        for key, value in budget.items()
    }
    assignments = []
    for index, query in enumerate(queries):
        allocation = {
            key: value // len(queries) + (index < value % len(queries))
            for key, value in reserve.items()
        }
        assignments.append(
            dict(
                query_id=query,
                sub_agent_id=f"observation-{round_no}-{index}",
                budget=allocation,
            )
        )
    parent._evidence(
        "observation_plan",
        None,
        parent.data["time_range"],
        {
            "round": round_no,
            "assignments": assignments,
            "scope": parent.data["scope"],
            "target": parent.data.get("target", {}),
            "concurrency": concurrency,
        },
        "ok",
        {"reserved_before_dispatch": True},
    )
    semaphore = asyncio.Semaphore(concurrency)
    agents = []

    async def observe(assignment):
        profile = deepcopy(parent.profile)
        allocation = assignment["budget"]
        profile["limits"].update(
            max_queries=allocation["queries"],
            max_discovery_calls=allocation["discovery"],
        )
        child = Observation(
            parent.tools, profile, deepcopy(parent.data), parent.deadline
        )
        agents.append((assignment, child))
        query = assignment["query_id"]
        try:
            async with semaphore:
                if allocation["queries"] == 0:
                    child._evidence(
                        query,
                        None,
                        child.data["time_range"],
                        {},
                        "unavailable",
                        {"reason": "budget_exhausted"},
                    )
                elif query not in profile["queries"]:
                    child._evidence(
                        query,
                        None,
                        child.data["time_range"],
                        {},
                        "unavailable",
                        {"reason": "unsupported_source"},
                    )
                else:
                    timeout = min(
                        parent.deadline - time.monotonic(),
                        profile["limits"].get("query_timeout_seconds", 30)
                        * max(1, allocation["queries"] + allocation["discovery"]),
                    )
                    async with asyncio.timeout(max(0, timeout)):
                        await child.collect(query)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            child._evidence(
                query,
                None,
                child.data["time_range"],
                {},
                "unavailable",
                {
                    "reason": "sub_agent_timeout"
                    if isinstance(exc, TimeoutError)
                    else "sub_agent_failed",
                    "error_type": type(exc).__name__,
                },
            )

    try:
        async with asyncio.TaskGroup() as group:
            for assignment in assignments:
                group.create_task(observe(assignment), name=assignment["sub_agent_id"])
    finally:
        # TaskGroup awaits cancellation too. No observation survives its round.
        budget["queries"] -= sum(child.calls for _, child in agents)
        budget["discovery"] -= sum(child.discovery_calls for _, child in agents)
        merged = []
        for assignment, child in agents:
            for evidence in child.evidence:
                evidence["quality"].update(
                    round=round_no, sub_agent_id=assignment["sub_agent_id"]
                )
                merged.append(evidence)
        merged.sort(
            key=lambda e: (
                e["query_id"],
                e["cluster_id"] or "",
                e["time_range"]["start"],
                e["time_range"]["end"],
                json.dumps(e["input"], sort_keys=True),
            )
        )
        parent.evidence.extend(merged)
    return {query: [e for e in merged if e["query_id"] == query] for query in queries}
