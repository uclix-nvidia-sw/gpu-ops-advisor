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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ids,expected",
    [
        (["D44", "D02"], ["D44", "D02"]),
        (["D44", "D02", "D11"], ["D44", "D02", "D11"]),
        ([], []),
        (["D99"], []),
        (["D44"] * 4, []),
        ("D44", []),
    ],
)
async def test_single_tool_call_selects_complete_auxiliary_batch(ids, expected):
    class Model:
        configured = True

        async def complete(self, prompt, payload, **kwargs):
            schema = kwargs["tools"][0]["function"]["parameters"]
            assert schema["required"] == ["query_ids"]
            assert schema["properties"]["query_ids"]["maxItems"] == 3
            assert "final collection round" in prompt
            return [
                {
                    "function": {
                        "name": "investigate",
                        "arguments": json.dumps({"query_ids": ids}),
                    }
                }
            ]

    assert (
        await choose_followup(Model(), ["D44", "D02", "D11"], ["unknown_value"])
        == expected
    )
