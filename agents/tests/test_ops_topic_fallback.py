"""Keep independently validated topics without admitting malformed model output."""

from copy import deepcopy
import json
from unittest.mock import AsyncMock

import pytest

from ops_agent.namespace_advice import present_advice
from ops_agent.report_interpretation import (
    interpret_report,
    payload_for,
    validate_sections,
)
from test_report_interpretation import result as base_result, reply_for


@pytest.fixture
def result():
    return base_result.__wrapped__()


@pytest.mark.parametrize("failed_topic", ["namespace_usage", "incident_summary"])
@pytest.mark.parametrize("advice_mode", [False, True])
async def test_failed_topic_preserves_other_ai_and_uses_calculated_fallback(
    result, failed_topic, advice_mode
):
    if advice_mode:
        from test_namespace_advice import topic

        result["topics"][0] = topic()
    before = deepcopy(result["topics"])
    payload = payload_for(result)
    valid = reply_for(payload)
    expected = validate_sections(valid, payload, result)
    present_advice(expected)
    invalid = deepcopy(valid)
    broken = next(s for s in invalid["sections"] if s["topic_id"] == failed_topic)
    if failed_topic == "namespace_usage" and advice_mode:
        broken["advice"][0]["summary"] = ""
        patch = {"advice": [{"fact_id": broken["advice"][0]["fact_id"], "summary": ""}]}
    else:
        broken["meaning"] = "XID 79가 기록됐습니다."
        patch = {"sections": [deepcopy(broken)]} if advice_mode else deepcopy(invalid)
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [invalid, patch]

    await interpret_report(result, llm)

    assert llm.complete.call_count == 2
    assert result["narrative_status"] == "failed"
    diagnostic = result["quality"]["report"]
    assert diagnostic["method"] == "partial_interpretation"
    assert diagnostic["topic_statuses"][failed_topic] == "failed"
    success = next(s for s in expected if s["topic_id"] != failed_topic)
    assert diagnostic["topic_statuses"][success["topic_id"]] == "complete"
    assert (
        next(s for s in result["narrative"] if s["topic_id"] == success["topic_id"])
        == success
    )
    fallback = next(s for s in result["narrative"] if s["topic_id"] == failed_topic)
    assert fallback["interpretation_source"] == "deterministic_fallback"
    assert "meaning" not in fallback and "advice" not in fallback
    source = next(t for t in before if t["topic_id"] == failed_topic)
    assert fallback["text"] == "\n\n".join(f["text"] for f in source["findings"][:3])
    assert result["topics"] == before


@pytest.mark.parametrize("second_reply", [None, {"sections": None}, {"sections": []}])
async def test_bad_repair_or_transport_keeps_first_valid_topic(result, second_reply):
    from test_namespace_advice import topic

    result["topics"][0] = topic()
    payload = payload_for(result)
    first = reply_for(payload)
    incident = next(s for s in first["sections"] if s["topic_id"] == "incident_summary")
    incident["meaning"] = "XID 79가 기록됐습니다."
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [first, second_reply]
    await interpret_report(result, llm)
    assert result["quality"]["report"]["topic_statuses"] == {
        "namespace_usage": "complete",
        "incident_summary": "failed",
    }
    assert next(n for n in result["narrative"] if n["topic_id"] == "namespace_usage")[
        "advice"
    ]


@pytest.mark.parametrize("problem", ["missing", "duplicate", "wrong_order"])
async def test_ambiguous_response_does_not_establish_valid_topics(result, problem):
    payload = payload_for(result)
    reply = reply_for(payload)
    if problem == "missing":
        reply["sections"].pop()
    elif problem == "duplicate":
        reply["sections"][1] = deepcopy(reply["sections"][0])
    else:
        reply["sections"].reverse()
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [deepcopy(reply), deepcopy(reply)]
    await interpret_report(result, llm)
    assert result["quality"]["report"]["method"] == "deterministic_fallback"
    assert "topic_statuses" not in result["quality"]["report"]


async def test_all_topics_invalid_remain_full_calculated_fallback(result):
    payload = payload_for(result)
    bad = reply_for(payload)
    for section in bad["sections"]:
        section["meaning"] = "XID 79가 기록됐습니다."
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [deepcopy(bad), deepcopy(bad)]
    await interpret_report(result, llm)
    assert result["narrative_status"] == "failed"
    assert result["quality"]["report"]["method"] == "deterministic_fallback"
    assert all(n["title"] == "계산 결과 요약" for n in result["narrative"])


@pytest.mark.parametrize("topic_id", ["namespace_usage", "incident_summary"])
@pytest.mark.parametrize("field", ["meaning", "next_check"])
@pytest.mark.parametrize(
    "text,kind",
    [
        ("XID 79가 기록됐습니다.", "number"),
        ("비밀은 <private-secret>입니다.", "symbol"),
        ("private-secret 원인입니다.", "forbidden_expression"),
        ("private-secret", "missing_korean"),
    ],
)
async def test_prose_diagnostics_store_only_fixed_provenance_codes(
    result, caplog, topic_id, field, text, kind
):
    payload = payload_for(result)
    bad = reply_for(payload)
    section = next(s for s in bad["sections"] if s["topic_id"] == topic_id)
    section[field] = text
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [deepcopy(bad), deepcopy(bad)]
    await interpret_report(result, llm)
    failures = result["quality"]["report"]["failures"]
    assert failures == [
        {
            "attempt": attempt,
            "reason": "unsupported_prose",
            "topic_id": topic_id,
            "field": field,
            "violation_kind": kind,
            "topic_failures": [{"topic_id": topic_id, "reason": "unsupported_prose"}],
        }
        for attempt in (1, 2)
    ]
    assert "private-secret" not in json.dumps(result["quality"]) + caplog.text
    assert text not in caplog.text
    assert f"topic={topic_id} field={field} violation={kind}" in caplog.text


async def test_full_repair_cannot_replace_first_valid_topic_prose(result):
    payload = payload_for(result)
    valid = reply_for(payload)
    first = deepcopy(valid)
    first["sections"][0]["meaning"] = "먼저 검증을 통과한 설명입니다."
    first["sections"][1]["meaning"] = "사건은 3건입니다."
    second = deepcopy(valid)
    second["sections"][0]["meaning"] = "보완 응답에서 다시 작성한 설명입니다."
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [first, second]
    await interpret_report(result, llm)
    assert result["narrative_status"] == "complete"
    assert result["narrative"][0]["meaning"] == "먼저 검증을 통과한 설명입니다."
    assert result["quality"]["report"]["method"] == "llm_interpreted"


@pytest.mark.parametrize("advice_mode", [False, True])
async def test_all_topics_validated_across_attempts_are_complete(result, advice_mode):
    if advice_mode:
        from test_namespace_advice import topic

        result["topics"][0] = topic()
    payload = payload_for(result)
    valid = reply_for(payload)
    expected = validate_sections(valid, payload, result)
    present_advice(expected)
    first = deepcopy(valid)
    first["sections"][1]["meaning"] = "사건은 3건입니다."
    second = deepcopy(valid)
    if advice_mode:
        # Partial repair must not return the already valid Namespace section.
        second = {"sections": [second["sections"][1]]}
    else:
        second["sections"][0]["meaning"] = "직접 쓴 숫자는 7입니다."
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [first, second]

    await interpret_report(result, llm)

    assert llm.complete.call_count == 2
    assert result["narrative"] == expected
    assert [n["topic_id"] for n in result["narrative"]] == [
        t["topic_id"] for t in payload["topics"]
    ]
    assert result["narrative_status"] == "complete"
    diagnostic = result["quality"]["report"]
    assert diagnostic["method"] == "llm_interpreted"
    assert diagnostic["reason"] == "repaired"
    assert "topic_statuses" not in diagnostic
    if advice_mode:
        from ops_agent.namespace_advice import VERSION

        assert diagnostic["namespace_advice_version"] == VERSION


async def test_advice_full_retry_collects_all_topics_as_complete(result):
    from test_namespace_advice import topic
    from ops_agent.namespace_advice import VERSION

    result["topics"][0] = topic()
    payload = payload_for(result)
    valid = reply_for(payload)
    expected = validate_sections(valid, payload, result)
    present_advice(expected)
    first = deepcopy(valid)
    # An invalid advice list requires full retry, preserving the valid incident.
    first["sections"][0]["advice"] = []
    second = deepcopy(valid)
    second["sections"][1]["meaning"] = "사건은 3건입니다."
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [first, second]

    await interpret_report(result, llm)

    assert "topics" in llm.complete.call_args_list[1].args[1]
    assert result["narrative"] == expected
    assert result["narrative_status"] == "complete"
    diagnostic = result["quality"]["report"]
    assert diagnostic["method"] == "llm_interpreted"
    assert diagnostic["reason"] == "repaired"
    assert diagnostic["namespace_advice_version"] == VERSION
    assert "topic_statuses" not in diagnostic


@pytest.mark.parametrize("field", ["meaning", "next_check"])
@pytest.mark.parametrize("namespace_initially_failed", [False, True])
async def test_repeated_echo_records_every_failed_topic_and_preserves_namespace(
    result, field, namespace_initially_failed
):
    from ops_agent.report_interpretation import INCIDENT_EXAMPLE
    from test_namespace_advice import topic

    result["topics"][0] = topic()
    result["topics"].reverse()
    payload = payload_for(result)
    valid = reply_for(payload)
    expected = validate_sections(valid, payload, result)
    present_advice(expected)
    first = deepcopy(valid)
    first["sections"][0][field] = INCIDENT_EXAMPLE[field]
    second = {"sections": [deepcopy(first["sections"][0])]}
    if namespace_initially_failed:
        first["sections"][1]["advice"][0]["summary"] = ""
        second["advice"] = [deepcopy(valid["sections"][1]["advice"][0])]
    original = deepcopy(result["topics"])
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [first, second]
    await interpret_report(result, llm)
    diagnostic = result["quality"]["report"]
    failures = diagnostic["failures"]
    incident_failure = {"topic_id": "incident_summary", "reason": "template_echo"}
    assert [f["reason"] for f in failures] == ["template_echo", "template_echo"]
    assert failures[0]["topic_failures"][0] == incident_failure
    assert len(failures[0]["topic_failures"]) == (
        2 if namespace_initially_failed else 1
    )
    if namespace_initially_failed:
        assert failures[0]["topic_failures"][1] == {
            "topic_id": "namespace_usage",
            "reason": "invalid_namespace_advice_text",
        }
    assert failures[1]["topic_failures"] == [incident_failure]
    assert diagnostic["method"] == "partial_interpretation"
    assert diagnostic["topic_statuses"] == {
        "incident_summary": "failed",
        "namespace_usage": "complete",
    }
    assert result["narrative"][1] == expected[1]
    assert result["narrative"][0]["interpretation_source"] == "deterministic_fallback"
    assert result["topics"] == original and llm.complete.call_count == 2
    assert not any(
        value in json.dumps(diagnostic, ensure_ascii=False)
        for value in INCIDENT_EXAMPLE.values()
        if value
    )


@pytest.mark.parametrize("field", ["meaning", "next_check"])
@pytest.mark.parametrize("value", ["", " "])
def test_empty_incident_writer_fields_are_rejected(result, field, value):
    payload = payload_for(result)
    reply = reply_for(payload)
    reply["sections"][1][field] = value
    with pytest.raises(ValueError, match="^invalid_section_text$"):
        validate_sections(reply, payload, result)


def test_topic_failure_codes_exclude_raw_exception_text(result, monkeypatch):
    import ops_agent.report_interpretation as module

    payload = payload_for(result)
    reply = reply_for(payload)

    def fail(*args):
        raise ValueError("private-secret/token=abc")

    monkeypatch.setattr(module, "_validate_sections", fail)
    with pytest.raises(ValueError) as caught:
        validate_sections(reply, payload, result)
    assert caught.value.topic_failures == [
        {"topic_id": topic["topic_id"], "reason": "model_response_unavailable"}
        for topic in payload["topics"]
    ]
