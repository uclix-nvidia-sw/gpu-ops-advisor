import asyncio
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
from threading import Thread
import time

import httpx
import pytest

from agent_common.contracts import base_result
from agent_common.grafana_mcp import GrafanaMCPClient, GrafanaMCPConfig
from agent_common.settings import Settings
from agent_common.worker import Worker
from test_incident_snapshot import rca_input
from test_worker import MemoryStore, claim


@pytest.fixture
def mcp_http():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            method = request["method"]
            calls.append(request)
            if "id" not in request:
                self.send_response(202)
                self.end_headers()
                return
            if method == "initialize":
                result = {
                    "protocolVersion": request["params"]["protocolVersion"],
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fixture", "version": "1"},
                }
            elif method == "tools/list":
                result = {
                    "tools": [
                        {
                            "name": "query_prometheus",
                            "description": "Read fixture observations",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"mode": {"type": "string"}},
                            },
                        }
                    ]
                }
            elif method == "tools/call":
                mode = request["params"]["arguments"].get("mode", "normal")
                if mode == "session_expired":
                    self.send_response(404)
                    self.end_headers()
                    return
                if mode == "disconnect":
                    time.sleep(0.1)
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                if mode == "slow":
                    time.sleep(5.2)
                if mode == "deadline":
                    time.sleep(0.5)
                result = {
                    "content": [{"type": "text", "text": '{"data":{"result":[]}}'}]
                }
                if mode == "tool_error":
                    result = {
                        "content": [{"type": "text", "text": "query failed"}],
                        "isError": True,
                    }
            else:
                raise AssertionError(method)
            payload = json.dumps(
                {"jsonrpc": "2.0", "id": request["id"], "result": result}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/mcp", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.asyncio
async def test_response_after_httpx_default_five_seconds_succeeds(mcp_http):
    url, calls = mcp_http
    async with GrafanaMCPClient(url) as client:
        tools = await client.get_tools()
        value = await tools["query_prometheus"].acall({"mode": "slow"})
        assert json.loads(value) == {"data": {"result": []}}
    assert len([x for x in calls if x["method"] == "tools/call"]) == 1
    assert client._connection_task.done()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["report", "rca"])
async def test_disconnect_does_not_cancel_worker_and_next_job_reconnects(
    mcp_http, tmp_path, kind
):
    url, requests = mcp_http
    c = claim()
    c["kind"] = kind
    if kind == "rca":
        c["input"] = rca_input({"alert": {"labels": {}}})
    calls = []
    mode = "disconnect"

    def handler(request):
        calls.append((request.url.path, json.loads(request.content)))
        return httpx.Response(
            200,
            json={"lease_expires_at": c["lease_expires_at"], "cancel_requested": False},
        )

    async with GrafanaMCPClient(url) as client:

        async def run(c):
            await client.call_tool("query_prometheus", {"mode": mode})
            return base_result(c, c["deadline_at"]), []

        store = MemoryStore()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            worker = Worker(
                Settings(kind, artifact_dir=str(tmp_path)), run, store, http
            )
            await asyncio.wait_for(worker.execute(c), timeout=5)
            assert calls[-1][0].endswith("/fail")
            assert calls[-1][1]["remote_call_state"] == "not_started"
            assert calls[-1][1]["code"] != "cancelled"
            assert any(path.endswith("/heartbeat") for path, _ in calls)
            assert store.saved == 0
            mode = "normal"
            c["attempt_no"] = 2
            await asyncio.wait_for(worker.execute(c), timeout=5)
            assert calls[-1][0].endswith("/complete")
            assert store.saved == 1
    assert [
        x["params"]["arguments"]["mode"]
        for x in requests
        if x["method"] == "tools/call"
    ] == ["disconnect", "normal"]
    assert len([x for x in requests if x["method"] == "initialize"]) == 2
    assert client._connection_task.done()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_tool_deadline_and_external_cancellation_remain_bounded(mcp_http, cancel):
    url, calls = mcp_http
    timeout = timedelta(seconds=30 if cancel else 0.1)
    async with GrafanaMCPClient(url) as client:
        # Exercise the call deadline without making initialization timing-dependent.
        client._tool_call_timeout = timeout
        task = asyncio.create_task(
            client.call_tool("query_prometheus", {"mode": "deadline"})
        )
        if cancel:
            await asyncio.sleep(0.1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=2)
        else:
            with pytest.raises(Exception, match="[Tt]imeout|[Tt]imed out"):
                await asyncio.wait_for(task, timeout=2)
        assert not client._connection_task.done()
        result = await client.call_tool("query_prometheus", {"mode": "normal"})
        assert not result.isError
    assert len([x for x in calls if x["method"] == "tools/call"]) == 2
    assert client._connection_task.done()


@pytest.mark.parametrize(
    "field,value",
    [
        ("tool_call_timeout", 0),
        ("reconnect_enabled", True),
        ("include", ["update_dashboard"]),
    ],
)
def test_transport_configuration_preserves_read_only_bounded_calls(field, value):
    with pytest.raises(ValueError):
        GrafanaMCPConfig.model_validate(
            {
                "server": {
                    "transport": "streamable-http",
                    "url": "http://localhost:8000/mcp",
                },
                field: value,
            }
        )


@pytest.mark.asyncio
async def test_cancelling_one_caller_preserves_sibling_and_connection(mcp_http):
    url, calls = mcp_http
    before = asyncio.all_tasks()
    async with GrafanaMCPClient(url) as client:
        cancelled = asyncio.create_task(
            client.call_tool("query_prometheus", {"mode": "deadline"})
        )
        sibling = asyncio.create_task(
            client.call_tool("query_prometheus", {"mode": "deadline"})
        )
        try:
            async with asyncio.timeout(2):
                while len([x for x in calls if x["method"] == "tools/call"]) < 2:
                    await asyncio.sleep(0.01)
            cancelled.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(cancelled, timeout=2)
            assert not (await asyncio.wait_for(sibling, timeout=2)).isError
            assert not client._connection_task.done()
            result = await client.call_tool("query_prometheus", {"mode": "normal"})
            assert not result.isError
        finally:
            for task in (cancelled, sibling):
                if not task.done():
                    task.cancel()
            await asyncio.gather(cancelled, sibling, return_exceptions=True)
    assert len([x for x in calls if x["method"] == "tools/call"]) == 3
    assert len([x for x in calls if x["method"] == "initialize"]) == 1
    assert client._connection_task.done()
    assert not asyncio.all_tasks() - before


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["session_expired", "tool_error"])
async def test_expired_session_reconnects_without_replaying_tool_errors(mcp_http, mode):
    url, calls = mcp_http
    async with GrafanaMCPClient(url) as client:
        connection = client._connection_task
        if mode == "session_expired":
            with pytest.raises(Exception, match="Session terminated"):
                await asyncio.wait_for(
                    client.call_tool("query_prometheus", {"mode": mode}), timeout=2
                )
            assert connection.done()
        else:
            result = await client.call_tool("query_prometheus", {"mode": mode})
            assert result.isError
            assert not connection.done()
        result = await client.call_tool("query_prometheus", {"mode": "normal"})
        assert not result.isError
    assert [
        x["params"]["arguments"]["mode"] for x in calls if x["method"] == "tools/call"
    ] == [mode, "normal"]
    assert len([x for x in calls if x["method"] == "initialize"]) == (
        2 if mode == "session_expired" else 1
    )
    assert client._connection_task.done()
