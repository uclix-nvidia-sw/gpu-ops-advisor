import asyncio
from builtins import BaseExceptionGroup
from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

import httpx
import pytest

from agent_common.settings import Settings
from agent_common.worker import Worker
from agent_common.runtime import attempt_context
from agent_common.contracts import base_result


def claim(kind="report"):
    deadline = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
    value = dict(
        job_id=str(uuid4()),
        kind=kind,
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
    if kind == "rca":
        data = value["input"]
        for key in ("topic_ids", "group_by", "timezone"):
            data.pop(key)
        data.update(
            incident_id=str(uuid4()),
            evidence_version=1,
            analysis_profile_revision="fixture",
            incident_time=data["time_range"]["start"],
        )
        data["incident_snapshot"] = {"input": dict(data), "evidence": {}}
    return value


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


@pytest.mark.parametrize("kind", ["rca", "report"])
@pytest.mark.parametrize(
    "remote_state", ["not_started", "running", "unknown", "terminated"]
)
async def test_mixed_exception_group_fails_attempt_and_next_claim_completes(
    tmp_path, kind, remote_state, caplog
):
    failed, succeeding = claim(kind), claim(kind)
    claims = iter((failed, succeeding))
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append((request.url.path, body))
        if request.url.path.endswith("/claims"):
            return httpx.Response(200, json=next(claims))
        return httpx.Response(
            200, json={"lease_expires_at": failed["lease_expires_at"]}
        )

    async def run(c):
        if c["job_id"] == failed["job_id"]:
            attempt_context.get()["llm"].state(remote_state)
            raise BaseExceptionGroup(
                "sensitive upstream message",
                [
                    RuntimeError("sensitive cause"),
                    BaseExceptionGroup("cleanup", [asyncio.CancelledError()]),
                ],
            )
        return base_result(c, c["deadline_at"]), []

    store = MemoryStore()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        worker = Worker(Settings(kind, artifact_dir=str(tmp_path)), run, store, http)
        assert await worker.once()
        assert await worker.once()
    failures = [(path, body) for path, body in calls if path.endswith("/fail")]
    assert failures == [
        (
            f"/internal/v1/jobs/{failed['job_id']}/fail",
            {
                "attempt_no": 1,
                "claim_token": "fixture",
                "code": "internal_error",
                "retryable": False,
                "remote_call_state": remote_state,
            },
        )
    ]
    assert [path for path, _ in calls if path.endswith("/complete")] == [
        f"/internal/v1/jobs/{succeeding['job_id']}/complete"
    ]
    assert store.saved == 1
    assert "sensitive" not in caplog.text


@pytest.mark.parametrize("kind", ["rca", "report"])
@pytest.mark.parametrize("external_cancel", [False, True])
async def test_cancellation_cleanup_group_still_reports_final_remote_state(
    tmp_path, kind, external_cancel
):
    entered = asyncio.Event()
    c = claim(kind)
    calls = []

    def handler(request):
        calls.append((request.url.path, json.loads(request.content)))
        return httpx.Response(
            200,
            json={
                "lease_expires_at": c["lease_expires_at"],
                "cancel_requested": entered.is_set() and not external_cancel,
            },
        )

    async def run(c):
        attempt_context.get()["llm"].state("running")
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            attempt_context.get()["llm"].state("unknown")
            raise BaseExceptionGroup(
                "cleanup", [RuntimeError(), asyncio.CancelledError()]
            )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        task = asyncio.create_task(
            Worker(
                Settings(kind, artifact_dir=str(tmp_path)), run, MemoryStore(), http
            ).execute(c)
        )
        await asyncio.wait_for(entered.wait(), 2)
        if external_cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
        else:
            await asyncio.wait_for(task, 2)
    assert calls[-1][0].endswith("/fail")
    assert calls[-1][1]["code"] == "cancelled"
    assert calls[-1][1]["remote_call_state"] == "unknown"
    assert not any(path.endswith("/complete") for path, _ in calls)


@pytest.mark.parametrize(
    "signal,during_cleanup",
    [
        (KeyboardInterrupt, False),
        (SystemExit, False),
        (asyncio.CancelledError, False),
        (KeyboardInterrupt, True),
        (SystemExit, True),
    ],
)
async def test_control_signal_group_is_reported_but_not_swallowed(
    tmp_path, signal, during_cleanup
):
    c = claim()
    calls = []
    entered = asyncio.Event()

    def handler(request):
        calls.append((request.url.path, json.loads(request.content)))
        return httpx.Response(
            200,
            json={
                "lease_expires_at": c["lease_expires_at"],
                "cancel_requested": entered.is_set() and during_cleanup,
            },
        )

    async def run(c):
        if during_cleanup:
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                raise BaseExceptionGroup("control", [signal()])
        raise BaseExceptionGroup("control", [signal()])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(BaseExceptionGroup) as caught:
            await Worker(
                Settings("report", artifact_dir=str(tmp_path)), run, MemoryStore(), http
            ).execute(c)
    assert isinstance(caught.value.exceptions[0], signal)
    assert calls[-1][0].endswith("/fail")
    assert calls[-1][1]["remote_call_state"] == "not_started"
    assert not any(path.endswith("/complete") for path, _ in calls)
