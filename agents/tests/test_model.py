import asyncio
import json
import math
import time

import httpx
import pytest

from agent_common.llm import LLM
from agent_common.model import model_destination, model_settings
from agent_common.settings import Settings


@pytest.mark.parametrize("kind", ["rca", "report"])
@pytest.mark.asyncio
async def test_routed_model_uses_saved_name_and_authentication(kind, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "fixture-key")
    monkeypatch.setenv("LLM_MODEL_SYNTHESIS", "wrong-deployment-model")
    monkeypatch.setenv("DSX_MODEL_HOSTS", "127.0.0.1:12345")
    settings = model_settings(
        Settings(kind),
        {
            "secret_ref": "env:LLM_API_KEY",
            "config": {
                "endpoint_url": "http://127.0.0.1:12345/v1",
                "model_name": "saved-model",
            },
        },
    )

    def handler(request):
        assert request.headers["Authorization"] == "Bearer fixture-key"
        assert request.headers["Host"] == "127.0.0.1:12345"
        assert request.url.path == "/v1/chat/completions"
        assert json.loads(request.content)["model"] == "saved-model"
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"ok":true}'}}]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        llm = LLM(settings, time.monotonic() + 10, 10000, lambda _: None, http)
        assert await llm.complete("fixture", {}) == {"ok": True}


@pytest.mark.parametrize("limit,expected_calls", [(1, 1), (3, 3)])
async def test_author_single_request_limit_does_not_change_other_callers(
    limit, expected_calls
):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503, json={"error": "fixture unavailable"})

    settings = Settings(
        "rca",
        llm_base_url="http://test/v1",
        llm_model="fixture",
        llm_api_key="test-only",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        llm = LLM(settings, time.monotonic() + 10, 32768, lambda _: None, http)
        llm.request_attempt_limit = limit
        assert await llm.complete("fixture", {}, stage="synthesis") is None
        assert llm.last_failure == "llm_http_error"
        assert len(calls) == expected_calls


def test_missing_key_and_unknown_reference_do_not_fall_back(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    base = Settings("report", llm_api_key="other-key")
    for ref in ["env:LLM_API_KEY", "env:DATABASE_URL"]:
        with pytest.raises(ValueError):
            model_settings(base, {"config": {}, "secret_ref": ref})
    assert model_settings(base, None) is base
    anonymous = model_settings(
        base, {"config": {"endpoint_url": "http://test/v1", "model_name": "public"}}
    )
    assert anonymous.llm_api_key == ""
    assert LLM(anonymous, time.monotonic() + 10, 100, lambda _: None).configured


@pytest.mark.asyncio
async def test_private_dns_requires_allowlist_and_keeps_original_host(monkeypatch):
    monkeypatch.setenv("DSX_MODEL_HOSTS", "model.internal")
    monkeypatch.delenv("DSX_MODEL_CIDRS", raising=False)

    async def dns(*args, **kwargs):
        return [(2, 1, 6, "", ("192.168.20.171", 443))]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", dns)
    with pytest.raises(ValueError, match="destination"):
        await model_destination("https://model.internal/v1/chat/completions")
    monkeypatch.setenv("DSX_MODEL_CIDRS", "192.168.20.171/32")
    url, headers, extensions = await model_destination(
        "https://model.internal/v1/chat/completions"
    )
    assert str(url) == "https://192.168.20.171/v1/chat/completions"
    assert headers == {"Host": "model.internal"}
    assert extensions == {"sni_hostname": "model.internal"}
    for raw in [
        "https://wrong.internal/v1",
        "https://user:password@model.internal/v1",
        "https://model.internal/v1?secret=x",
    ]:
        with pytest.raises(ValueError, match="endpoint"):
            await model_destination(raw)


@pytest.mark.parametrize("kind", ["report", "rca"])
@pytest.mark.parametrize("medium_effort", [False, True])
async def test_ops_medium_effort_override_is_explicit_and_does_not_change_rca(
    kind, medium_effort
):
    settings = Settings(
        kind,
        llm_base_url="http://test/v1",
        llm_model="auto-router",
        llm_api_key="fixture",
        ops_llm_medium_effort=medium_effort,
    )

    def handler(request):
        payload = json.loads(request.content)
        if kind == "report" and medium_effort:
            assert payload["chat_template_kwargs"] == {
                "enable_thinking": True,
                "medium_effort": True,
            }
        else:
            assert "chat_template_kwargs" not in payload
        assert payload["model"] == "auto-router"
        assert payload["max_tokens"] == settings.llm_synthesis_max_tokens
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"content": '{"ok":true}'}}
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 4,
                    "total_tokens": 14,
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        llm = LLM(settings, time.monotonic() + 10, 65536, lambda _: None, http)
        assert await llm.complete("fixture", {}) == {"ok": True}
        assert llm.usage["charged_tokens"] == 14


@pytest.mark.parametrize(
    "raw,expected", [("", False), ("true", True), ("false", False)]
)
def test_ops_medium_effort_environment(monkeypatch, raw, expected):
    monkeypatch.setenv("OPS_LLM_MEDIUM_EFFORT", raw)
    assert Settings("report").ops_llm_medium_effort is expected


@pytest.mark.parametrize("raw", ["0", "1", '"false"', "[]", "{}", "False", "null"])
def test_ops_medium_effort_rejects_ambiguous_values(monkeypatch, raw):
    monkeypatch.setenv("OPS_LLM_MEDIUM_EFFORT", raw)
    with pytest.raises(ValueError):
        Settings("report")


def context_settings(kind, cap, context):
    return Settings(
        kind,
        llm_base_url="http://test/v1",
        llm_model="fixture-model",
        llm_api_key="fixture",
        llm_synthesis_max_tokens=cap,
        llm_context_tokens=context,
    )


# A ~60KB prompt: the server limit (prompt + max_tokens <= 65536) leaves less output
# room than the job budget (131072), so the context limit decides the cap.
CONTEXT_DATA = {"evidence": "x" * 60000}


@pytest.mark.parametrize("context", [0, 65536])
def test_context_limit_trims_the_configured_output_cap(context):
    llm = LLM(context_settings("rca", 41000, context), 0, 131072, lambda _: None)
    budget = llm.request_budget("fixture", CONTEXT_DATA, "synthesis")
    room = 65536 - math.ceil(budget["prompt_token_bound"] / 2)
    assert budget["output_token_cap"] == (room if context else 41000)
    assert budget.get("context_tokens") == (context or None)


@pytest.mark.parametrize("kind", ["rca", "report"])
async def test_length_retry_doubles_within_the_context_limit(kind):
    caps = []

    def handler(request):
        caps.append(json.loads(request.content)["max_tokens"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length" if len(caps) == 1 else "stop",
                        "message": {"content": '{"ok":true}'},
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        )

    settings = context_settings(kind, 20000, 65536)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        llm = LLM(settings, time.monotonic() + 10, 131072, lambda _: None, http)
        bound = llm.request_budget("fixture", CONTEXT_DATA, "synthesis")[
            "prompt_token_bound"
        ]
        assert await llm.complete("fixture", CONTEXT_DATA) == {"ok": True}
    room = 65536 - math.ceil(bound / 2)
    assert room < 40000 and caps == [20000, room]


@pytest.mark.parametrize("raw,expected", [("0", 0), ("65536", 65536)])
def test_context_limit_environment(monkeypatch, raw, expected):
    monkeypatch.setenv("LLM_CONTEXT_TOKENS", raw)
    assert Settings("rca").llm_context_tokens == expected


def test_context_limit_rejects_negative_values(monkeypatch):
    monkeypatch.setenv("LLM_CONTEXT_TOKENS", "-1")
    with pytest.raises(ValueError):
        Settings("rca")
