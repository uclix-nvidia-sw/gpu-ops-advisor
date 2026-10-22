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


async def read_prior_rca(conn, data, history):
    ids = [
        r["body"]["id"]
        for r in history["rows"]
        if r["body"]["id"] != data["incident_id"]
    ]
    if not ids:
        return
    records = await (
        await conn.execute(
            "SELECT DISTINCT ON (j.incident_id) j.incident_id,j.id AS job_id,c.id AS result_id,c.content_hash,c.body->>'result_status' AS result_status,c.body->>'narrative_status' AS narrative_status,c.body->'cause_candidates' AS cause_candidates "
            "FROM jobs j JOIN result_candidates c ON c.id=j.published_result_id JOIN job_attempts a ON a.job_id=j.id AND a.attempt_no=j.attempt_no "
            "WHERE j.kind='rca' AND j.status='succeeded' AND dsx_scope_contains(%s,j.scope) AND j.incident_id=ANY(%s::uuid[]) AND a.ended_at<=%s "
            "ORDER BY j.incident_id,a.ended_at DESC,j.id LIMIT 500",
            (Jsonb(data["scope"]), ids, history["period"]["end"]),
        )
    ).fetchall()
    by_id = {
        str(r["incident_id"]): dict(
            r,
            job_id=str(r["job_id"]),
            result_id=str(r["result_id"]),
            incident_id=str(r["incident_id"]),
        )
        for r in records
    }
    for row in history["rows"]:
        prior = by_id.get(str(row["body"]["id"]))
        if prior:
            prior["cause_candidates"] = [
                {"claim": c.get("claim", ""), "causal_status": c.get("causal_status")}
                for c in (prior["cause_candidates"] or [])[:5]
            ]
            row["prior_rca"] = prior


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
                await read_prior_rca(conn, claim["input"], context["host_incidents"])
        return context
