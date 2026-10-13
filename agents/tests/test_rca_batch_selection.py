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


@pytest.mark.asyncio
async def test_missing_tool_call_repairs_to_registered_batch():
    class Model:
        configured = True
        last_failure = None
        calls = 0

        async def complete(self, prompt, payload, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return None
            assert "tools" not in kwargs
            return {"query_ids": ["D44", "D02"]}

    model = Model()
    diagnostics = {}
    assert await choose_followup(
        model, ["D44", "D02"], ["unknown_value"], diagnostics
    ) == ["D44", "D02"]
    assert diagnostics == {
        "status": "selected",
        "attempts": 2,
        "selected_queries": ["D44", "D02"],
        "initial_failure": "missing_tool_calls",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    ["llm_deadline_exhausted", "llm_token_budget_exhausted", "llm_http_error"],
)
async def test_selection_transport_failure_is_not_explicit_stop(failure):
    class Model:
        configured = True
        last_failure = failure
        calls = 0

        async def complete(self, *args, **kwargs):
            self.calls += 1
            return None

    model = Model()
    diagnostics = {}
    assert await choose_followup(model, ["D44"], ["unknown_value"], diagnostics) == []
    assert model.calls == 1
    assert diagnostics["status"] == "model_unavailable"
    assert diagnostics["initial_failure"] == failure


@pytest.mark.asyncio
async def test_explicit_stop_does_not_retry_or_force_remaining_queries():
    class Model:
        configured = True
        calls = 0

        async def complete(self, *args, **kwargs):
            self.calls += 1
            return [
                {"function": {"name": "investigate", "arguments": '{"query_ids": []}'}}
            ]

    model = Model()
    diagnostics = {}
    assert (
        await choose_followup(model, ["D44", "D02"], ["unknown_value"], diagnostics)
        == []
    )
    assert model.calls == 1
    assert diagnostics["status"] == "explicit_stop"
