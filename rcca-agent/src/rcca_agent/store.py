"""Read-only host history for RCA; never changes report/Ops context selection."""

from datetime import datetime, timedelta

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from agent_common.store import Store


async def read_host_history(conn, data, cutoff):
    target = data.get("target", {})
    machine = target.get("machine_id")
    node = target.get("node") or target.get("k8s_node_name")
    end = min(
        datetime.fromisoformat(data["time_range"]["end"].replace("Z", "+00:00")),
        datetime.fromisoformat(cutoff.replace("Z", "+00:00")),
    )
    start = end - timedelta(days=14)
    result = {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "rows": [],
        "complete": False,
    }
    if not machine and not node:
        return result
    # Prefer stable machine identity; never combine same-named replacement hosts.
    predicate = (
        "i.target->>'machine_id'=%s"
        if machine
        else "COALESCE(i.target->>'node',i.target->>'k8s_node_name')=%s"
    )
    records = await (
        await conn.execute(
            "SELECT to_jsonb(i) AS body, v.snapshot FROM incidents i LEFT JOIN incident_evidence_versions v ON v.incident_id=i.id AND v.revision=1 "
            "WHERE dsx_scope_contains(%s,i.scope) AND i.cluster_id=ANY(%s) AND "
            + predicate
            + " AND i.occurred_at >= %s AND i.occurred_at <= %s ORDER BY i.occurred_at DESC,i.id LIMIT 501",
            (
                Jsonb(data["scope"]),
                [c["cluster_id"] for c in data["scope"]["clusters"]],
                machine or node,
                start,
                end,
            ),
        )
    ).fetchall()
    result.update(rows=records[:500], complete=len(records) <= 500)
    return result


class RcaStore(Store):
    async def read_context(self, claim):
        context = await super().read_context(claim)
        if claim["kind"] != "rca":
            return context
        async with await psycopg.AsyncConnection.connect(
            self.url, row_factory=dict_row
        ) as conn:
            async with conn.transaction():
                await conn.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                )
                context["host_incidents"] = await read_host_history(
                    conn, claim["input"], context["data_cutoff_at"]
                )
        return context
