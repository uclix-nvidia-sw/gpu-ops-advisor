"""Malformed topic wrappers may prepare repair, never bypass validation."""

from copy import deepcopy
import json
import time
from unittest.mock import AsyncMock

import httpx
import pytest

from agent_common.artifacts import render
from agent_common.llm import LLM
from agent_common.settings import Settings
from ops_agent.namespace_advice import present_advice
from ops_agent.report_interpretation import (
    interpret_report,
    payload_for,
    validate_sections,
)
from test_namespace_advice import completed_topic
from test_report_interpretation import reply_for, result as report_result


def wrapped_reply(reply):
    return {
        section["topic_id"]: {
            key: deepcopy(value) for key, value in section.items() if key != "topic_id"
        }
        for section in reply["sections"]
    }


@pytest.fixture
def structured_report():
    result = report_result.__wrapped__()
    result["topics"][0] = completed_topic()
    result["topics"].reverse()
    result.update(measurements=[], result_status="complete")
    for topic in result["topics"]:
        for metric in topic["metrics"]:
            metric.setdefault("method", "fixture")
    return result


@pytest.mark.parametrize("origin", ["schedule", "manual"])
@pytest.mark.parametrize("repair_error", [None, "reference", "unknown_fact"])
@pytest.mark.parametrize("include_topic_id", [False, True])
async def test_named_topics_repair_only_invalid_prose(
    structured_report, origin, repair_error, include_topic_id
):
    report = structured_report
    report["report_origin"] = origin
    original = deepcopy(report)
    payload = payload_for(report)
    valid = reply_for(payload)
    invalid = wrapped_reply(valid)
    if include_topic_id:
        for topic_id, section in invalid.items():
            section["topic_id"] = topic_id
    item = invalid["namespace_usage"]["advice"][-1]
    item["summary"] = "{{target}} " + item["summary"]
    untouched = deepcopy(invalid)
    with pytest.raises(ValueError, match="^topic_sections_required:"):
        validate_sections(invalid, payload, report)
    patch = deepcopy(valid["sections"][1]["advice"][-1])
    if repair_error == "reference":
        patch["summary"] = item["summary"]
    elif repair_error == "unknown_fact":
        patch["fact_id"] = "not-a-candidate"
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [invalid, {"advice": [patch]}]

    await interpret_report(report, llm)

    assert llm.complete.await_count == 2
    repair = llm.complete.call_args_list[1].args[1]
    assert "topics" not in repair and "section_repair" not in repair
    assert [i["fact_id"] for i in repair["summary_repair"]] == [item["fact_id"]]
    assert repair["summary_repair"][0]["validation_error"].startswith(
        "namespace_summary_tokens_required:"
    )
    assert repair["response_shape"] == {
        "advice": [{"fact_id": item["fact_id"], "summary": ""}]
    }
    failures = report["quality"]["report"]["failures"]
    assert failures[0] == {"attempt": 1, "reason": "topic_sections_required"}
    assert len(failures) == (2 if repair_error else 1)
    if repair_error:
        assert report["narrative_status"] == "failed"
        assert report["quality"]["report"]["method"] == "deterministic_fallback"
    else:
        expected = validate_sections(valid, payload, original)
        present_advice(expected)
        assert report["narrative"] == expected
        assert report["narrative_status"] == "complete"
    assert invalid == untouched
    for key in ("topics", "time_range", "limitations", "report_origin"):
        assert report[key] == original[key]
    assert render(report)["csv"] == render(original)["csv"]


@pytest.mark.parametrize(
    "problem",
    [
        "unknown_topic",
        "missing_topic",
        "conflicting_topic_id",
        "non_object",
        "duplicate_advice",
        "duplicate_section",
        "section_order",
    ],
)
async def test_ambiguous_wrappers_keep_full_repair(structured_report, problem):
    report = structured_report
    valid = reply_for(payload_for(report))
    invalid = wrapped_reply(valid)
    invalid["namespace_usage"]["advice"][-1]["summary"] = "잘못된 {{target}}"
    if problem == "unknown_topic":
        invalid["extra"] = {}
    elif problem == "missing_topic":
        del invalid["incident_summary"]
    elif problem == "conflicting_topic_id":
        invalid["namespace_usage"]["topic_id"] = "incident_summary"
    elif problem == "non_object":
        invalid["incident_summary"] = []
    elif problem == "duplicate_advice":
        invalid["namespace_usage"]["advice"].append(
            deepcopy(invalid["namespace_usage"]["advice"][0])
        )
    elif problem == "duplicate_section":
        invalid = deepcopy(valid)
        invalid["sections"].append(deepcopy(invalid["sections"][0]))
    elif problem == "section_order":
        invalid = deepcopy(valid)
        invalid["sections"].reverse()
    untouched = deepcopy(invalid)
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [invalid, valid]

    await interpret_report(report, llm)

    assert llm.complete.await_count == 2
    first, second = [call.args[1] for call in llm.complete.call_args_list]
    assert first["topics"] == second["topics"]
    assert "summary_repair" not in second
    assert second["response_shape"] == first["response_shape"]
    assert report["narrative_status"] == "complete"
    assert report["quality"]["report"]["attempts"] == 2
    assert invalid == untouched


async def test_compact_repair_preserves_output_room_without_larger_budget(
    structured_report,
):
    report = structured_report
    incident = report["topics"][0]
    sample = incident["findings"][0]
    incident["findings"] = [
        {
            **deepcopy(sample),
            "id": sample["id"] if i == 0 else f"incident-fixture-{i}",
            "text": "저장된 알림은 관측 범위의 표본이며 원인이나 현재 상태를 확정하지 않습니다. "
            * 10,
        }
        for i in range(6)
    ]
    valid = reply_for(payload_for(report))
    full_llm = AsyncMock(configured=True)
    ambiguous = {**wrapped_reply(valid), "unknown_topic": {}}
    full_llm.complete.side_effect = [ambiguous, valid]
    await interpret_report(deepcopy(report), full_llm)
    full_system, full_request = full_llm.complete.call_args.args
    invalid = wrapped_reply(valid)
    invalid["namespace_usage"]["advice"][-1]["summary"] += " {{target}}"
    partial_llm = AsyncMock(configured=True)
    partial_llm.complete.side_effect = [
        invalid,
        {"advice": [deepcopy(valid["sections"][1]["advice"][-1])]},
    ]
    await interpret_report(report, partial_llm)
    system, request = partial_llm.complete.call_args.args
    settings = Settings(
        kind="report", llm_synthesis_max_tokens=16384, llm_context_tokens=0
    )
    llm = LLM(settings, 0, 65536, lambda state: None)
    full_bound = llm.request_budget(full_system, full_request, "synthesis")[
        "prompt_token_bound"
    ]
    llm.remaining = full_bound + 3436
    assert llm.remaining < 65536
    assert (
        llm.request_budget(full_system, full_request, "synthesis")["output_token_cap"]
        == 3436
    )
    assert llm.request_budget(system, request, "synthesis")["output_token_cap"] >= 8192
    assert len(json.dumps(full_request, ensure_ascii=False).encode()) < 32000
    assert len(json.dumps(request, ensure_ascii=False).encode()) < 32000
    assert report["narrative_status"] == "complete"


async def test_recovered_wrapper_cannot_bypass_exhausted_transport_budget(
    structured_report,
):
    report = structured_report
    original = deepcopy(report["topics"])
    invalid = wrapped_reply(reply_for(payload_for(report)))
    invalid["namespace_usage"]["advice"][-1]["summary"] += " {{target}}"
    http = AsyncMock()
    http.post.return_value = httpx.Response(
        200,
        json={
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": json.dumps(invalid, ensure_ascii=False)},
                }
            ],
            "usage": {"total_tokens": 65000},
        },
    )
    llm = LLM(
        Settings(
            kind="report",
            llm_base_url="https://example.invalid/v1",
            llm_model="fixture",
            llm_api_key="fixture",
            llm_synthesis_max_tokens=16384,
            llm_context_tokens=0,
        ),
        time.monotonic() + 30,
        65536,
        lambda state: None,
        http=http,
    )

    await interpret_report(report, llm)

    assert http.post.await_count == 1
    assert llm.remaining == 536
    assert report["narrative_status"] == "failed"
    assert report["quality"]["report"]["failures"] == [
        {"attempt": 1, "reason": "topic_sections_required"},
        {"attempt": 2, "reason": "llm_token_budget_exhausted"},
    ]
    assert report["topics"] == original


@pytest.mark.parametrize("origin", ["schedule", "manual"])
@pytest.mark.parametrize("structure", ["named_topics", "empty_heading"])
async def test_format_only_repair_preserves_valid_prose_without_another_model_call(
    structured_report, origin, structure
):
    report = structured_report
    report["report_origin"] = origin
    original = deepcopy(report)
    payload = payload_for(report)
    valid = reply_for(payload)
    invalid = wrapped_reply(valid) if structure == "named_topics" else deepcopy(valid)
    if structure == "empty_heading":
        invalid["sections"].append({"topic_id": "namespace_usage", "advice": []})
    before = deepcopy(invalid)
    llm = AsyncMock(configured=True)
    llm.complete.return_value = invalid
    await interpret_report(report, llm)
    expected = validate_sections(valid, payload, original)
    present_advice(expected)
    assert report["narrative"] == expected
    assert report["quality"]["report"]["attempts"] == 1
    assert report["quality"]["report"]["reason"] == "repaired"
    assert report["quality"]["report"]["failures"] == [
        {"attempt": 1, "reason": "topic_sections_required"}
    ]
    assert llm.complete.await_count == 1 and invalid == before
    assert report["topics"] == original["topics"]
    assert render(report)["csv"] == render(original)["csv"]


@pytest.mark.parametrize("repeat_bad", [False, True])
async def test_empty_heading_repairs_only_invalid_item_and_keeps_valid_length(
    structured_report, repeat_bad
):
    report = structured_report
    original = deepcopy(report)
    valid = reply_for(payload_for(report))
    invalid = deepcopy(valid)
    bad = invalid["sections"][1]["advice"][-1]
    bad["summary"] += " {{target}}"
    invalid["sections"].append({"topic_id": "namespace_usage", "advice": []})
    before = deepcopy(invalid)
    fixed = deepcopy(valid["sections"][1]["advice"][-1])
    if repeat_bad:
        fixed = deepcopy(bad)
    llm = AsyncMock(configured=True)
    llm.complete.side_effect = [invalid, {"advice": [fixed]}]
    await interpret_report(report, llm)
    request = llm.complete.call_args_list[1].args[1]
    assert [a["fact_id"] for a in request["summary_repair"]] == [bad["fact_id"]]
    assert "topics" not in request and "section_repair" not in request
    assert report["narrative_status"] == ("failed" if repeat_bad else "complete")
    assert llm.complete.await_count == 2 and invalid == before
    if not repeat_bad:
        expected = validate_sections(valid, payload_for(original), original)
        present_advice(expected)
        assert report["narrative"] == expected
    assert report["topics"] == original["topics"]
    assert render(report)["csv"] == render(original)["csv"]
