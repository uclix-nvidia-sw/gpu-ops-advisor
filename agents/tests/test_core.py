import asyncio
import csv
import io
import json
import time

import httpx
import pytest

from agent_common.calculations import (
    allocation_hours,
    seconds,
    intersect,
    low_activity,
    low_activity_windows,
    weighted_mean,
    weighted_p95,
    energy,
    sample_intervals,
    normalize_health,
)
from agent_common.contracts import content_hash, go_json, result_status
from agent_common.artifacts import render
from agent_common.llm import LLM, RemoteUncertain, strip_reasoning
from agent_common.observation import Observation
from agent_common.settings import Settings
from rcca_agent.workflow import compatible_runbooks


def test_contract_calculations():
    rows = [
        dict(cluster_id="c", gpu_uuid=g, mode="exclusive", start=0, end=8 * 3600)
        for g in ["g1", "g2"]
    ]
    assert allocation_hours(rows + rows) == 16
    # Joint intersection, not mean/min of source coverage.
    assert seconds(intersect([(0, 100)], [(50, 150)])) == 50
    actual = low_activity(
        [(0, 3600)], [(0, 54 * 60, 0), (54 * 60, 58 * 60, 10)], 0, 3600
    )
    assert actual["coverage"] == pytest.approx(58 / 60)
    assert actual["low_ratio"] == pytest.approx(54 / 58)
    assert actual["low_gpu_hours"] == 0.9
    assert actual["status"] == "low_activity_candidate"
    assert (
        low_activity([(0, 300)], [(0, 300, 0)], 0, 300)["status"] == "insufficient_data"
    )
    rows = [
        dict(
            cluster_id="c",
            gpu_uuid="g",
            mode="exclusive",
            pod_uid=p,
            episode=p,
            start=a,
            end=b,
        )
        for p, a, b in [("A", 0, 1800), ("B", 1800, 3600)]
    ]
    assert all(
        w["status"] == "insufficient_data"
        for w in low_activity_windows(rows, {("c", "g"): [(0, 3600, 0)]})
    )
    assert weighted_mean([(0, 90, 10), (90, 100, 100)]) == 19
    assert weighted_p95([(0, 96, 10), (96, 100, 100)]) == 10
    assert energy([(0, 10 * 3600, 250)] * 4) == 10
    assert energy([(0, 10 * 3600, 200)] * 4) == 8
    assert sample_intervals([(0, "10"), (100, "20")], 0, 200, 30) == [
        (0, 30, 10),
        (100, 130, 20),
    ]
    assert sample_intervals([(0, "10"), (0, "20")], 0, 30, 30) == []


def test_health_and_hash_and_reasoning():
    contract = {
        "producer_contract": "fleet-v1",
        "revision": "p1",
        "checks": {"unavailable": "unavailable"},
        "health": {"Healthy": {"normalized_health": "healthy"}},
    }
    health = normalize_health(
        {
            "health": "Healthy",
            "check_status": "unavailable",
            "producer_contract": "fleet-v1",
        },
        contract,
    )
    assert (
        health["normalized_health"] == "unknown" and health["raw_health"] == "Healthy"
    )
    assert (
        go_json({"n": 1.0, "s": "<한국>&", "tiny": 1e-7})
        == '{"n":1,"s":"\\u003c한국\\u003e\\u0026","tiny":1e-7}'
    )
    assert strip_reasoning('<think>secret</think>{"ok":true}') == '{"ok":true}'
    assert strip_reasoning("reasoning</think>answer") == "answer"
    assert strip_reasoning("<think>unfinished") == ""


def test_runbook_compatibility_before_latest():
    body = {"claim": "known issue"}
    rows = [
        dict(
            id=str(i),
            knowledge_key="same",
            revision=i,
            content=body,
            content_hash=content_hash(body),
            reviewed_content_hash=content_hash(body),
            compatibility={"producer_contract": c},
        )
        for i, c in [(1, "A"), (2, "B")]
    ]
    assert compatible_runbooks(rows, {"producer_contract": "A"})[0]["revision"] == 1
    assert compatible_runbooks(rows, {"producer_contract": "C"}) == []


def test_result_status_and_export():
    assert result_status([{"status": "ready"}, {"status": "blocked"}]) == "partial"
    assert result_status([{"status": "blocked"}]) == "blocked"
    result = {
        "measurements": [
            dict(id="=cmd", value=10, unit="<script>", method="test", quality={})
        ],
        "topics": [],
        "result_status": "partial",
        "limitations": ["<script>bad</script>"],
    }
    output = render(result)
    assert b"<script>" not in output["html"]
    rows = list(csv.reader(io.StringIO(output["csv"].decode("utf-8-sig"))))
    assert rows[1][0] == "'=cmd"


@pytest.mark.asyncio
async def test_llm_transport_and_unknown_termination():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '<think>private</think>{"fact_ids":["a"]}'
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"total_tokens": 20},
            },
        )

    settings = Settings(
        "report",
        llm_base_url="http://test/v1",
        llm_model="model",
        llm_api_key="test-only",
    )
    states = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        llm = LLM(settings, time.monotonic() + 10, 10000, states.append, http)
        assert await llm.complete("facts", {}) == {"fact_ids": ["a"]}
        assert states == ["running", "terminated"]
        assert requests[0]["model"] == "model"

    def timeout(request):
        raise httpx.ReadTimeout("fixture timeout")

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as http:
        llm = LLM(settings, time.monotonic() + 10, 10000, states.append, http)
        with pytest.raises(RemoteUncertain):
            await llm.complete("facts", {})
        assert states[-1] == "unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError,
        httpx.ReadTimeout,
        httpx.RemoteProtocolError,
        asyncio.CancelledError,
    ],
)
async def test_llm_transport_logs_safe_diagnostics_and_preserves_quarantine(
    error, caplog
):
    def handler(request):
        raise error("Bearer secret-token and private-prompt") from OSError(
            "private-upstream-detail"
        )

    settings = Settings(
        "rca",
        llm_base_url="http://test/v1",
        llm_model="model",
        llm_api_key="secret-token",
    )
    states = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        llm = LLM(settings, time.monotonic() + 10, 10000, states.append, http)
        expected = (
            asyncio.CancelledError
            if error is asyncio.CancelledError
            else RemoteUncertain
        )
        with pytest.raises(expected):
            await llm.complete("private-prompt", {}, stage="investigation")
    assert states == ["running", "unknown"]
    assert f"error_type={error.__name__}" in caplog.text
    assert "cause_type=OSError" in caplog.text
    assert "stage=investigation attempt=1" in caplog.text
    assert "elapsed_seconds=" in caplog.text and "timeout_seconds=" in caplog.text
    assert all(
        secret not in caplog.text
        for secret in ("secret-token", "private-prompt", "private-upstream-detail")
    )


@pytest.mark.asyncio
async def test_llm_http_error_logs_status_without_body_or_quarantine(caplog):
    def handler(request):
        return httpx.Response(401, json={"error": "private-response"})

    settings = Settings(
        "rca",
        llm_base_url="http://test/v1",
        llm_model="model",
        llm_api_key="secret-token",
    )
    states = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        llm = LLM(settings, time.monotonic() + 10, 10000, states.append, http)
        assert await llm.complete("private-prompt", {}) is None
    assert states == ["running", "terminated"]
    assert "LLM HTTP failed" in caplog.text and "status=401" in caplog.text
    assert all(
        secret not in caplog.text
        for secret in ("secret-token", "private-prompt", "private-response")
    )


@pytest.mark.asyncio
async def test_query_scope_budget_and_failure_independence():
    profile = json.load(open("agents/tests/fixtures/config-v7.json", encoding="utf-8"))
    profile["clusters"]["cpc-2"] = {
        "mimir_uid": "metrics",
        "metric_selector": {"cluster_id": "cpc-2"},
    }
    profile["limits"]["max_queries"] = 1
    requests = []

    async def query(args):
        requests.append(args)
        return {"data": [{"metric": {"UUID": "g"}, "values": [[100, "0"]]}]}

    data = {
        "scope": {"clusters": [{"cluster_id": "cpc-2", "namespaces": ['dev"|.*']}]},
        "time_range": {"start": "2026-09-15T00:00:00Z", "end": "2026-09-15T02:00:00Z"},
    }
    obs = Observation({"query_prometheus": query}, profile, data, time.monotonic() + 10)
    result = await obs.collect("D02")
    assert len(requests) == 1 and 'cluster_id="cpc-2"' in requests[0]["expr"]
    assert requests[0]["queryType"] == "instant"
    assert result[-1]["quality"]["reason"] == "budget_exhausted"
    with pytest.raises(ValueError):
        await obs.collect(
            "D02", {"start": "2026-09-14T00:00:00Z", "end": "2026-09-15T00:00:00Z"}
        )
