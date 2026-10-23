import copy
import json

import pytest

from rcca_agent.synthesis import identifier_tokens, validate_synthesis
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


def response(ref="log", claim="보고된 SXID 11001은 추가 확인이 필요합니다."):
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

    def check(limitation, claim="보고된 SXID 11001은 추가 확인이 필요합니다."):
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


@pytest.mark.parametrize(
    "supporting,contradicting,rule",
    [
        ([], [], "empty_supporting_refs"),
        (["D09"], [], "unknown_observation_refs"),
        (["log"], ["log"], "overlapping_evidence_refs"),
    ],
)
def test_reference_diagnostics_distinguish_failure_without_accepting_bad_refs(
    supporting, contradicting, rule
):
    from rcca_agent.synthesis import SynthesisValidationError

    reply = response()
    reply["hypotheses"][0]["supporting_refs"] = supporting
    reply["hypotheses"][0]["contradicting_refs"] = contradicting
    with pytest.raises(SynthesisValidationError) as caught:
        validate_synthesis(reply, ["log"])
    assert caught.value.diagnostic == {
        "code": "invalid_evidence_references",
        "rule": rule,
        "tokens": [],
        "hypothesis_index": 0,
    }


@pytest.mark.parametrize("code", ["XID79", "XID 79", "XID:79", "xid79"])
def test_cited_code_spelling_is_not_an_unregistered_measurement(code):
    observations = [{"error_code": "xid:79", "evidence_refs": ["log"]}]
    reply = response(claim=f"보고된 {code}는 추가 확인이 필요합니다.")
    reply["limitations"] = [f"{code}만으로 실제 장치 고장은 확정할 수 없습니다."]
    assert validate_synthesis(reply, ["log"], observations)
    with pytest.raises(ValueError):
        validate_synthesis(reply, ["log"], [])


def test_code_spelling_does_not_whitelist_adjacent_measurements():
    observations = [{"error_code": "xid:79", "evidence_refs": ["log"]}]
    reply = response(claim="XID79 오류가 79회 발생했습니다.")
    with pytest.raises(ValueError, match="unregistered_numeric_claim"):
        validate_synthesis(reply, ["log"], observations)


def test_language_diagnostic_preserves_offsets_and_hides_raw_prose():
    text = "노드 fixture-node GPU 상태는 spuriously 미확인입니다."
    with pytest.raises(ValueError) as caught:
        validate_synthesis(
            {"hypotheses": [], "limitations": [text]}, [], identifiers=["fixture-node"]
        )
    diagnostic = caught.value.diagnostic["language_diagnostic"]
    start = text.index("spuriously")
    assert diagnostic["matches"] == [{"start": start, "end": start + len("spuriously")}]
    assert not diagnostic["missing_korean_prose"]
    assert "spuriously" not in json.dumps(diagnostic)
    assert "fixture-node" not in json.dumps(diagnostic)


@pytest.mark.parametrize(
    "component",
    ["accelerator-nvidia-error-xid", "accelerator-nvidia-error-sxid", "cpu", "disk"],
)
def test_identity_cause_precedes_language_for_any_component(component):
    observation = {
        "component": component,
        "evidence_refs": ["log"],
        "device_mapping": "unresolved",
    }
    with pytest.raises(ValueError) as caught:
        validate_synthesis(
            response(claim="장치 식별 불확실성이 unexpected 원인일 가능성이 있다"),
            ["log"],
            [observation],
        )
    assert caught.value.diagnostic["rule"] == "identity_is_not_cause"
    # A limitation remains legitimate; no GPU identity is required for node observations.
    assert (
        validate_synthesis(
            {
                "hypotheses": [],
                "limitations": [
                    "보고 대상의 연결 정보가 없어 현재 상태를 확인할 수 없습니다."
                ],
            },
            ["log"],
            [observation],
        )
        == []
    )


def test_bounded_context_prioritizes_event_device_without_mutating_history():
    raw = {
        "error_events": [
            {
                "reported_device": "PCI:0000:bd:00",
                "evidence_refs": ["log"],
                "status": "reported_event",
                "time_basis": "producer_event_time",
                "event_time": "2026-10-19T01:00:00Z",
            }
        ],
        "device_observations": [
            {
                "reported_pci_addresses": ["PCI:0000:87:00"],
                "evidence_refs": ["log"],
                "reason": "old" * 150,
            },
            {
                "reported_pci_addresses": ["PCI:0000:bd:00"],
                "evidence_refs": ["log"],
                "reason": "incident",
            },
        ],
    }
    before = copy.deepcopy(raw)
    view = bounded_context(raw, 1100)
    assert raw == before
    assert view["device_observations"][0]["reported_pci_addresses"] == [
        "PCI:0000:bd:00"
    ]
    assert encoded_size(view) <= 1100


def test_planned_incident_context_leaves_room_for_32k_route_output():
    from rcca_agent.synthesis import synthesis_view

    raw = payload()
    raw["incident_comparison"] = [{"text": "오류 보고 비교", "evidence_refs": ["log"]}]
    view, limit = synthesis_view(raw, 131072, 21000)
    assert limit == 24000
    assert encoded_size(view) <= limit
    assert "log" in view["observation_refs"]
    assert view["metric_observations"]
    assert len(raw["metric_observations"]) == 138
    del raw["incident_comparison"]
    assert synthesis_view(raw, 131072, 21000)[1] == 64000
