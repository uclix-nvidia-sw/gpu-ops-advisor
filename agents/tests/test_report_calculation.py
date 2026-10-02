"""CPU-bound report calculations must not starve the Worker lease or outlive it."""

import asyncio
import copy
from datetime import datetime, timedelta, timezone
import json
import threading
import time

import httpx
import psycopg
import pytest

from agent_common.contracts import content_hash
from agent_common.settings import Settings
from agent_common.worker import Worker
from ops_agent import workflow
import test_e2e
from test_report_observation import DATA, collected
from test_worker import MemoryStore, claim

stack = test_e2e.stack


@pytest.mark.parametrize(
    "mode, criteria",
    [("success", "1.1"), ("success", "1.2")]
    + [
        (mode, "1.2")
        for mode in ("cancel", "cancel_error", "lease_lost", "deadline", "error")
    ],
)
async def test_calculation_keeps_lease_and_drains_before_attempt_ends(
    tmp_path, monkeypatch, mode, criteria
):
    c = claim()
    c["input"].update(
        copy.deepcopy(DATA), topic_ids=list(workflow.PLAN), group_by=["namespace"]
    )
    c["versions"]["criteria"] = criteria
    if mode == "deadline":
        c["deadline_at"] = (
            datetime.now(timezone.utc) + timedelta(seconds=0.3)
        ).isoformat()
    source = collected()
    context = dict(
        data_cutoff_at=c["deadline_at"], incidents=[], rca_results=[], actions=[]
    )
    entered, finished = threading.Event(), threading.Event()
    calculated, requests, written, saved = [], [], [], []
    heartbeats_during_calculation = 0
    lease_seconds = 0.5
    lease_expires = time.monotonic() + lease_seconds
    real_calculate = workflow.calculate
    run_task = None

    async def collect(*args):
        return source, [e for es in source.values() for e in es], {"complete": True}

    def calculate(topic_id, *args, **kwargs):
        calculated.append(topic_id)
        if len(calculated) == 1:
            entered.set()
            try:
                # Busy Python, not sleep: reproduce event-loop starvation and GIL contention.
                stop = time.monotonic() + (1.2 if mode == "success" else 0.8)
                while time.monotonic() < stop:
                    sum(range(100))
                if mode in {"error", "cancel_error"}:
                    raise RuntimeError("fixture calculation failure")
            finally:
                finished.set()
        return real_calculate(topic_id, *args, **kwargs)

    async def write_report(result, llm):
        written.append(result)

    class Store(MemoryStore):
        async def read_context(self, claim):
            return context.copy()

        async def save(self, claim, result, evidence):
            saved.append((result, evidence))
            return await super().save(claim, result, evidence)

    def handler(request):
        nonlocal lease_expires, heartbeats_during_calculation
        requests.append((request.url.path, json.loads(request.content)))
        if request.url.path.endswith("/heartbeat"):
            if time.monotonic() >= lease_expires or (
                entered.is_set() and mode == "lease_lost"
            ):
                return httpx.Response(409, json={"code": "stale_attempt"})
            if entered.is_set() and not finished.is_set():
                heartbeats_during_calculation += 1
                if mode in {"cancel", "cancel_error"}:
                    # A second cancellation during the drain must not detach the CPU task.
                    asyncio.get_running_loop().call_later(0.05, run_task.cancel)
            lease_expires = time.monotonic() + lease_seconds
        return httpx.Response(
            200,
            json={
                "lease_expires_at": (
                    datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
                ).isoformat(),
                "cancel_requested": entered.is_set()
                and mode in {"cancel", "cancel_error"},
            },
        )

    async def run(claim):
        nonlocal run_task
        run_task = asyncio.current_task()
        output = await workflow.run({})
        return output["result"], output["evidence"]

    monkeypatch.setattr(workflow, "collect_report", collect)
    monkeypatch.setattr(workflow, "calculate", calculate)
    monkeypatch.setattr(workflow, "write_report", write_report)
    store = Store()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await asyncio.wait_for(
            Worker(
                Settings("report", artifact_dir=str(tmp_path)), run, store, http
            ).execute(c),
            5,
        )
    assert entered.is_set() and finished.is_set()
    if mode == "success":
        assert heartbeats_during_calculation >= 2
        assert calculated == c["input"]["topic_ids"]
        assert len(written) == store.saved == len(saved) == 1
        result, evidence = saved[0]
        assert result["topics"] == [
            real_calculate(
                topic,
                c["input"],
                source,
                context,
                evidence[0],
                criteria_version=criteria,
            )
            for topic in c["input"]["topic_ids"]
        ]
        assert requests[-1][0].endswith("/complete")
    else:
        assert calculated == ["O01"]
        assert not written and not saved and store.saved == 0
        assert not any(path.endswith("/complete") for path, _ in requests)
        assert requests[-1][0].endswith("/fail")
        assert requests[-1][1]["code"] == {
            "deadline": "timeout",
            "error": "internal_error",
        }.get(mode, "cancelled")
        assert requests[-1][1]["remote_call_state"] == "not_started"


@pytest.mark.e2e
async def test_slow_calculation_publishes_with_real_jc_and_store(
    stack, tmp_path, monkeypatch
):
    data = dict(
        scope=test_e2e.SCOPE,
        time_range=test_e2e.PERIOD,
        timezone="UTC",
        topic_ids=list(workflow.PLAN),
        group_by=["cluster"],
    )
    jid = await asyncio.to_thread(test_e2e.submit, stack, "report", data)
    entered, finished = threading.Event(), threading.Event()
    heartbeats = []
    real_calculate = workflow.calculate

    async def collect(*args):
        return {}, [], {"complete": True}

    def calculate(topic_id, *args, **kwargs):
        if topic_id == "O01":
            entered.set()
            try:
                stop = time.monotonic() + 2.6
                while time.monotonic() < stop:
                    sum(range(100))
            finally:
                finished.set()
        return real_calculate(topic_id, *args, **kwargs)

    async def response_hook(response):
        if (
            response.request.url.path.endswith("/heartbeat")
            and entered.is_set()
            and not finished.is_set()
        ):
            heartbeats.append(response.status_code)

    async def run(claim):
        output = await workflow.run({})
        return output["result"], output["evidence"]

    monkeypatch.setattr(workflow, "collect_report", collect)
    monkeypatch.setattr(workflow, "calculate", calculate)
    settings = Settings(
        "report",
        jc_url=stack["jc"],
        database_url=stack["url"],
        artifact_dir=str(tmp_path),
        config_path=stack["env"]["AGENT_CONFIG_FILE"],
        llm_base_url="",
        llm_model="",
        llm_api_key="",
    )
    try:
        async with httpx.AsyncClient(event_hooks={"response": [response_hook]}) as http:
            worker = Worker(settings, run, http=http)
            await worker.post(
                "/workers/register",
                {**worker.identity, "capacity_profile_id": "report-v1"},
            )
            c = await worker.post("/claims", worker.identity)
            assert c["job_id"] == jid
            c["heartbeat_seconds"] = 0.1
            # The fixture job only: real JC must renew this lease during 2.6s CPU work.
            async with await psycopg.AsyncConnection.connect(stack["url"]) as conn:
                await conn.execute(
                    "UPDATE jobs SET versions=jsonb_set(versions,'{execution,lease_seconds}','2') WHERE id=%s",
                    (jid,),
                )
                await conn.execute(
                    "UPDATE job_attempts SET lease_expires_at=clock_timestamp()+interval '2 seconds' WHERE job_id=%s",
                    (jid,),
                )
            await asyncio.wait_for(worker.execute(c), 15)
        assert finished.is_set() and len(heartbeats) >= 3
        assert set(heartbeats) == {200}
        async with await psycopg.AsyncConnection.connect(stack["url"]) as conn:
            status, body, digest = await (
                await conn.execute(
                    "SELECT j.status,r.body,r.content_hash FROM jobs j LEFT JOIN result_candidates r ON r.id=j.published_result_id WHERE j.id=%s",
                    (jid,),
                )
            ).fetchone()
            assert status == "succeeded"
            assert content_hash(body) == digest
            assert [t["topic_id"] for t in body["topics"]] == data["topic_ids"]
            assert body["quality"]["report"]["status"] == "complete"
    finally:
        # Release only this disposable job if an assertion fails; never affect later fixtures.
        async with await psycopg.AsyncConnection.connect(stack["url"]) as conn:
            await conn.execute(
                "UPDATE slot_reservations SET state='released' WHERE job_id=%s", (jid,)
            )
            await conn.execute(
                "UPDATE jobs SET status='failed' WHERE id=%s AND status<>'succeeded'",
                (jid,),
            )
