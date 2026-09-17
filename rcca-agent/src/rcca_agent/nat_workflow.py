from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig
from agent_common.runtime import nat_tools
from .workflow import run


class RCAConfig(FunctionBaseConfig, name="rcca_workflow"):
    pass


@register_function(config_type=RCAConfig)
async def workflow(config: RCAConfig, builder: Builder):
    tools = await nat_tools(builder)

    async def execute(claim: dict) -> dict:
        return await run(tools)

    yield FunctionInfo.from_fn(
        execute, description="Incident RCA registered investigation workflow"
    )
