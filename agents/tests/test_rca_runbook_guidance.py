import copy
import json
from pathlib import Path

import pytest

from rcca_agent.report import write_report
from rcca_agent.synthesis import validate_synthesis


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", ["published", "builtin"])
async def test_investigation_guidance_survives_without_remediation(origin):
    book = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "rcca-agent/runbooks/xid/RB-XID-79.json"
        ).read_text("utf-8")
    )
    result = dict(
        result_status="partial",
        termination_reason="missing_data",
        cause_candidates=[],
        recommendations=[],
        missing_inputs=[],
        limitations=[],
        quality={},
    )
    before = copy.deepcopy(result)

    class Offline:
        configured = False

    await write_report(
        result,
        {"incident_time": "2026-10-13T00:00:00Z"},
        {},
        [
            {
                "id": "book",
                "query_id": "runbook",
                "query_version": "4",
                "quality": {"origin": origin},
                "snapshot": book["content"],
            }
        ],
        Offline(),
    )
    guidance = next((s for s in result["narrative"] if s["id"] == "guidance"), None)
    if origin == "published":
        for term in (
            "HARDWARE_INSPECTION",
            "CONTACT_SUPPORT",
            "RESTART_BM",
            "R565",
            "A100",
            "호스트 진단 자료",
            "유지보수 승인",
            "동반 이벤트 부재",
        ):
            assert term in guidance["text"]
        assert guidance["evidence_refs"] == ["book"]
        assert "실행 승인으로 해석하지" in guidance["text"]
    else:
        assert guidance is None
    assert result["recommendations"] == before["recommendations"] == []
    assert result["result_status"] == "partial"


@pytest.mark.parametrize("word", ["spuriously", "possibly", "unexpectedly"])
def test_mixed_english_prose_rejected(word):
    response = {
        "hypotheses": [
            {
                "claim": f"GPU 오류가 {word} 발생했을 가능성이 있습니다.",
                "supporting_refs": ["log"],
                "contradicting_refs": [],
                "missing_inputs": [],
            }
        ],
        "limitations": [],
    }
    with pytest.raises(ValueError, match="non_korean"):
        validate_synthesis(response, ["log"])


@pytest.mark.parametrize("family,code", [("xid", 79), ("sxid", 11001)])
def test_structured_guidance_projects_published_original_only(family, code):
    from rcca_agent.operator_guidance import (
        project_guidance,
        validate_operator_guidance,
    )

    book = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / f"rcca-agent/runbooks/{family}/RB-{family.upper()}-{code}.json"
        ).read_text("utf-8")
    )
    content = book["content"]
    validate_operator_guidance(content["operator_guidance"], content["sources"])
    entry = {
        "id": "original",
        "query_id": "runbook",
        "query_version": "next",
        "quality": {"origin": "published"},
        "snapshot": content,
    }
    actual = project_guidance([entry])
    assert actual[0]["guidance"] == content["operator_guidance"]
    actual[0]["guidance"]["meaning"] = "changed"
    assert content["operator_guidance"]["meaning"] != "changed"
    assert project_guidance([{**entry, "quality": {"origin": "builtin"}}]) == []
    bad = copy.deepcopy(content["operator_guidance"])
    bad["references"][0]["source_indices"] = [999]
    with pytest.raises(ValueError, match="operator_guidance"):
        validate_operator_guidance(bad, content["sources"])


@pytest.mark.parametrize(
    "claim",
    [
        "연결된 GPU가 슬롯 접촉 불량으로 분리된 가능성이 있다",
        "NVSwitch 펌웨어 오류 또는 링크 문제로 발생했을 가능성이 있다",
    ],
)
@pytest.mark.parametrize(
    "relation", ["not_in_reported_inventory", "switch_inventory_required"]
)
def test_unmapped_hardware_claim_is_rejected(claim, relation):
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
