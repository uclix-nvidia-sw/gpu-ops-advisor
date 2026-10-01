import copy
import time

import pytest

from agent_common.normalize import allocations
from agent_common.parsers import parse_health, health_facts
from rcca_agent.incident import alert_clues
from rcca_agent.procedures import select_procedure
from rcca_agent.synthesis import (
    identifier_tokens,
    validate_synthesis,
    synthesize,
    SynthesisValidationError,
)
from test_fleet_rca import evidence, profile, fleet, NS
from test_rca_korean import reply


def payload():
    return {
        "device_observations": [
            {
                "evidence_refs": ["log"],
                "fact_eligible": False,
                "time_basis": "loki_recorded_at",
            }
        ],
        "metric_observations": [],
        "pod_relations": [],
        "observation_refs": ["log"],
        "query_quality": [{"query_id": "D08"}],
    }


@pytest.mark.parametrize(
    "text",
    [
        "fact_eligible=false 관측이라 확정할 수 없습니다.",
        "time_basis가 loki_recorded_at 기준이라 확인해야 합니다.",
        "context_selection에 따라 일부 metric_observations가 생략됐습니다.",
        "D08 결과가 없어 확인해야 합니다.",
    ],
)
def test_actual_input_fields_masked_but_not_arbitrary_english(text):
    view = {**payload(), "context_selection": {}, "sample_selection": {}}
    assert validate_synthesis(
        reply(limitations=[text]), ["log"], identifiers=identifier_tokens(view)
    )
    with pytest.raises(SynthesisValidationError):
        validate_synthesis(
            reply(limitations=["arbitrary_secret_unknown_field 설명"]),
            ["log"],
            identifiers=identifier_tokens(view),
        )
    with pytest.raises(SynthesisValidationError, match="unregistered_numeric_claim"):
        validate_synthesis(
            reply("하나의 GPU가 영향을 받았을 가능성이 있습니다."), ["log"]
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "repair", ["valid", "invalid", "no_response", "budget", "deadline"]
)
async def test_repair_preserves_safe_candidates_and_never_logs_model_text(repair):
    class Model:
        configured = True
        remaining = 32768
        deadline = time.monotonic() + 60
        usage = {"request_attempts": 0, "calls": 0}

        async def complete(self, system, data, **kwargs):
            self.usage["request_attempts"] += 1
            self.usage["calls"] += 1
            if self.usage["calls"] == 1:
                if repair == "budget":
                    self.remaining = 1
                if repair == "deadline":
                    self.deadline = 0
                return reply(
                    limitations=[
                        "관측 조건은 추가 확인이 필요합니다.",
                        "secret_private_credential must not be stored",
                    ]
                )
            assert "secret_private" not in str(data)
            return (
                reply()
                if repair == "valid"
                else None
                if repair == "no_response"
                else reply("The GPU has physically failed.")
            )

    model, diagnostics = Model(), {}
    status, candidates, limits = await synthesize(model, payload(), diagnostics)
    assert status == "complete" and candidates
    assert "secret_private" not in str(diagnostics)
    assert diagnostics["repair_attempts"] == (
        0 if repair in {"budget", "deadline"} else 1
    )
    assert len(candidates) == 1
    if repair != "valid":
        assert any("제외" in line for line in limits)


def test_log_dedup_retains_provenance_and_cluster_boundary():
    p = profile()
    a = evidence()
    b = copy.deepcopy(a)
    b.update(id="copy", query_id="D05")
    c = copy.deepcopy(a)
    c.update(id="other-cluster", cluster_id="other")
    before = copy.deepcopy([a, b, c])
    health = parse_health([a, b, c], p["health_contracts"], p["queries"])
    assert len(health) == 2 and health[0]["evidence_refs"] == ["log", "copy"]
    assert [a, b, c] == before


def test_inventory_candidates_cannot_authorize_runbook_or_recovery():
    p, raw = profile(), fleet()
    raw["resources"]["gpuInfo.gpus"] = [
        {"uuid": "GPU-fixture", "busID": "0000:01:00.0"}
    ]
    health = parse_health([evidence(raw, NS)], p["health_contracts"], p["queries"])
    assert health[0]["gpu_candidates"][0]["verified"] is False
    assert (
        health_facts(
            health, {"node": "node-1", "machine_id": "machine-1", "cluster_id": "c"}
        )
        == {}
    )


def test_observed_zero_utilization_joins_pod_only_in_time_and_never_becomes_allocation():
    period = {"start": "1970-01-01T00:00:00Z", "end": "1970-01-01T00:01:00Z"}

    def metric(identifier, labels, value):
        return {
            "id": identifier,
            "cluster_id": "c",
            "tool_status": "ok",
            "quality": {
                "complete": True,
                "original_samples": True,
                "max_hold_seconds": 30,
                "allocation_semantics": "observed_pod_labels"
                if identifier == "gpu"
                else None,
            },
            "snapshot": {"data": [{"metric": labels, "values": [[10, str(value)]]}]},
        }

    gpu = metric(
        "gpu", {"UUID": "GPU-a", "node": "n", "namespace": "ns", "pod": "p"}, 0
    )
    pod = metric("pod", {"node": "n", "namespace": "ns", "pod": "p", "uid": "uid-a"}, 1)
    assert allocations([gpu], period, [pod]) == []
    linked = allocations([gpu], period, [pod], observed=True)
    assert linked[0]["pod_uid"] == "uid-a" and linked[0]["mode"] == "unknown"
    conflicting = copy.deepcopy(pod)
    conflicting["snapshot"]["data"][0]["metric"]["uid"] = "uid-b"
    assert allocations([gpu], period, [pod, conflicting], observed=True) == []


@pytest.mark.parametrize(
    "component", ["accelerator-nvidia-error-xid", "accelerator-nvidia-error-sxid"]
)
def test_xid_procedure_precedes_mapping_purpose(component):
    clues = alert_clues({"alert": {"labels": {"component": component}}})
    assert (
        select_procedure({"purpose_ids": ["R01", "R02"]}, clues).procedure_id
        == "gpu_access"
    )


def test_dcgm_uid_must_agree_with_same_time_ksm_when_join_required():
    period = {"start": "1970-01-01T00:00:00Z", "end": "1970-01-01T00:01:00Z"}
    e = {
        "id": "metric",
        "cluster_id": "c",
        "tool_status": "ok",
        "quality": {"original_samples": True, "max_hold_seconds": 30},
        "snapshot": {
            "data": [
                {
                    "metric": {
                        "UUID": "GPU-a",
                        "pod": "p",
                        "namespace": "ns",
                        "node": "n",
                        "uid": "unverified",
                    },
                    "values": [[10, "0"]],
                }
            ]
        },
    }
    assert allocations([e], period, [], observed=True, require_pod_join=True) == []
