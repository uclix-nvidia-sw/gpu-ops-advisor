import argparse
import asyncio
import contextlib
import logging
import sys
from agent_common.settings import Settings
from agent_common.worker import serve_nat
from .cleanup import cleanup


async def serve(settings, once=False):
    if once:
        await cleanup(settings, once=True)
        return await serve_nat(settings, once=True)
    task = asyncio.create_task(cleanup(settings))
    try:
        await serve_nat(settings)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    logging.basicConfig(level=logging.INFO)
    settings = Settings("report")
    settings.nat_config_file = (
        settings.nat_config_file or "ops-agent/configs/workflow.yml"
    )
    asyncio.run(serve(settings, args.once))


if __name__ == "__main__":
    main()
