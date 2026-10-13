"""Ops-owned artifact cleanup follows committed report deletion tombstones only."""

import asyncio
import contextlib
import threading
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest

from agent_common.artifacts import save_artifacts
from ops_agent import cleanup as module
from ops_agent import main


def test_removal_is_idempotent_and_blocks_late_writers(tmp_path):
    job = str(uuid4())
    folder = tmp_path / job
    folder.mkdir()
    (folder / "report.csv").write_text("private report", encoding="utf-8")
    late = (folder / "late.tmp").open("wb")
    try:
        module.remove_artifacts(tmp_path, job)
        late.write(b"late result")
    finally:
        late.close()
    assert folder.is_file() and folder.stat().st_size == 0
    module.remove_artifacts(tmp_path, job)
    with pytest.raises(FileExistsError):
        save_artifacts({"job_id": job}, str(tmp_path))
    with pytest.raises(NotADirectoryError):
        (folder / "late.csv").write_text("late result", encoding="utf-8")


def test_missing_job_directory_gets_a_barrier(tmp_path):
    job = str(uuid4())
    module.remove_artifacts(tmp_path, job)
    assert (tmp_path / job).is_file()
    with pytest.raises(FileNotFoundError):
        module.remove_artifacts(tmp_path / "unmounted-volume", job)


@pytest.mark.parametrize(
    "job", ["../outside", "not-a-uuid", "{00000000-0000-0000-0000-000000000000}"]
)
def test_cleanup_rejects_noncanonical_paths(tmp_path, job):
    with pytest.raises(ValueError):
        module.remove_artifacts(tmp_path, job)
    assert not list(tmp_path.iterdir())


def test_cleanup_never_follows_symlinks_or_replaces_unknown_files(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep", encoding="utf-8")
    job = str(uuid4())
    folder = root / job
    folder.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        module.remove_artifacts(root, job)
    folder.unlink()
    folder.write_text("unexpected file", encoding="utf-8")
    with pytest.raises(ValueError):
        module.remove_artifacts(root, job)
    folder.unlink()
    folder.mkdir()
    (folder / "link").symlink_to(outside, target_is_directory=True)
    module.remove_artifacts(root, job)
    assert (outside / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_writer_winning_directory_recreation_keeps_cleanup_retryable(
    tmp_path, monkeypatch
):
    job = str(uuid4())
    folder = tmp_path / job
    folder.mkdir()
    original = module.shutil.rmtree

    def racing_delete(path):
        original(path)
        path.mkdir()
        (path / "late.csv").write_text("late", encoding="utf-8")

    monkeypatch.setattr(module.shutil, "rmtree", racing_delete)
    with pytest.raises(FileExistsError):
        module.remove_artifacts(tmp_path, job)
    assert folder.is_dir()
    monkeypatch.setattr(module.shutil, "rmtree", original)
    module.remove_artifacts(tmp_path, job)
    assert folder.is_file() and folder.stat().st_size == 0


class Connection:
    def __init__(self, job):
        self.job, self.queries, self.events = job, [], []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    @contextlib.asynccontextmanager
    async def transaction(self):
        self.events.append("lock")
        try:
            yield
        finally:
            self.events.append("unlock")

    async def execute(self, query, parameters=None):
        self.queries.append((query, parameters))
        return self

    async def fetchone(self):
        return (self.job,) if self.job else None


@pytest.fixture
def connection(monkeypatch):
    conn = Connection(str(uuid4()))

    async def connect(*args, **kwargs):
        return conn

    monkeypatch.setattr(module.psycopg.AsyncConnection, "connect", connect)
    return conn


@pytest.mark.parametrize("failure", [False, True])
async def test_cleanup_acknowledges_only_after_filesystem_completion(
    tmp_path, connection, failure
):
    settings = SimpleNamespace(database_url="fixture-only", artifact_dir=str(tmp_path))
    if failure:
        (tmp_path / connection.job).write_text("unexpected file", encoding="utf-8")
    assert await module.cleanup_once(settings)
    select = next(q for q, p in connection.queries if q.startswith("SELECT"))
    assert "j.kind='report'" in select and "SKIP LOCKED" in select
    assert "j.status IN ('succeeded','failed','cancelled','expired')" in select
    update = next(p for q, p in connection.queries if q.startswith("UPDATE"))
    assert update == (
        "failed" if failure else "complete",
        "ValueError" if failure else None,
        connection.job,
    )
    if not failure:
        assert (tmp_path / connection.job).stat().st_size == 0
    assert connection.events == ["lock", "unlock"]


async def test_empty_cleanup_does_not_touch_files(tmp_path, connection):
    connection.job = None
    settings = SimpleNamespace(database_url="fixture-only", artifact_dir=str(tmp_path))
    assert await module.cleanup_once(settings) is False
    assert not any(q.startswith("UPDATE") for q, p in connection.queries)
    assert not list(tmp_path.iterdir())


async def test_cancellation_drains_file_work_before_releasing_row_lock(
    tmp_path, connection, monkeypatch
):
    started, finish = threading.Event(), threading.Event()
    remove = module.remove_artifacts

    def blocked_remove(*args):
        started.set()
        assert finish.wait(2)
        remove(*args)

    monkeypatch.setattr(module, "remove_artifacts", blocked_remove)
    settings = SimpleNamespace(database_url="fixture-only", artifact_dir=str(tmp_path))
    task = asyncio.create_task(module.cleanup_once(settings))
    try:
        assert await asyncio.to_thread(started.wait, 1)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done() and connection.events == ["lock"]
    finally:
        finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert connection.events == ["lock", "unlock"]
    assert not any(q.startswith("UPDATE") for q, p in connection.queries)
    assert (tmp_path / connection.job).is_file()


async def test_missing_migration_is_graceful_and_does_not_log_connection_details(
    monkeypatch, caplog
):
    async def missing(settings):
        raise psycopg.errors.UndefinedTable("credential-sensitive-fixture")

    monkeypatch.setattr(module, "cleanup_once", missing)
    await module.cleanup(SimpleNamespace(), once=True)
    assert "UndefinedTable" in caplog.text
    assert "credential-sensitive-fixture" not in caplog.text


async def test_once_mode_runs_one_cleanup_before_worker(monkeypatch):
    calls = []

    async def cleanup(settings, once=False):
        calls.append(("cleanup", once))

    async def worker(settings, once=False, *, store=None):
        assert isinstance(store, main.ReportStore)
        calls.append(("worker", once))

    monkeypatch.setattr(main, "cleanup", cleanup)
    monkeypatch.setattr(main, "serve_nat", worker)
    await main.serve(SimpleNamespace(database_url="fixture-only"), once=True)
    assert calls == [("cleanup", True), ("worker", True)]


async def test_worker_exit_cancels_cleanup_task(monkeypatch):
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def cleanup(settings):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    async def worker(settings, *, store=None):
        assert isinstance(store, main.ReportStore)
        await started.wait()
        raise RuntimeError("fixture worker exit")

    monkeypatch.setattr(main, "cleanup", cleanup)
    monkeypatch.setattr(main, "serve_nat", worker)
    with pytest.raises(RuntimeError, match="fixture worker exit"):
        await main.serve(SimpleNamespace(database_url="fixture-only"))
    assert stopped.is_set()


async def test_failed_barrier_flush_is_retryable(tmp_path, connection, monkeypatch):
    settings = SimpleNamespace(database_url="fixture-only", artifact_dir=str(tmp_path))
    fsync = module.os.fsync

    def failure(fd):
        raise OSError("fixture flush failed")

    monkeypatch.setattr(module.os, "fsync", failure)
    assert await module.cleanup_once(settings)
    update = [p for q, p in connection.queries if q.startswith("UPDATE")][-1]
    assert update == ("failed", "OSError", connection.job)
    monkeypatch.setattr(module.os, "fsync", fsync)
    assert await module.cleanup_once(settings)
    update = [p for q, p in connection.queries if q.startswith("UPDATE")][-1]
    assert update == ("complete", None, connection.job)
