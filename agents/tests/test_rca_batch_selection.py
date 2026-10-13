import json

import pytest

from rcca_agent.workflow import choose_followup


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ids, expected",
    [
        (["D02", "D44", "D11"], ["D02", "D44", "D11"]),
        (["D02", "D02"], ["D02"]),
        (["D02", "D44", "D11", "D33"], []),
        (["D02", "D99"], []),
        (["stop"], []),
    ],
)
async def test_bounded_registered_batch(ids, expected):
    class Model:
        configured = True

        async def complete(self, *args, **kwargs):
            return [
                {
                    "function": {
                        "name": "investigate",
                        "arguments": json.dumps({"query_id": q}),
                    }
                }
                for q in ids
            ]

    assert (
        await choose_followup(
            Model(), ["D02", "D44", "D11", "D33"], ["missing_evidence"]
        )
        == expected
    )
