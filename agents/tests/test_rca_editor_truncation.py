import asyncio
import json
import time

import httpx
import pytest

from agent_common.llm import LLM, RemoteUncertain
from agent_common.settings import Settings
from rcca_agent.report_editor import prioritize


def editorial():
    return {
        "facts": [
            {
                "id": f"limits-{i}",
                "section": "limits",
                "text": "미확정 " * 200,
                "value_refs": [],
                "evidence_refs": ["e1"],
            }
            for i in range(20)
        ],
        "limitations": [],
        "narrative_status": "omitted",
    }


@pytest.mark.asyncio
async def test_completed_truncation_gets_bounded_retry_with_original_statements():
    calls = []

    def handle(request):
        payload = json.loads(request.content)
        calls.append(json.loads(payload["messages"][1]["content"]))
        truncated = len(calls) <= 2
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length" if truncated else "stop",
                        "message": {"content": json.dumps({"fact_ids": ["limits-1"]})},
                    }
                ],
                "usage": {
                    "total_tokens": 100,
                    "completion_tokens": 50,
                    "prompt_tokens": 50,
                },
            },
        )

    settings = Settings(
        kind="rca",
        llm_base_url="https://fixture.invalid/v1",
        llm_model="fixture",
        llm_api_key="fixture",
        llm_synthesis_max_tokens=128,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        llm = LLM(settings, time.monotonic() + 30, 20000, lambda _: None, http)
        output = editorial()
        diagnostics = await prioritize(output, llm)
    assert len(calls) == 3  # shared transport's bounded retry, then compact RCA retry
    assert len(calls[0]["facts"]) == 6
    assert len(calls[0]["facts"][0]["text"]) == 384
    assert len(calls[2]["facts"][0]["text"]) == 96
    assert diagnostics["truncation_retry"] == "response_received"
    assert output["narrative"][0] == output["facts"][1]
    assert len(output["facts"]) == 20


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "budget,seconds,reason",
    [(0, 30, "token_budget_exhausted"), (20000, -1, "deadline_exhausted")],
)
async def test_compact_retry_reports_exact_gate(budget, seconds, reason):
    class Model:
        configured = True
        last_failure = "llm_output_truncated"
        remaining = budget
        deadline = time.monotonic() + seconds
        settings = Settings(kind="rca")
        calls = 0

        async def complete(self, *args):
            self.calls += 1
            return None

    model = Model()
    output = editorial()
    diagnostics = await prioritize(output, model)
    assert model.calls == 1
    assert diagnostics["truncation_retry"] == reason
    assert output["narrative_status"] == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RemoteUncertain, asyncio.CancelledError])
async def test_uncertain_execution_never_retried(error):
    class Model:
        configured = True
        calls = 0

        async def complete(self, *args):
            self.calls += 1
            raise error()

    model = Model()
    with pytest.raises(error):
        await prioritize(editorial(), model)
    assert model.calls == 1
