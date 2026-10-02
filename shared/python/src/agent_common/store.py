import asyncio
import json
import logging
import time
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .contracts import content_hash, validate_result

log = logging.getLogger(__name__)


def encoded_json(value):
    # Encode in the preparation thread, not psycopg's event-loop adapter.
    return Jsonb(json.dumps(value).encode(), dumps=lambda data: data)


def prepare_result(result, evidence):
    validate_result(result, evidence)
    return encoded_json(result), content_hash(result)


def prepare_evidence(e):
    return (
        encoded_json(e["scope"]),
        encoded_json(e["input"]),
        encoded_json(e["quality"]),
        encoded_json(e["snapshot"]),
        content_hash(e["snapshot"]),
    )


async def check_attempt(conn, claim):
    # Wall clock, not transaction-start now(): a save may outlive a lease.
    row = await (
        await conn.execute(
            "SELECT 1 FROM job_attempts a JOIN jobs j ON j.id=a.job_id WHERE a.job_id=%s AND a.attempt_no=%s AND a.claim_token=%s AND a.ended_at IS NULL AND a.lease_expires_at>clock_timestamp() AND j.deadline_at>clock_timestamp() AND j.cancel_requested_at IS NULL AND j.status='running' AND j.attempt_no=a.attempt_no",
            (claim["job_id"], claim["attempt_no"], claim["claim_token"]),
        )
    ).fetchone()
    if not row:
        raise ValueError("stale attempt")


class Store:
    def __init__(self, url):
        self.url = url

    async def read_context(self, claim):
        data = claim["input"]
        async with await psycopg.AsyncConnection.connect(
            self.url, row_factory=dict_row
        ) as conn:
            async with conn.transaction():
                await conn.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                )
                cutoff = (await (await conn.execute("SELECT now() AS t")).fetchone())[
                    "t"
                ].isoformat()
                context = dict(
                    data_cutoff_at=cutoff,
                    incidents=[],
                    rca_results=[],
                    actions=[],
                    runbooks=[],
                )
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
                if claim["kind"] == "rca":
                    row = await (
                        await conn.execute(
                            "SELECT snapshot,content_hash FROM incident_evidence_versions WHERE incident_id=%s AND revision=%s",
                            (data["incident_id"], data["evidence_version"]),
                        )
                    ).fetchone()
                    if (
                        not row
                        or row["snapshot"] != data["incident_snapshot"]
                        or content_hash(row["snapshot"]) != row["content_hash"]
                    ):
                        raise ValueError("immutable incident snapshot mismatch")
                    rows = await (
                        await conn.execute(
                            "SELECT id,knowledge_id,knowledge_key,revision,content,compatibility,content_hash,reviewed_content_hash FROM knowledge_revisions WHERE kind='runbook' AND state IN ('published','retired') AND (visibility='common' OR dsx_scope_contains(scope,%s)) ORDER BY revision DESC",
                            (Jsonb(data["scope"]),),
                        )
                    ).fetchall()
                    pinned = {
                        (k["knowledge_id"], k["revision"], k["content_hash"])
                        for k in claim["versions"].get("knowledge", [])
                    }
                    context["runbooks"] = [
                        {
                            **r,
                            "id": str(r["id"]),
                            "knowledge_id": str(r["knowledge_id"]),
                        }
                        for r in rows
                        if (str(r["knowledge_id"]), r["revision"], r["content_hash"])
                        in pinned
                    ]
                if claim["kind"] in {"report", "rca"}:
                    # Exact supplied scope, absolute period, one repeatable-read snapshot.
                    rows = await (
                        await conn.execute(
                            "SELECT to_jsonb(i) AS body FROM incidents i WHERE dsx_scope_contains(%s,i.scope) AND i.occurred_at >= %s AND i.occurred_at < %s",
                            (
                                Jsonb(data["scope"]),
                                data["time_range"]["start"],
                                data["time_range"]["end"],
                            ),
                        )
                    ).fetchall()
                    context["incidents"] = [r["body"] for r in rows]
                    rows = await (
                        await conn.execute(
                            "SELECT c.id,c.content_hash,c.body FROM jobs j JOIN result_candidates c ON c.id=j.published_result_id WHERE j.kind='rca' AND j.status='succeeded' AND dsx_scope_contains(%s,j.scope) AND j.incident_id=ANY(%s::uuid[])",
                            (
                                Jsonb(data["scope"]),
                                [r["id"] for r in context["incidents"]],
                            ),
                        )
                    ).fetchall()
                    context["rca_results"] = [
                        dict(
                            result_id=str(r["id"]),
                            content_hash=r["content_hash"],
                            body=r["body"],
                        )
                        for r in rows
                    ]
                    rows = await (
                        await conn.execute(
                            "SELECT id,occurred_at,body FROM review_records WHERE kind='action' AND dsx_scope_contains(%s,scope) AND occurred_at IS NOT NULL AND (%s::uuid[] IS NULL OR id=ANY(%s::uuid[])) AND occurred_at<=%s",
                            (
                                Jsonb(data["scope"]),
                                data.get("action_record_ids"),
                                data.get("action_record_ids"),
                                data["time_range"]["end"],
                            ),
                        )
                    ).fetchall()
                    context["actions"] = [
                        dict(
                            id=str(r["id"]),
                            occurred_at=r["occurred_at"].isoformat(),
                            body=r["body"],
                        )
                        for r in rows
                    ]
                return context

    async def save(self, claim, result, evidence):
        started = time.monotonic()
        candidate_id = str(uuid4())
        body, digest = await asyncio.to_thread(prepare_result, result, evidence)
        prepare_seconds = time.monotonic() - started
        async with await psycopg.AsyncConnection.connect(self.url) as conn:
            async with conn.transaction():
                await check_attempt(conn, claim)
                for e in evidence:
                    before = time.monotonic()
                    (
                        scope,
                        inputs,
                        quality,
                        snapshot,
                        checksum,
                    ) = await asyncio.to_thread(prepare_evidence, e)
                    prepare_seconds += time.monotonic() - before
                    await conn.execute(
                        "INSERT INTO evidence(id,job_id,attempt_no,cluster_id,scope,query_id,query_version,input,tool_status,time_start,time_end,data_cutoff_at,quality,snapshot,checksum) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (
                            e["id"],
                            claim["job_id"],
                            claim["attempt_no"],
                            e.get("cluster_id"),
                            scope,
                            e["query_id"],
                            e["query_version"],
                            inputs,
                            e["tool_status"],
                            e["time_range"]["start"],
                            e["time_range"]["end"],
                            result["data_cutoff_at"],
                            quality,
                            snapshot,
                            checksum,
                        ),
                    )
                await conn.execute(
                    "INSERT INTO result_candidates(id,job_id,attempt_no,kind,schema_version,body,content_hash,validation_status) VALUES(%s,%s,%s,%s,%s,%s,%s,'valid')",
                    (
                        candidate_id,
                        claim["job_id"],
                        claim["attempt_no"],
                        claim["kind"],
                        claim["versions"]
                        .get("execution", {})
                        .get("result_schema", "1.3"),
                        body,
                        digest,
                    ),
                )
                # Keep the fence only for final validation/commit. JC non-key updates
                # remain compatible with the FK key-share locks held during inserts.
                await conn.execute(
                    "SELECT 1 FROM jobs WHERE id=%s FOR SHARE", (claim["job_id"],)
                )
                await conn.execute(
                    "SELECT 1 FROM job_attempts WHERE job_id=%s AND attempt_no=%s FOR SHARE",
                    (claim["job_id"], claim["attempt_no"]),
                )
                await check_attempt(conn, claim)
        elapsed = time.monotonic() - started
        log.info(
            "candidate saved job=%s evidence=%d prepare_seconds=%.3f db_seconds=%.3f",
            claim["job_id"],
            len(evidence),
            prepare_seconds,
            elapsed - prepare_seconds,
        )
        return candidate_id, digest
