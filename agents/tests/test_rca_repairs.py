import copy

import pytest

from agent_common.normalize import allocations
from agent_common.parsers import parse_health, health_facts
from rcca_agent.incident import alert_clues
from rcca_agent.synthesis import (
    identifier_tokens,
    validate_synthesis,
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
def test_xid_clues_do_not_choose_a_purpose(component):
    clues = alert_clues({"alert": {"labels": {"component": component}}})
    assert clues["symptom"] == "xid"
    assert "purpose_ids" not in clues


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


def test_numeric_diagnostic_preserves_offsets_without_raw_reply():
    text = "XID79 관측 뒤 secret_token_12345 값과 두 개의 장치를 확인합니다."
    with pytest.raises(SynthesisValidationError) as caught:
        validate_synthesis(
            reply(text), ["log"], [{"error_code": "xid:79", "evidence_refs": ["log"]}]
        )
    diagnostic = caught.value.diagnostic["numeric_diagnostic"]
    assert len(diagnostic["text_sha256"]) == 64
    assert diagnostic["text_length"] == len(text)
    assert diagnostic["matches"][0] == {
        "start": text.index("12345"),
        "end": text.index("12345") + 5,
        "kind": "digits",
    }
    assert diagnostic["matches"][1]["kind"] == "number_word"
    assert "secret_token" not in str(caught.value.diagnostic)
    assert "12345" not in str(caught.value.diagnostic)
