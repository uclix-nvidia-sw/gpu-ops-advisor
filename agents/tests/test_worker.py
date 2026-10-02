import asyncio
from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

import httpx
import pytest

from agent_common.settings import Settings
from agent_common.worker import Worker
from agent_common.runtime import attempt_context
from agent_common.contracts import base_result


def claim():
    deadline = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
    return dict(
        job_id=str(uuid4()),
        kind="report",
        attempt_no=1,
        claim_token="fixture",
        input={
            "scope": {"clusters": [{"cluster_id": "cpc-2", "namespaces": ["dev"]}]},
            "time_range": {
                "start": "2026-09-15T00:00:00Z",
                "end": "2026-09-15T01:00:00Z",
            },
            "topic_ids": ["O09"],
            "group_by": ["cluster"],
            "timezone": "UTC",
        },
        deadline_at=deadline,
        lease_expires_at=deadline,
        heartbeat_seconds=0.01,
        versions={},
        budget={"attempt_limit": 10000},
    )


class MemoryStore:
    def __init__(self, fail=False):
        self.saved = 0
        self.fail = fail

    async def read_context(self, c):
        return {"data_cutoff_at": c["deadline_at"]}

    async def save(self, *args):
        self.saved += 1
        if self.fail:
            raise OSError("fixture disk full")
        return str(uuid4()), "hash"


@pytest.mark.asyncio
async def test_cancel_heartbeats_continue_and_remote_uncertainty(tmp_path):
    calls = []
    c = claim()

    def handler(request):
        body = json.loads(request.content)
        calls.append((request.url.path, body))
        return httpx.Response(
            200,
            json={
                "lease_expires_at": c["lease_expires_at"],
                "cancel_requested": len(calls) >= 3,
            },
        )

    async def run(c):
        attempt_context.get()["llm"].state("running")
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            attempt_context.get()["llm"].state("unknown")
            raise

    store = MemoryStore()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await Worker(
            Settings("report", artifact_dir=str(tmp_path)), run, store, http
        ).execute(c)
    assert store.saved == 0
    assert len([x for x in calls if x[0].endswith("/heartbeat")]) >= 3
    assert calls[-1][0].endswith("/fail")
    assert calls[-1][1]["remote_call_state"] == "unknown"
    assert calls[-1][1]["code"] == "cancelled"


@pytest.mark.asyncio
async def test_storage_failure_never_completes(tmp_path):
    calls = []
    c = claim()

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(
            200,
            json={"lease_expires_at": c["lease_expires_at"], "cancel_requested": False},
        )

    async def run(c):
        return base_result(c, c["deadline_at"]), []

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await Worker(
            Settings("report", artifact_dir=str(tmp_path)), run, MemoryStore(True), http
        ).execute(c)
    assert calls[-1].endswith("/fail")
    assert not any(path.endswith("/complete") for path in calls)


@pytest.mark.parametrize("cancel_mode", ["cancel", "lease_lost"])
async def test_cancellation_during_save_rolls_back_without_completion(
    tmp_path, cancel_mode
):
    entered, stopped = asyncio.Event(), asyncio.Event()
    calls = []
    c = claim()

    class SlowStore(MemoryStore):
        async def save(self, *args):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

    def handler(request):
        calls.append(request.url.path)
        if (
            request.url.path.endswith("/heartbeat")
            and entered.is_set()
            and cancel_mode == "lease_lost"
        ):
            return httpx.Response(409, json={"code": "stale_attempt"})
        return httpx.Response(
            200,
            json={
                "lease_expires_at": c["lease_expires_at"],
                "cancel_requested": entered.is_set(),
            },
        )

    async def run(c):
        return base_result(c, c["deadline_at"]), []

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await asyncio.wait_for(
            Worker(
                Settings("report", artifact_dir=str(tmp_path)), run, SlowStore(), http
            ).execute(c),
            2,
        )
    assert stopped.is_set()
    assert not any(path.endswith("/complete") for path in calls)
