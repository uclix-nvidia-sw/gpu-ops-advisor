"""Sanitized shapes from the three 11:44 runs; no production identifiers."""

import copy

import pytest

from rcca_agent.fleet_events import enrich_report_inventory
from rcca_agent.synthesis import validate_synthesis
from rcca_agent.synthesis_context import bounded_context, encoded_size
from test_fleet_rca import fleet, evidence, profile
from agent_common.parsers import parse_health


def test_switch_pci_is_not_compared_with_gpu_inventory():
    raw = fleet()
    raw["attributes"]["reason"] += " PCI:0000:00:00.0"
    raw["resources"]["gpuInfo.gpus"] = '[{"uuid":"GPU-fixture","busID":"0000:08:00.0"}]'
    e, p = evidence(raw), profile()
    before = copy.deepcopy(e)
    report = enrich_report_inventory(
        parse_health([e], p["health_contracts"], p["queries"]), [e]
    )[0]
    assert report["pci_inventory_relation"] == "switch_inventory_required"
    assert report["fact_eligible"] is False
    assert e == before


@pytest.mark.parametrize(
    "relation,claim",
    [
        ("not_in_reported_inventory", "GPU가 물리적으로 분리되었을 가능성이 있다."),
        (
            "not_in_reported_inventory",
            "존재하지 않는 장치에서 핫 제거가 일어났을 가능성이 있다.",
        ),
        (
            "switch_inventory_required",
            "장치 주소가 없어 잘못된 명령이 전달되었을 가능성이 있다.",
        ),
    ],
)
def test_mapping_gap_cannot_become_cause(relation, claim):
    response = {
        "hypotheses": [
            {
                "claim": claim,
                "supporting_refs": ["log"],
                "contradicting_refs": [],
                "missing_inputs": [],
            }
        ],
        "limitations": [],
    }
    with pytest.raises(ValueError, match="unsupported_identity_cause"):
        validate_synthesis(
            response,
            ["log"],
            [{"evidence_refs": ["log"], "pci_inventory_relation": relation}],
        )
    response["hypotheses"] = []
    response["limitations"] = ["오류 장치와 인벤토리의 연결을 확인해야 합니다."]
    assert validate_synthesis(response, ["log"]) == []


def test_later_query_keeps_representative_samples_without_changing_source():
    payload = {
        "device_observations": [],
        "metric_observations": [
            {
                "evidence_refs": [ref],
                "labels": {"gpu": str(i)},
                "samples": [[t, i] for t in range(123)],
            }
            for ref in ("D44-evidence", "D02-evidence")
            for i in range(8)
        ],
        "observation_refs": ["D44-evidence", "D02-evidence"],
    }
    before = copy.deepcopy(payload)
    view = bounded_context(payload, 1600)
    assert set(view["observation_refs"]) == set(payload["observation_refs"])
    assert encoded_size(view) <= 1600
    assert not view["context_selection"]["complete"]
    assert payload == before


@pytest.mark.parametrize(
    "claim",
    [
        "보고된 PCI 주소가 인벤토리에 없는 GPU와 매핑되지 않아 장치 식별 불확실성이 원인일 가능성이 있다",
        "장치 신원이 확인되지 않아 문제가 발생했을 가능성이 있다",
        "인벤토리 불일치로 문제가 발생했을 가능성이 있다",
    ],
)
def test_identity_uncertainty_is_not_a_cause_without_relation_metadata(claim):
    reply = {
        "hypotheses": [
            {
                "claim": claim,
                "supporting_refs": ["log"],
                "contradicting_refs": [],
                "missing_inputs": [],
            }
        ],
        "limitations": [],
    }
    with pytest.raises(ValueError, match="unsupported_identity_cause"):
        validate_synthesis(reply, ["log"])
    reply["hypotheses"] = []
    reply["limitations"] = ["장치 신원이 확인되지 않아 원인을 판단하지 못했습니다."]
    assert validate_synthesis(reply, ["log"]) == []
