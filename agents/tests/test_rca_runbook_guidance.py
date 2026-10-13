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
            "원본 오류 로그",
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
