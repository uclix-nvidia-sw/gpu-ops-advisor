import argparse
import asyncio
import logging
import sys
from agent_common.settings import Settings
from agent_common.worker import serve_nat


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    logging.basicConfig(level=logging.INFO)
    settings = Settings("rca")
    settings.nat_config_file = (
        settings.nat_config_file or "rcca-agent/configs/workflow.yml"
    )
    asyncio.run(serve_nat(settings, args.once))


if __name__ == "__main__":
    main()
