"""Paired budget regressions with real accounting and fixed model responses."""

from copy import deepcopy
import json
import time

import httpx
import pytest

from agent_common.llm import LLM
from agent_common.observation import Observation
from agent_common.settings import Settings
from rcca_agent import evaluation
from rcca_agent.prompts import SYNTHESIS
from rcca_agent.synthesis import reserve_review_budget, synthesis_view
from rcca_agent.synthesis_context import encoded_size
from evaluation_fixtures import interpretation_reply, review_reply
from test_rca_analysis import analysis_reply
from test_rca_evaluation import DATA, observation
from test_rca_repairs import payload


async def run_round(
    budget,
    reported,
    rule_size,
    monkeypatch,
    *,
    fixed=False,
    unprotected=False,
    truncated=False,
):
    requests = []

    def handler(request):
        body = json.loads(request.content)
        inputs = json.loads(body["messages"][1]["content"])
        if "draft" in inputs:
            stage, response = "review", review_reply(inputs, "acceptable")
        elif body["messages"][0]["content"].endswith(SYNTHESIS):
            stage, response = "synthesis", analysis_reply(inputs["observation_refs"])
        else:
            stage, response = "interpretation", interpretation_reply()
        requests.append((stage, body["max_tokens"]))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length"
                        if truncated and stage == "synthesis"
                        else "stop",
                        "message": {
                            "content": json.dumps(response, ensure_ascii=False)
                        },
                    }
                ],
                **({"usage": {"total_tokens": 1000}} if reported else {}),
            },
        )

    def assemble(candidates):
        return candidates, [
            {
                "text": "담당자가 근거를 검토하세요." * rule_size,
                "eligibility": "eligible",
                "execution": "not_performed",
                "evidence_refs": ["log"],
                "value_refs": [],
            }
        ]

    settings = Settings(
        kind="rca",
        llm_base_url="http://fixture.invalid/v1",
        llm_model="fixture",
        llm_api_key="fixture",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        llm = LLM(settings, time.monotonic() + 60, budget, lambda _: None, http)
        obs = Observation({}, {"queries": {}}, DATA, time.monotonic() + 60)
        original = observation("partial", False)
        obs.evidence.append(deepcopy(original))
        with monkeypatch.context() as patch:
            if fixed:
                patch.setattr(
                    evaluation,
                    "reserve_review_budget",
                    lambda llm, payload, requested, floor: (
                        max(llm.reserved_tokens, requested),
                        {},
                    ),
                )
            elif unprotected:
                patch.setattr(
                    evaluation,
                    "reserve_review_budget",
                    lambda llm, payload, requested, floor: reserve_review_budget(
                        llm, payload, requested
                    ),
                )
            result = await evaluation.evaluate_analysis(
                obs, DATA, {}, [], payload(), assemble, llm, {}, 0, []
            )
        assert obs.evidence[0] == original
        assert llm.reserved_tokens == 0
        assert 0 <= llm.remaining <= budget
        assert llm.usage["charged_tokens"] == budget - llm.remaining
        assert result["review"]["analysis_id"] == result["draft"]["analysis_id"]
        return result, requests


@pytest.mark.asyncio
@pytest.mark.parametrize("reported", [False, True])
@pytest.mark.parametrize("rule_size", [1, 20])
async def test_allocation_does_not_trade_review_for_synthesis(
    monkeypatch, reported, rule_size
):
    recovered = []
    for budget in [18000, 21000, 23000, 25000, 27000, 30000, 32768, 40000]:
        before, _ = await run_round(
            budget, reported, rule_size, monkeypatch, fixed=True
        )
        released, _ = await run_round(
            budget, reported, rule_size, monkeypatch, unprotected=True
        )
        after, requests = await run_round(budget, reported, rule_size, monkeypatch)
        before_failure = (
            before["synthesis_status"] == "complete"
            and before["review"]["execution_status"] != "complete"
        )
        after_failure = (
            after["synthesis_status"] == "complete"
            and after["review"]["execution_status"] != "complete"
        )
        assert not after_failure or before_failure, (budget, after, requests)
        assert not after_failure or (
            released["synthesis_status"] == "complete"
            and released["review"]["execution_status"] != "complete"
        )
        if before["review"]["execution_status"] == "complete":
            assert after["review"]["execution_status"] == "complete"
        if (
            before["synthesis_status"] != "complete"
            and after["synthesis_status"] == "complete"
        ):
            assert after["review"]["execution_status"] == "complete"
            recovered.append(budget)
    if not reported and rule_size == 1:
        assert recovered


@pytest.mark.asyncio
@pytest.mark.parametrize("reported", [False, True])
async def test_truncated_analysis_leaves_review_capacity(monkeypatch, reported):
    result, requests = await run_round(25000, reported, 1, monkeypatch, truncated=True)
    assert any(stage == "synthesis" for stage, _ in requests)
    assert result["synthesis"]["error_code"] == "llm_output_truncated"
    # A deterministic fallback is not model-reviewed; the reserve stays unspent.
    assert result["review"]["execution_status"] == "skipped"
    assert result["review"]["reason"] == "synthesis_unavailable"
    assert not any(stage == "review" for stage, _ in requests)


def test_floor_and_existing_allocation_contract():
    class Model:
        remaining = 28237
        reserved_tokens = 500

    data = payload()
    original = deepcopy(data)
    before, limit = synthesis_view(data, Model.remaining, 22000)
    assert encoded_size(before) > limit or not before["observation_refs"]
    selected, allocation = reserve_review_budget(Model(), data, 22000, 12000)
    assert 12000 <= selected < 22000
    assert allocation["synthesis_sources_fit"]
    assert allocation["review_reserve_reduced"]
    assert allocation["requested_review_reserve"] == 22000
    assert allocation["applied_review_reserve"] == selected
    assert data == original and Model.reserved_tokens == 500
    Model.remaining = 1000
    assert reserve_review_budget(Model(), data, 20000)[0] == 500
    assert reserve_review_budget(Model(), data, 20000, 12000)[0] == 20000
