import asyncio
from builtins import ExceptionGroup
from contextlib import asynccontextmanager

import httpx
import pytest

from agent_common.settings import Settings
from agent_common.worker import serve_nat, transient_connection_error


@pytest.mark.asyncio
async def test_startup_retries_nested_mcp_connection_error_before_serving(monkeypatch):
    import nat.runtime.loader
    import agent_common.worker as worker

    attempts, delays, served = [], [], []

    @asynccontextmanager
    async def load(*args, **kwargs):
        attempts.append(1)
        if len(attempts) <= 2:
            raise ExceptionGroup(
                "TaskGroup",
                [ExceptionGroup("transport", [httpx.ConnectError("offline")])],
            )
        yield object()

    async def sleep(delay):
        delays.append(delay)

    async def serve(self, once):
        served.append(once)

    monkeypatch.setattr(nat.runtime.loader, "load_workflow", load)
    monkeypatch.setattr(worker.asyncio, "sleep", sleep)
    monkeypatch.setattr(worker.Worker, "serve", serve)
    await serve_nat(Settings("report"), once=True)
    assert len(attempts) == 3
    assert delays == [2, 4]
    assert served == [True]


@pytest.mark.asyncio
async def test_permanent_startup_error_is_not_hidden_by_retries(monkeypatch):
    import nat.runtime.loader

    @asynccontextmanager
    async def load(*args, **kwargs):
        raise ValueError("invalid workflow configuration")
        yield  # pragma: no cover

    monkeypatch.setattr(nat.runtime.loader, "load_workflow", load)
    with pytest.raises(ValueError, match="invalid workflow"):
        await serve_nat(Settings("rca"))


@pytest.mark.asyncio
async def test_worker_failure_after_initialization_is_not_replayed(monkeypatch):
    import nat.runtime.loader
    import agent_common.worker as worker

    @asynccontextmanager
    async def load(*args, **kwargs):
        yield object()

    async def serve(self, once):
        raise httpx.ConnectError("worker network error after initialization")

    monkeypatch.setattr(nat.runtime.loader, "load_workflow", load)
    monkeypatch.setattr(worker.Worker, "serve", serve)
    with pytest.raises(httpx.ConnectError):
        await serve_nat(Settings("rca"))


def test_only_transient_connection_errors_are_retryable():
    assert transient_connection_error(httpx.ConnectTimeout("timeout"))
    assert not transient_connection_error(ValueError("invalid"))
    assert not transient_connection_error(asyncio.CancelledError())
    assert not transient_connection_error(
        ExceptionGroup("mixed", [httpx.ConnectError("offline"), ValueError("invalid")])
    )
    request = httpx.Request("POST", "http://mcp/mcp")
    for status in (401, 403, 404):
        assert not transient_connection_error(
            httpx.HTTPStatusError(
                "error", request=request, response=httpx.Response(status)
            )
        )
