"""Slow candidate storage with real PostgreSQL and JC; no production services."""

import asyncio
from datetime import datetime, timezone
import json
import threading
import time
from uuid import uuid4

import httpx
import psycopg
import pytest

from agent_common import store as storage
from agent_common.contracts import base_result, content_hash
import test_e2e
from test_e2e import PERIOD, SCOPE, submit

stack = test_e2e.stack


@pytest.mark.e2e
@pytest.mark.parametrize(
    "outcome",
    ["complete", "cancel", "expired", "replaced", "deadline", "late_heartbeat"],
)
async def test_save_keeps_lease_and_fences_invalid_attempts(
    stack, monkeypatch, outcome
):
    data = dict(
        scope=SCOPE,
        time_range=PERIOD,
        timezone="UTC",
        topic_ids=["O11"],
        group_by=["cluster"],
    )
    jid = await asyncio.to_thread(submit, stack, "report", data)
    identity = dict(
        worker_id="save-test-" + str(uuid4()), boot_id=str(uuid4()), kind="report"
    )
    async with httpx.AsyncClient(base_url=stack["jc"], timeout=2) as client:
        r = await client.post(
            "/workers/register", json={**identity, "capacity_profile_id": "report-v1"}
        )
        r.raise_for_status()
        r = await client.post("/claims", json=identity)
        r.raise_for_status()
        claim = r.json()
        assert claim["job_id"] == jid
        fence = {k: claim[k] for k in ("attempt_no", "claim_token")}
        # Short test lease, without changing production profiles. The blocked insert
        # lasts longer than this lease, so renewing only before save cannot pass.
        async with await psycopg.AsyncConnection.connect(stack["url"]) as conn:
            await conn.execute(
                "UPDATE jobs SET versions=jsonb_set(versions,'{execution,lease_seconds}','2') WHERE id=%s",
                (jid,),
            )
            await conn.execute(
                "UPDATE job_attempts SET lease_expires_at=clock_timestamp()+interval '2 seconds' WHERE job_id=%s",
                (jid,),
            )
        result = base_result(claim, datetime.now(timezone.utc).isoformat())
        snapshot = {
            "values": [[1760000000 + i, i / 10] for i in range(1000)],
            "text": "한글<&>",
        }
        evidence = [
            dict(
                id=str(uuid4()),
                cluster_id="cpc-2",
                scope=SCOPE,
                query_id="save-fixture",
                query_version="v1",
                input={},
                tool_status="ok",
                time_range=PERIOD,
                quality={},
                snapshot=snapshot,
            )
            for _ in range(217 if outcome == "complete" else 2)
        ]
        result["evidence_refs"] = [e["id"] for e in evidence]
        result["topics"] = [
            {
                "topic_id": "O11",
                "status": "blocked",
                "metrics": [],
                "missing_inputs": ["fixture_only"],
            }
        ]
        inserted, release = asyncio.Event(), asyncio.Event()
        execute = psycopg.AsyncConnection.execute
        thread_ids = []
        original_hash = storage.content_hash

        def tracked_hash(value):
            thread_ids.append(threading.get_ident())
            return original_hash(value)

        async def slow_insert(conn, query, *args, **kwargs):
            response = await execute(conn, query, *args, **kwargs)
            if str(query).startswith("INSERT INTO evidence") and not inserted.is_set():
                inserted.set()  # The FK row lock is held here until commit/rollback.
                await release.wait()
            return response

        monkeypatch.setattr(storage, "content_hash", tracked_hash)
        monkeypatch.setattr(psycopg.AsyncConnection, "execute", slow_insert)
        task = asyncio.create_task(
            storage.Store(stack["url"]).save(claim, result, evidence)
        )
        beat = None
        heartbeats = []

        async def heartbeat():
            while True:
                r = await client.post(
                    f"/jobs/{jid}/heartbeat",
                    json={
                        **fence,
                        "stage": "saving",
                        "remote_call_state": "terminated",
                    },
                )
                r.raise_for_status()
                heartbeats.append(time.monotonic())
                await asyncio.sleep(0.1)

        try:
            ready = asyncio.create_task(inserted.wait())
            try:
                await asyncio.wait(
                    [ready, task], timeout=5, return_when=asyncio.FIRST_COMPLETED
                )
                if task.done():
                    await task
                assert inserted.is_set(), "save did not reach evidence insert"
            finally:
                ready.cancel()
                await asyncio.gather(ready, return_exceptions=True)
            if outcome == "complete":
                beat = asyncio.create_task(heartbeat())
                await asyncio.sleep(2.6)
                assert not beat.done(), beat.exception() if beat.done() else None
                assert len(heartbeats) >= 3
                release.set()
                candidate, digest = await asyncio.wait_for(task, 10)
                beat.cancel()
                await asyncio.gather(beat, return_exceptions=True)
                assert thread_ids and threading.get_ident() not in thread_ids
                assert digest == content_hash(result)
                response = await client.post(
                    f"/jobs/{jid}/complete",
                    json={**fence, "candidate_id": candidate, "content_hash": digest},
                )
                assert response.status_code == 200, response.text
                # Same completion is idempotent, with one candidate and all evidence.
                repeated = await client.post(
                    f"/jobs/{jid}/complete",
                    json={**fence, "candidate_id": candidate, "content_hash": digest},
                )
                assert repeated.status_code == 200
                assert {
                    k: v for k, v in repeated.json().items() if k != "request_id"
                } == {k: v for k, v in response.json().items() if k != "request_id"}
                async with await psycopg.AsyncConnection.connect(stack["url"]) as conn:
                    row = await (
                        await conn.execute(
                            "SELECT status,published_result_id::text FROM jobs WHERE id=%s",
                            (jid,),
                        )
                    ).fetchone()
                    assert row == ("succeeded", candidate)
                    rows = await (
                        await conn.execute(
                            "SELECT snapshot,checksum FROM evidence WHERE job_id=%s",
                            (jid,),
                        )
                    ).fetchall()
                    assert len(rows) == 217
                    assert all(
                        body == snapshot and checksum == content_hash(snapshot)
                        for body, checksum in rows
                    )
            else:
                if outcome == "cancel":
                    current = (await client.get(f"/jobs/{jid}")).json()
                    response = await client.post(
                        f"/jobs/{jid}/cancel",
                        headers={
                            "Idempotency-Key": str(uuid4()),
                            "If-Match": str(current["version"]),
                        },
                        json={
                            "contract_version": "1.3",
                            "source_module": "backend",
                            "input": {"reason": "storage fixture"},
                        },
                    )
                    assert response.status_code == 200, response.text
                elif outcome == "late_heartbeat":
                    async with await psycopg.AsyncConnection.connect(
                        stack["url"]
                    ) as blocker:
                        await blocker.execute(
                            "SELECT 1 FROM jobs WHERE id=%s FOR SHARE", (jid,)
                        )
                        late = asyncio.create_task(
                            client.post(
                                f"/jobs/{jid}/heartbeat",
                                timeout=5,
                                json={
                                    **fence,
                                    "stage": "saving",
                                    "remote_call_state": "terminated",
                                },
                            )
                        )
                        try:
                            # Wait until the real JC is blocked on our row, then let
                            # the lease expire. An old pre-lock timestamp would renew it.
                            async with await psycopg.AsyncConnection.connect(
                                stack["url"], autocommit=True
                            ) as observer:
                                for _ in range(100):
                                    waiting = await (
                                        await observer.execute(
                                            "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE 'SELECT to_jsonb(j) FROM jobs j WHERE id=%'"
                                        )
                                    ).fetchone()
                                    if waiting[0]:
                                        break
                                    await asyncio.sleep(0.01)
                                assert waiting[0], (
                                    "heartbeat did not reach the row lock"
                                )
                            await asyncio.sleep(2.1)
                            await blocker.commit()
                            response = await late
                            assert response.status_code == 409, response.text
                        finally:
                            late.cancel()
                            await asyncio.gather(late, return_exceptions=True)
                else:
                    query = {
                        "expired": "UPDATE job_attempts SET lease_expires_at=clock_timestamp() WHERE job_id=%s",
                        "replaced": "UPDATE jobs SET attempt_no=attempt_no+1 WHERE id=%s",
                        "deadline": "UPDATE jobs SET deadline_at=clock_timestamp() WHERE id=%s",
                    }[outcome]
                    async with await psycopg.AsyncConnection.connect(
                        stack["url"]
                    ) as conn:
                        await conn.execute(query, (jid,))
                release.set()
                with pytest.raises(ValueError, match="stale attempt"):
                    await asyncio.wait_for(task, 5)
                async with await psycopg.AsyncConnection.connect(stack["url"]) as conn:
                    for table in ["evidence", "result_candidates"]:
                        row = await (
                            await conn.execute(
                                f"SELECT count(*) FROM {table} WHERE job_id=%s", (jid,)
                            )
                        ).fetchone()
                        assert row == (0,)
        finally:
            release.set()
            task.cancel()
            if beat:
                beat.cancel()
            await asyncio.gather(
                task, *([beat] if beat else []), return_exceptions=True
            )
            # Restore only this disposable test job; never leave a test quarantine
            # consuming the shared fixture's capacity for the next case.
            async with await psycopg.AsyncConnection.connect(stack["url"]) as conn:
                await conn.execute(
                    "UPDATE slot_reservations SET state='released' WHERE job_id=%s",
                    (jid,),
                )
                await conn.execute(
                    "UPDATE jobs SET status='failed' WHERE id=%s AND status<>'succeeded'",
                    (jid,),
                )


def test_preencoded_json_preserves_wire_values():
    value = {
        "text": "한글<&>\u2028",
        "values": [0, -0.0, 1e-7, 1e21, 9007199254740993, None, True],
    }
    prepared = storage.encoded_json(value)
    assert json.loads(prepared.dumps(prepared.obj)) == value
