"""Actual JC deletion + isolated PostgreSQL cleanup locking and retry.

Uses the same local process fixture and RUN_AGENT_E2E requirements as test_e2e.
"""

import asyncio
import threading
from types import SimpleNamespace
from uuid import uuid4

import httpx
import psycopg
import pytest

from ops_agent import cleanup as module
import test_e2e
from test_e2e import PERIOD, SCOPE, submit

stack = test_e2e.stack


@pytest.mark.e2e
async def test_report_cleanup_retry_and_concurrent_claim(stack, tmp_path, monkeypatch):
    job = submit(
        stack,
        "report",
        dict(
            scope=SCOPE,
            time_range=PERIOD,
            topic_ids=["O09"],
            group_by=["cluster"],
            timezone="UTC",
        ),
    )
    for operation in ("cancel", "delete"):
        current = httpx.get(stack["jc"] + "/jobs/" + job, timeout=10).json()
        response = httpx.post(
            stack["jc"] + "/jobs/" + job + "/" + operation,
            json=dict(
                contract_version="1.3",
                source_module="backend",
                input={"reason": "isolated cleanup fixture"},
            ),
            headers={
                "If-Match": str(current["version"]),
                "Idempotency-Key": str(uuid4()),
            },
            timeout=10,
        )
        assert response.status_code == 200, response.text
    settings = SimpleNamespace(database_url=stack["url"], artifact_dir=str(tmp_path))
    folder = tmp_path / job
    folder.write_text("unexpected path must not be removed", encoding="utf-8")
    assert await module.cleanup_once(settings)
    with psycopg.connect(stack["url"]) as conn:
        state, error, attempted = conn.execute(
            "SELECT artifact_cleanup_state,artifact_cleanup_error,artifact_cleanup_at "
            "FROM report_deletions WHERE job_id=%s",
            (job,),
        ).fetchone()
    assert (state, error) == ("failed", "ValueError") and attempted is not None
    assert folder.read_text(encoding="utf-8") == "unexpected path must not be removed"

    folder.unlink()
    folder.mkdir()
    (folder / "report.csv").write_text("fixture", encoding="utf-8")
    unrelated = tmp_path / str(uuid4())
    unrelated.mkdir()
    (unrelated / "keep.csv").write_text("keep", encoding="utf-8")
    started, release = threading.Event(), threading.Event()
    remove, calls = module.remove_artifacts, []

    def blocked_remove(directory, job_id):
        calls.append(job_id)
        started.set()
        assert release.wait(10), "test did not release cleanup thread"
        remove(directory, job_id)

    monkeypatch.setattr(module, "remove_artifacts", blocked_remove)
    first = asyncio.create_task(module.cleanup_once(settings))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        assert not await asyncio.wait_for(module.cleanup_once(settings), timeout=5)
    finally:
        release.set()
        assert await first
    assert calls == [job]
    assert folder.is_file() and folder.stat().st_size == 0
    assert (unrelated / "keep.csv").read_text(encoding="utf-8") == "keep"
    with psycopg.connect(stack["url"]) as conn:
        state, error, completed = conn.execute(
            "SELECT artifact_cleanup_state,artifact_cleanup_error,artifact_cleanup_at "
            "FROM report_deletions WHERE job_id=%s",
            (job,),
        ).fetchone()
    assert (state, error) == ("complete", None) and completed >= attempted
    assert not await module.cleanup_once(settings)
