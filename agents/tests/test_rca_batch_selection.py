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
            assert not kwargs.get("tools")
            return {"query_ids": ids}

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
async def test_json_response_selects_complete_auxiliary_batch(ids, expected):
    class Model:
        configured = True

        async def complete(self, prompt, payload, **kwargs):
            assert not kwargs.get("tools")
            assert "query_ids" in prompt
            return {"query_ids": ids}

    assert (
        await choose_followup(Model(), ["D44", "D02", "D11"], ["unknown_value"])
        == expected
    )


@pytest.mark.asyncio
async def test_missing_json_selection_repairs_to_registered_batch():
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
        "initial_failure": "missing_selection",
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
            return {"query_ids": []}

    model = Model()
    diagnostics = {}
    assert (
        await choose_followup(model, ["D44", "D02"], ["unknown_value"], diagnostics)
        == []
    )
    assert model.calls == 1
    assert diagnostics["status"] == "explicit_stop"


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected_attempts", [(200, 1), (401, 1), (500, 3)])
async def test_json_selection_through_real_llm_transport(status, expected_attempts):
    import json
    import time
    import httpx
    from agent_common.llm import LLM
    from agent_common.settings import Settings

    requests = []

    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        # Reproduce an endpoint that rejects forced tool calling.
        if payload.get("tools"):
            return httpx.Response(500, json={"error": "tool protocol unsupported"})
        return httpx.Response(
            status,
            json={
                "choices": [
                    {
                        "message": {"content": '{"query_ids":["D44","D02"]}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"total_tokens": 30},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        llm = LLM(
            Settings(
                "rca",
                llm_base_url="http://fixture/v1",
                llm_model="fixture",
                llm_api_key="fixture",
            ),
            time.monotonic() + 30,
            20000,
            lambda _: None,
            client,
        )
        diagnostics = {}
        selected = await choose_followup(
            llm, ["D44", "D02"], ["unknown_value"], diagnostics
        )
    assert len(requests) == expected_attempts
    assert all("tools" not in r and "tool_choice" not in r for r in requests)
    assert selected == (["D44", "D02"] if status == 200 else [])
    assert diagnostics["status"] == (
        "selected" if status == 200 else "model_unavailable"
    )


@pytest.mark.asyncio
async def test_repair_http_failure_is_not_malformed_response():
    class Model:
        configured = True
        last_failure = None
        calls = 0

        async def complete(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {"query_ids": ["D99"]}
            self.last_failure = "llm_http_error"
            return None

    diagnostics = {}
    assert await choose_followup(Model(), ["D02"], [], diagnostics) == []
    assert diagnostics["repair_failure"] == "llm_http_error"
    assert diagnostics["status"] == "model_unavailable"
