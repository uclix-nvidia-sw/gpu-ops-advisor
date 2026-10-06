from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig
from agent_common.runtime import nat_tools
import agent_common.grafana_mcp  # noqa: F401 - register the shared NAT MCP group
from .workflow import run


class ReportConfig(FunctionBaseConfig, name="ops_workflow"):
    pass


@register_function(config_type=ReportConfig)
async def workflow(config: ReportConfig, builder: Builder):
    tools = await nat_tools(builder)

    async def execute(claim: dict) -> dict:
        return await run(tools)

    yield FunctionInfo.from_fn(
        execute,
        description="Sequential collection, deterministic calculations and evidence-based report",
    )
