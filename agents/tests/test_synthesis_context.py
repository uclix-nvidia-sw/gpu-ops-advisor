import asyncio
import copy
import json
import time

import httpx
import pytest

from agent_common.llm import LLM, RemoteUncertain
from agent_common.settings import Settings
from rcca_agent.prompts import SYNTHESIS
from rcca_agent.synthesis import identifier_tokens, synthesize, validate_synthesis
from rcca_agent.synthesis_context import bounded_context, encoded_size


def payload():
    return {
        "device_observations": [{"error_code": "sxid:11001", "evidence_refs": ["log"]}],
        "pod_relations": [],
        "metric_observations": [
            {
                "labels": {"node": "fixture", "pod": str(i)},
                "evidence_refs": [f"m{i}"],
                "samples": [[1700000000 + t, 1.0] for t in range(122)],
            }
            for i in range(138)
        ],
        "observation_refs": ["log"] + [f"m{i}" for i in range(138)],
    }


def response(ref="log", claim="Reported SXID 11001 needs confirmation."):
    return {
        "hypotheses": [
            {
                "claim": claim,
                "supporting_refs": [ref],
                "contradicting_refs": [],
                "missing_inputs": ["confirmation"],
            }
        ],
        "limitations": [],
    }


def test_bounded_original_samples_and_references_without_mutation():
    raw = payload()
    original = copy.deepcopy(raw)
    view = bounded_context(raw, 16000)
    assert encoded_size(view) <= 16000
    assert raw == original
    assert not view["context_selection"]["complete"]
    assert view["context_selection"]["omitted_metric_samples"] > 0
    assert view["context_selection"]["omitted_observations"]["metric_observations"] > 0
    assert set(view["observation_refs"]) == {
        ref
        for key in ("device_observations", "pod_relations", "metric_observations")
        for row in view[key]
        for ref in row["evidence_refs"]
    }
    for row in view["metric_observations"]:
        assert len(row["samples"]) == 8
        source = next(
            r for r in raw["metric_observations"] if r["labels"] == row["labels"]
        )
        assert all(sample in source["samples"] for sample in row["samples"])
        assert row["samples"][0] == source["samples"][0]
        assert row["samples"][-1] == source["samples"][-1]
    omitted = next(
        ref for ref in raw["observation_refs"] if ref not in view["observation_refs"]
    )
    with pytest.raises(ValueError, match="invalid_evidence_references"):
        validate_synthesis(
            response(omitted, "Unsupported observation."), view["observation_refs"]
        )


def test_only_cited_typed_error_identifiers_can_contain_digits():
    observations = payload()["device_observations"]
    assert (
        validate_synthesis(response(), ["log"], observations)[0]["causal_status"]
        == "candidate"
    )
    for claim in ("SXID 11002", "XID 11001", "SXID 11001 temperature 99", "node 1"):
        with pytest.raises(ValueError, match="unregistered_numeric_claim"):
            validate_synthesis(response(claim=claim), ["log"], observations)
    with pytest.raises(ValueError):
        validate_synthesis(response("metric"), ["log", "metric"], observations)


def test_input_identifiers_allowed_but_measurements_rejected():
    # Shape of the deployed RCA view: digit-bearing IDs, timestamps and samples.
    view = {
        "target": {"cluster_id": "cpc-2", "k8s_node_name": "vessl-k8s-worker-01"},
        "purpose_ids": ["R01"],
        "incident_time": "2026-10-01T02:27:11Z",
        "query_quality": [{"query_id": "D05"}, {"query_id": "D09"}],
        "device_observations": [
            {
                "error_code": "sxid:11001",
                "reason": "SXID 11001 temperature 95C on node3",
                "evidence_refs": ["log"],
            }
        ],
        "metric_observations": [
            {
                "labels": {"gpu": "0", "modelName": "Tesla V100-PCIE-16GB"},
                "samples": [[1700000000, "85C"]],
                "evidence_refs": ["metric"],
            }
        ],
        "limits": {"memory": "16GB", "window": "30m"},
    }
    ids = identifier_tokens(view)
    assert {"cpc-2", "vessl-k8s-worker-01", "R01", "D05", "V100-PCIE-16GB"} <= ids
    assert not ids & {"0", "2026-10-01T02:27:11Z", "85C", "95C", "16GB", "30m"}
    assert not any(" " in i for i in ids)
    assert "sxid:11001" not in ids
    observations = view["device_observations"]
    # Error codes remain limited to cited observations even with identifiers.
    with pytest.raises(ValueError, match="unregistered_numeric_claim"):
        validate_synthesis(
            response("metric", "sxid:11001 was reported."),
            ["log", "metric"],
            observations,
            ids,
        )

    def check(limitation, claim="Reported SXID 11001 needs confirmation."):
        reply = response(claim=claim)
        reply["limitations"] = [limitation]
        return validate_synthesis(reply, ["log"], observations, ids)

    for text in (
        "D05·D09 조회가 partial이라 cpc-2의 vessl-k8s-worker-01 상태가 불완전합니다.",
        "R01 판단은 Tesla V100-PCIE-16GB 장비 연결 확인이 필요합니다.",
        "d05 조회가 불완전합니다.",
    ):
        assert check(text)[0]["causal_status"] == "candidate"
    for text in (
        "GPU 0 온도가 85C입니다.",
        "SXID 11001 temperature 95C on node3",
        "30분 동안 오류가 없었습니다.",
        "D050 조회가 불완전합니다.",
        "vessl-k8s-worker-02 상태가 불명확합니다.",
        "cpc-2 노드 3대가 영향을 받았습니다.",
    ):
        with pytest.raises(ValueError, match="invalid_limitations"):
            check(text)
    with pytest.raises(ValueError, match="unregistered_numeric_claim"):
        check("D05 조회가 불완전합니다.", claim="vessl-k8s-worker-01 사용률 99")


@pytest.mark.asyncio
async def test_large_input_preflight_failure_then_bounded_real_transport_call():
    requests = []

    def handler(request):
        sent = json.loads(json.loads(request.content)["messages"][1]["content"])
        requests.append(sent)
        assert encoded_size(sent) <= 16000
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(response())},
                    }
                ],
                "usage": {"total_tokens": 2000},
            },
        )

    settings = Settings(
        kind="rca",
        llm_base_url="http://fixture.invalid/v1",
        llm_model="fixture",
        llm_api_key="fixture",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        llm = LLM(settings, time.monotonic() + 30, 32768, lambda _: None, http)
        assert await llm.complete(SYNTHESIS, payload()) is None
        assert llm.last_failure == "llm_token_budget_exhausted"
        assert llm.usage["request_attempts"] == 0 and requests == []
        diagnostics = {}
        status, candidates, limits = await synthesize(llm, payload(), diagnostics)
        assert status == "complete" and candidates and limits
        assert diagnostics["request_attempts"] == diagnostics["response_calls"] == 1
        assert diagnostics["error_code"] is None
        assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["budget", "http", "invalid", "uncertain", "cancel"])
async def test_failure_diagnostics_and_fencing(mode):
    class Model:
        configured = True
        remaining = 10 if mode == "budget" else 32768
        usage = {"calls": 1, "request_attempts": 1}  # Earlier stage is excluded.
        last_failure = "llm_http_error"

        async def complete(self, *args, **kwargs):
            self.usage["request_attempts"] += 1
            if mode == "uncertain":
                raise RemoteUncertain("private upstream error")
            if mode == "cancel":
                raise asyncio.CancelledError
            if mode == "http":
                return None
            self.usage["calls"] += 1
            return response("invented", "private model text")

    diagnostics = {}
    if mode in ("uncertain", "cancel"):
        with pytest.raises(
            RemoteUncertain if mode == "uncertain" else asyncio.CancelledError
        ):
            await synthesize(Model(), payload(), diagnostics)
    else:
        assert (await synthesize(Model(), payload(), diagnostics))[0] == "failed"
        assert (
            diagnostics["error_code"]
            == {
                "budget": "llm_context_budget_exhausted",
                "http": "llm_http_error",
                "invalid": "invalid_evidence_references",
            }[mode]
        )
        assert diagnostics["request_attempts"] == (0 if mode == "budget" else 1)
        assert "private" not in json.dumps(diagnostics)


@pytest.mark.asyncio
async def test_no_evidence_and_unconfigured_do_not_request():
    class Model:
        configured = False

    diagnostics = {}
    assert (await synthesize(Model(), {"observation_refs": []}, diagnostics))[
        0
    ] == "no_usable_evidence"
    assert diagnostics["request_attempts"] == 0
    assert (await synthesize(Model(), payload(), diagnostics))[0] == "unconfigured"
    assert diagnostics["error_code"] == "model_not_configured"
