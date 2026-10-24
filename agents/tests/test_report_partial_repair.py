from copy import deepcopy
import json
from unittest.mock import AsyncMock

import pytest
from ops_agent.report_interpretation import (
    interpret_report,
    payload_for,
    validate_sections,
)
from test_namespace_advice import writer_section, topic
from ops_agent.namespace_advice import present_advice


@pytest.fixture
def repair_case():
    usage = topic(pending=2)
    quiet = topic()
    for key in ("rows", "workloads"):
        quiet[key][0]["namespace"] = "quiet"
        usage[key].extend(quiet[key])
    period = usage["workloads"][0]["hours"][0]
    incident = dict(
        topic_id="incident_summary",
        status="ready",
        missing_inputs=[],
        metrics=[
            dict(
                id="incident.count",
                value=3,
                unit="events",
                period={k: period[k] for k in ("start", "end")},
                target={"cluster_id": "cpc-1", "node": "gpu-node"},
                quality={},
            )
        ],
        findings=[
            dict(
                id="incident-node",
                text="저장 알림 기록입니다.",
                target={"cluster_id": "cpc-1", "node": "gpu-node"},
                value_refs=["incident.count"],
                evidence_refs=["incident-evidence"],
            )
        ],
    )
    result = dict(topics=[usage, incident], time_range={}, quality={})
    wire = payload_for(result)
    target = wire["topics"][1]["findings"][0]["fact_id"]
    inc = dict(
        topic_id="incident_summary",
        fact_ids=[target],
        observation="{{target:"
        + target
        + "}}의 {{period:incident.count}} 저장 사건은 {{value:incident.count}}입니다.",
        meaning="저장된 알림이며 현재 장비 상태는 미확인입니다.",
        next_check="{{target:"
        + target
        + "}}의 {{period:incident.count}} 알림과 기존 점검 기록을 대조하세요.",
    )
    valid = {"sections": [writer_section(wire["topics"][0]["findings"]), inc]}
    validate_sections(valid, wire, result)
    return result, valid


@pytest.mark.parametrize("origin", ["schedule", "manual"])
@pytest.mark.parametrize("broken", ["incident", "namespace", "both"])
@pytest.mark.parametrize("incident_first", [False, True])
async def test_partial_repair_preserves_valid_topics_and_namespace_sentences(
    repair_case, origin, broken, incident_first
):
    result, valid = repair_case
    result["report_origin"] = origin
    invalid = deepcopy(valid)
    queue = next(
        a for a in invalid["sections"][0]["advice"] if "스케줄러" in a["summary"]
    )
    patches = {}
    if broken in {"namespace", "both"}:
        queue["summary"] = queue["summary"].replace(
            "대기 Pod의 상태·스케줄러 이벤트를 대조해 노드 배정 전인지 준비 단계인지 확인하세요.",
            "관측된 범위입니다.",
        )
        patches["advice"] = [
            next(
                a
                for a in valid["sections"][0]["advice"]
                if a["fact_id"] == queue["fact_id"]
            )
        ]
    if broken in {"incident", "both"}:
        invalid["sections"][1]["observation"] = "사건은 3건입니다."
        patches["sections"] = [valid["sections"][1]]
    if incident_first:
        result["topics"].reverse()
        invalid["sections"].reverse()
        valid["sections"].reverse()
    original, first = deepcopy(result), deepcopy(invalid)
    expected = validate_sections(valid, payload_for(result), result)
    present_advice(expected)
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [invalid, patches]
    await interpret_report(result, llm)
    request = llm.complete.call_args.args[1]
    assert set(request["response_shape"]) == set(patches)
    assert "topics" not in request
    assert len(request.get("summary_repair", [])) == (broken != "incident")
    assert len(request.get("section_repair", [])) == (broken != "namespace")
    assert result["narrative"] == expected
    assert result["topics"] == original["topics"]
    assert result["report_origin"] == origin
    assert result["quality"]["report"]["reason"] == "repaired"
    assert llm.complete.call_count == 2 and invalid == first


@pytest.mark.parametrize(
    "attack",
    [
        "unsolicited_item",
        "wrong_topic",
        "missing_topic",
        "duplicate_topic",
        "unknown_fact",
        "unsupported_claim",
    ],
)
async def test_mixed_repair_cannot_change_valid_scope_or_skip_final_validation(
    repair_case, attack
):
    result, valid = repair_case
    invalid = deepcopy(valid)
    invalid["sections"][1]["observation"] = "사건은 3건입니다."
    patch = {"sections": [deepcopy(valid["sections"][1])]}
    if attack == "unsolicited_item":
        patch["advice"] = valid["sections"][0]["advice"]
    elif attack == "wrong_topic":
        patch["sections"][0]["topic_id"] = "namespace_usage"
    elif attack == "missing_topic":
        patch["sections"] = []
    elif attack == "duplicate_topic":
        patch["sections"] *= 2
    elif attack == "unknown_fact":
        patch["sections"][0]["fact_ids"] = ["not-offered"]
    else:
        patch["sections"][0]["observation"] = "사건은 7건입니다."
    original = deepcopy(result["topics"])
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [invalid, patch]
    await interpret_report(result, llm)
    assert result["narrative_status"] == "failed"
    assert result["quality"]["report"]["method"] == "deterministic_fallback"
    assert result["topics"] == original and llm.complete.call_count == 2


async def test_oversized_topic_repair_keeps_original_input_limit_and_fallback(
    repair_case,
):
    result, invalid = repair_case
    invalid["sections"][1]["observation"] = "x" * 33_000
    original = deepcopy(result["topics"])
    llm = AsyncMock(configured=True)
    llm.complete.return_value = invalid
    await interpret_report(result, llm)
    assert result["narrative_status"] == "failed"
    assert result["quality"]["report"]["reason"] == "interpretation_input_limit"
    assert result["topics"] == original and llm.complete.call_count == 1


async def test_mixed_repair_above_legacy_limit_preserves_all_context(repair_case):
    result, valid = repair_case
    invalid = deepcopy(valid)
    invalid["sections"][1]["observation"] = "x" * 17_000
    original = deepcopy(result["topics"])
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [invalid, {"sections": [valid["sections"][1]]}]
    await interpret_report(result, llm)
    request = llm.complete.call_args.args[1]
    assert 16_000 < len(json.dumps(request, ensure_ascii=False).encode()) < 32_000
    offered = payload_for(result)["topics"][1]["findings"]
    assert request["section_repair"][0]["topic"]["findings"] == [
        {k: f[k] for k in ("fact_id", "target", "values", "text")} for f in offered
    ]
    example = request["response_shape"]["sections"][0]
    assert "{{target:" in example["observation"]
    assert (
        "{{period:" in example["observation"] and "{{value:" in example["observation"]
    )
    assert result["quality"]["report"]["reason"] == "repaired"
    assert result["topics"] == original and llm.complete.call_count == 2
