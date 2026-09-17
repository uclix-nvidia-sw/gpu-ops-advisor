from contextvars import ContextVar

# Per-attempt context is not included in model input or remote MCP arguments.
attempt_context = ContextVar("attempt_context")


async def nat_tools(builder):
    tools = {}
    for name in ("query_prometheus", "query_loki_logs"):
        fn = await builder.get_function("grafana__" + name)
        tools[name] = fn.ainvoke
    return tools
