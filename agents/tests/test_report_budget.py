"""The shipped execution budget must permit synthesis of a multi-GPU report."""

import asyncio
import copy
import json
from pathlib import Path
import time

import httpx

from agent_common.llm import LLM, explain
from agent_common.settings import Settings
from ops_agent.prompts import EXPLANATION


def test_shipped_budget_reaches_llm_for_multi_gpu_report():
    root = Path(__file__).resolve().parents[2]
    profiles = json.loads(
        (root / "job-controller/config.example.json").read_text(encoding="utf-8")
    )["execution_profiles"]
    # Same shape as the production report: 19 facts, each citing eight snapshots.
    facts = [
        {
            "id": f"O01.vram.{i}.fact",
            "text": f"vram.{i}",
            "value_refs": [f"O01.vram.{i}"],
            "evidence_refs": [f"00000000-0000-4000-8000-{j:012d}" for j in range(8)],
        }
        for i in range(19)
    ]
    result = {"facts": [], "topics": [{"facts": facts}], "limitations": []}
    calls = []

    def handle(request):
        payload = json.loads(request.content)
        calls.append(payload)
        assert request.url.path == "/v1/chat/completions"
        assert payload["max_tokens"] == 16384
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps({"fact_ids": [facts[0]["id"]]})}}
                ],
                "usage": {
                    "prompt_tokens": 2000,
                    "completion_tokens": 30,
                    "total_tokens": 2030,
                },
            },
        )

    async def run():
        settings = Settings(
            kind="report",
            llm_base_url="https://fixture.invalid/v1",
            llm_model="fixture",
            llm_api_key="fixture",
            llm_synthesis_max_tokens=16384,
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            for budget, expected_calls in [
                (1000, 0),
                (profiles["local-v1"]["attempt_budget"], 1),
            ]:
                llm = LLM(
                    settings,
                    time.monotonic() + 30,
                    budget,
                    lambda _: None,
                    http,
                )
                output = copy.deepcopy(result)
                await explain(output, llm, EXPLANATION)
                assert llm.usage["calls"] == expected_calls
                assert llm.usage["request_attempts"] == expected_calls
                assert llm.last_failure == (
                    None if expected_calls else "llm_token_budget_exhausted"
                )
                assert output["narrative_status"] == (
                    "complete" if expected_calls else "failed"
                )
        assert len(calls) == 1

    asyncio.run(run())
