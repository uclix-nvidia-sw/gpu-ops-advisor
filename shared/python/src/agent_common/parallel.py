"""Bounded in-process tasks; cancellation never leaves sibling work running."""

import asyncio


async def run_bounded(items, run, concurrency):
    if type(concurrency) is not int or concurrency < 1:
        raise ValueError("positive observation concurrency required")
    semaphore = asyncio.Semaphore(concurrency)

    async def invoke(item):
        async with semaphore:
            return await run(item)

    tasks = [asyncio.create_task(invoke(item)) for item in items]
    try:
        return await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
