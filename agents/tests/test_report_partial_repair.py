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
    from test_aggregate_report import concentration_report

    incident = concentration_report()["topics"][0]
    result = dict(topics=[usage, incident], time_range={}, quality={})
    wire = payload_for(result)
    from test_report_interpretation import concentration_reply

    inc = concentration_reply(wire)["sections"][1]
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
        a
        for a in invalid["sections"][0]["advice"]
        if a["fact_id"]
        == next(
            f["fact_id"]
            for t in payload_for(result)["topics"]
            for f in t["findings"]
            if f.get("kind") == "queue_review"
        )
    )
    patches = {}
    if broken in {"namespace", "both"}:
        queue["summary"] = "Pod의 GPU 활동률이 낮았습니다."
        patches["advice"] = [
            next(
                a
                for a in valid["sections"][0]["advice"]
                if a["fact_id"] == queue["fact_id"]
            )
        ]
    if broken in {"incident", "both"}:
        invalid["sections"][1]["meaning"] = "사건은 3건입니다."
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
    instruction = request["instruction"]
    assert "INCIDENT_RULES" not in instruction
    for call in llm.complete.call_args_list:
        for text in (call.args[0], call.args[1].get("instruction", "")):
            assert not any(
                name in text
                for name in ("INCIDENT_RULES", "INCIDENT_EXAMPLE", "ADVICE_SYSTEM")
            )
    if broken != "namespace":
        assert "incident_summary 작성:" in llm.complete.call_args.args[0]
        assert "validation_error가 지적한 부분을 고쳐" in instruction
        assert "지적되지 않은 정상 내용은 유지" in instruction
    assert ("summary_repair의 Namespace summary" in instruction) == (
        broken != "incident"
    )
    assert ("prose_max_chars" in instruction) == (broken != "incident")
    assert ("system의 incident_summary 작성 규칙" in instruction) == (
        broken != "namespace"
    )
    assert ("focus.check_context" in instruction) == (broken != "namespace")
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
        "unknown_value",
        "unsupported_claim",
    ],
)
async def test_mixed_repair_cannot_change_valid_scope_or_skip_final_validation(
    repair_case, attack
):
    result, valid = repair_case
    invalid = deepcopy(valid)
    invalid["sections"][1]["meaning"] = "사건은 3건입니다."
    patch = {"sections": [deepcopy(valid["sections"][1])]}
    if attack == "unsolicited_item":
        patch["advice"] = valid["sections"][0]["advice"]
    elif attack == "wrong_topic":
        patch["sections"][0]["topic_id"] = "namespace_usage"
    elif attack == "missing_topic":
        patch["sections"] = []
    elif attack == "duplicate_topic":
        patch["sections"] *= 2
    elif attack == "unknown_value":
        patch["sections"][0]["meaning"] = "종류와 노드는 {{value:not-offered}}입니다."
    else:
        patch["sections"][0]["meaning"] = "종류와 노드는 7건입니다."
    original = deepcopy(result["topics"])
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [invalid, patch]
    await interpret_report(result, llm)
    assert result["narrative_status"] == "failed"
    assert result["quality"]["report"]["method"] == "partial_interpretation"
    expected = validate_sections(valid, payload_for(result), result)
    present_advice(expected)
    assert result["narrative"][0] == expected[0]
    assert result["narrative"][1]["interpretation_source"] == "deterministic_fallback"
    assert "meaning" not in result["narrative"][1]
    assert result["topics"] == original and llm.complete.call_count == 2


async def test_oversized_topic_repair_keeps_original_input_limit_and_fallback(
    repair_case,
):
    result, invalid = repair_case
    invalid["sections"][1]["meaning"] = "x" * 33_000
    original = deepcopy(result["topics"])
    llm = AsyncMock(configured=True)
    llm.complete.return_value = invalid
    await interpret_report(result, llm)
    assert result["narrative_status"] == "failed"
    assert result["quality"]["report"]["reason"] == "interpretation_input_limit"
    assert result["quality"]["report"]["method"] == "partial_interpretation"
    assert result["quality"]["report"]["topic_statuses"] == {
        "namespace_usage": "complete",
        "incident_summary": "failed",
    }
    assert result["topics"] == original and llm.complete.call_count == 1


async def test_mixed_repair_above_legacy_limit_preserves_all_context(repair_case):
    result, valid = repair_case
    invalid = deepcopy(valid)
    invalid["sections"][1]["meaning"] = "x" * 17_000
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
    from ops_agent.report_interpretation import INCIDENT_EXAMPLE

    assert {key: example[key] for key in INCIDENT_EXAMPLE} == dict.fromkeys(
        INCIDENT_EXAMPLE, ""
    )
    assert result["quality"]["report"]["reason"] == "repaired"
    assert result["topics"] == original and llm.complete.call_count == 2
