"""Pinned NAT MCP integration with explicit HTTP limits and isolated connection lifetime."""

import asyncio
from builtins import BaseExceptionGroup
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Literal

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError
from nat.builder.function import FunctionGroup
from nat.cli.register_workflow import register_function_group
from nat.data_models.function import FunctionGroupBaseConfig
from nat.plugins.mcp.client.client_base import MCPStreamableHTTPClient
from nat.plugins.mcp.client.client_config import MCPServerConfig
from nat.plugins.mcp.exceptions import MCPError
from pydantic import BaseModel, Field, model_validator

READ_TOOLS = (
    "query_prometheus",
    "query_loki_logs",
    "list_datasources",
    "list_prometheus_label_values",
    "list_loki_label_values",
)


class GrafanaMCPConfig(FunctionGroupBaseConfig, name="grafana_mcp"):
    server: MCPServerConfig
    tool_call_timeout: timedelta = Field(default=timedelta(seconds=30), gt=timedelta(0))
    reconnect_enabled: Literal[False] = False

    @model_validator(mode="after")
    def validate_grafana_client(self):
        if self.server.transport != "streamable-http":
            raise ValueError("Grafana MCP requires streamable-http")
        if (set(self.include) | set(self.exclude)) - set(READ_TOOLS):
            raise ValueError("Only the existing Grafana read tools are supported")
        return self


class GrafanaMCPClient(MCPStreamableHTTPClient):
    def __init__(
        self,
        url,
        *,
        tool_call_timeout=timedelta(seconds=30),
        auth_provider=None,
        custom_headers=None,
    ):
        super().__init__(
            url,
            tool_call_timeout=tool_call_timeout,
            auth_flow_timeout=tool_call_timeout,
            auth_provider=auth_provider,
            custom_headers=custom_headers,
            reconnect_enabled=False,
        )
        self._connection_task = None
        self._connection_lock = asyncio.Lock()
        self._stop = None
        self._closed = False

    @asynccontextmanager
    async def connect_to_server(self):
        # NAT 1.5.0 otherwise supplies an HTTPX client with a five-second read timeout.
        timeout = self._tool_call_timeout.total_seconds() + 5
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers=self.custom_headers or None,
            auth=self._httpx_auth,
        ) as http:
            try:
                async with streamable_http_client(self.url, http_client=http) as (
                    read,
                    write,
                    session_id,
                ):
                    self._get_mcp_session_id = session_id
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        yield session
            finally:
                self._get_mcp_session_id = None

    async def _connection_lifetime(self, ready, stop):
        # SDK cancel scopes must be entered and exited by this same task.
        try:
            await super().__aenter__()
            ready.set()
            await stop.wait()
        finally:
            try:
                await super().__aexit__(None, None, None)
            finally:
                self._session = self._exit_stack = self._tools = None
                self._connection_established = False

    async def _wait_connection(self, connection, operation):
        call = asyncio.create_task(operation)
        try:
            done, _ = await asyncio.wait(
                (call, connection), return_when=asyncio.FIRST_COMPLETED
            )
            if connection in done:
                try:
                    connection.result()
                except asyncio.CancelledError as exc:
                    raise ConnectionError("Grafana MCP connection closed") from exc
                except BaseExceptionGroup as exc:
                    if isinstance(exc, Exception):
                        raise
                    raise ConnectionError("Grafana MCP connection failed") from exc
                raise ConnectionError("Grafana MCP connection closed")
            return await call
        except MCPError as exc:
            original = exc.original_exception
            if (
                isinstance(original, McpError)
                and original.error.code == 32600
                and original.error.message == "Session terminated"
            ):
                # The SDK turns HTTP 404 into this error but leaves the session open.
                if self._connection_task is connection:
                    self._stop.set()
                await asyncio.gather(connection, return_exceptions=True)
            raise
        finally:
            if not call.done():
                call.cancel()
            await asyncio.gather(call, return_exceptions=True)

    async def _ensure_connection(self):
        async with self._connection_lock:
            if self._closed:
                raise ConnectionError("Grafana MCP client is closed")
            if self._connection_task is None or self._connection_task.done():
                if self._connection_task and not self._connection_task.cancelled():
                    self._connection_task.exception()
                ready, self._stop = asyncio.Event(), asyncio.Event()
                self._connection_task = asyncio.create_task(
                    self._connection_lifetime(ready, self._stop),
                    name="grafana-mcp-connection",
                )
                try:
                    await asyncio.wait_for(
                        self._wait_connection(self._connection_task, ready.wait()),
                        timeout=self._tool_call_timeout.total_seconds(),
                    )
                except BaseException:
                    self._connection_task.cancel()
                    await asyncio.gather(self._connection_task, return_exceptions=True)
                    raise
            return self._connection_task

    async def __aenter__(self):
        self._closed = False
        await self._ensure_connection()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        self._closed = True
        if self._stop:
            self._stop.set()
        if self._connection_task:
            await asyncio.gather(self._connection_task, return_exceptions=True)

    async def get_tools(self):
        connection = await self._ensure_connection()
        return await self._wait_connection(connection, super().get_tools())

    async def call_tool(self, tool_name, tool_args=None):
        connection = await self._ensure_connection()
        # A failed call is never replayed. Only a later call can open a new connection.
        return await self._wait_connection(
            connection, super().call_tool(tool_name, tool_args)
        )


def _tool_function(tool):
    async def invoke(tool_input: BaseModel | None = None, **kwargs) -> str:
        value = tool_input or tool.input_schema.model_validate(
            {key: value for key, value in kwargs.items() if value is not None}
        )
        return await tool.acall(value.model_dump(mode="json", exclude_none=True))

    return invoke


@register_function_group(config_type=GrafanaMCPConfig)
async def grafana_mcp(config: GrafanaMCPConfig, builder):
    auth = (
        await builder.get_auth_provider(config.server.auth_provider)
        if config.server.auth_provider
        else None
    )
    async with GrafanaMCPClient(
        str(config.server.url),
        tool_call_timeout=config.tool_call_timeout,
        auth_provider=auth,
        custom_headers=config.server.custom_headers,
    ) as client:
        available = await client.get_tools()
        names = (set(config.include) or set(READ_TOOLS)) - set(config.exclude)
        if names - available.keys():
            raise ValueError("Configured Grafana read tools are unavailable")
        group = FunctionGroup(config=config)
        for name in sorted(names):
            tool = available[name]
            group.add_function(
                name,
                _tool_function(tool),
                input_schema=tool.input_schema,
                description=tool.description,
            )
        yield group
