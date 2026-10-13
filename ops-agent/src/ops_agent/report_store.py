"""Compact read-only incident snapshot for Ops; RCA Store remains unchanged."""

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from agent_common.store import Store
from agent_common.settings import Settings

from .report_contract import (
    VERSION,
    MAX_INCIDENTS,
    aggregate_report,
    previous_period,
    validate,
)


class ReportSettings(Settings):
    def profile_for_claim(self, claim):
        if aggregate_report(claim["input"]):
            validate(claim["input"])
            if claim["versions"].get("criteria") != VERSION:
                raise ValueError("aggregate_report_version_mismatch")
            return {"limits": {"deadline_seconds": 900}}
        return self.profile()


class ReportStore(Store):
    async def read_context(self, claim):
        data = claim["input"]
        if not aggregate_report(data):
            return await super().read_context(claim)
        validate(data)
        async with await psycopg.AsyncConnection.connect(
            self.url, row_factory=dict_row
        ) as conn:
            async with conn.transaction():
                await conn.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                )
                await conn.execute("SET LOCAL statement_timeout = '15s'")
                cutoff = (await (await conn.execute("SELECT now() AS t")).fetchone())[
                    "t"
                ].isoformat()
                context = {
                    "data_cutoff_at": cutoff,
                    "incidents": [],
                    "previous_incidents": [],
                    "incident_limit_exceeded": False,
                }
                model = claim["versions"].get("model")
                if model is not None:
                    row = await (
                        await conn.execute(
                            "SELECT snapshot FROM profile_revisions WHERE profile_id::text=%s AND revision=%s",
                            (model["model_id"], model["model_revision"]),
                        )
                    ).fetchone()
                    if not row or row["snapshot"].get("kind") != "model":
                        raise ValueError("pinned model revision is unavailable")
                    context["model_profile"] = row["snapshot"]
                if "incident_summary" not in data["topic_ids"]:
                    return context
                for key, period in (
                    ("incidents", data["time_range"]),
                    ("previous_incidents", previous_period(data)),
                ):
                    rows = await (
                        await conn.execute(
                            """SELECT i.id::text, i.cluster_id, i.occurred_at, left(i.symptom,512) AS symptom, md5(i.symptom) AS symptom_key,
                        jsonb_build_object('gpu_uuid',i.target->'gpu_uuid') AS target, i.alarm_status, i.alarm_resolved_at,
                        r.id::text AS result_id, r.content_hash
                        FROM incidents i LEFT JOIN LATERAL (
                          SELECT c.id,c.content_hash FROM jobs j JOIN result_candidates c ON c.id=j.published_result_id
                          WHERE j.kind='rca' AND j.status='succeeded' AND j.incident_id=i.id
                          AND dsx_scope_contains(%s,j.scope)
                          ORDER BY j.created_at DESC,j.id DESC LIMIT 1
                        ) r ON true
                        WHERE dsx_scope_contains(%s,i.scope) AND i.occurred_at >= %s AND i.occurred_at < %s
                        ORDER BY i.occurred_at,i.id LIMIT %s""",
                            (
                                Jsonb(data["scope"]),
                                Jsonb(data["scope"]),
                                period["start"],
                                period["end"],
                                MAX_INCIDENTS + 1,
                            ),
                        )
                    ).fetchall()
                    if len(rows) > MAX_INCIDENTS:
                        context["incident_limit_exceeded"] = True
                        # Never publish a truncated count as the period total.
                        continue
                    context[key] = [
                        {
                            **row,
                            "occurred_at": row["occurred_at"].isoformat(),
                            "alarm_resolved_at": row["alarm_resolved_at"].isoformat()
                            if row["alarm_resolved_at"]
                            else None,
                        }
                        for row in rows
                    ]
                return context
