import asyncio
import json
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
