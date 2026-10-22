"""Prompt contracts and received-but-rejected combined author responses."""

import json
import re

import pytest

from rcca_agent.combined_synthesis import author_prompt, validate_author
from rca_replay import replay
from rca_replay_cases import reply
from test_rca_combined_policy import policy_case


def test_combined_prompt_has_one_unambiguous_complete_response_contract():
    prompt = author_prompt({})
    examples = [
        json.JSONDecoder().raw_decode(prompt[match.end() :].lstrip())[0]
        for match in re.finditer(
            r"Return (?:JSON with exactly these keys:|exactly)\s*", prompt
        )
    ]
    assert len(examples) == 1, "Conflicting standalone output contracts reached author"
    example = examples[0]
    assert set(example) == {"interpretation", "hypotheses", "limitations"}
    assert set(example["interpretation"]) == {
        "findings",
        "unknowns",
        "conflicts",
        "limitations",
    }
    assert example["hypotheses"] == []
    assert "Hypothesis objects have claim, supporting_refs" in prompt
    _, candidates, _, errors = validate_author(
        example,
        {
            "input_evidence_refs": ["evidence id"],
            "observation_refs": ["evidence id"],
            "device_observations": [],
            "error_events": [],
            "query_quality": [],
        },
        None,
    )
    assert errors == []
    assert candidates == []


@pytest.mark.parametrize(
    "shape", ["analysis_only", "interpretation_only", "extra", "array"]
)
async def test_wrong_author_shape_is_received_but_not_adopted_or_retried(shape):
    case = policy_case()
    author = case["responses"]["synthesis"][0]["response"]
    if shape == "analysis_only":
        response = {k: v for k, v in author.items() if k != "interpretation"}
    elif shape == "interpretation_only":
        response = author["interpretation"]
    elif shape == "extra":
        response = {**author, "private-untrusted-key": "do not persist rejected text"}
    else:
        response = []
    case["responses"]["synthesis"] = [reply(response)]
    result = await replay(case)
    assert not result["missing_inputs"]
    record = next(
        e["snapshot"]
        for e in result["output"]["evidence"]
        if e["query_id"] == "rca_synthesis"
    )
    diagnostic = record["diagnostics"]
    assert diagnostic["request_attempts"] == diagnostic["response_calls"] == 1
    assert diagnostic["error_code"] == "invalid_author_response"
    assert diagnostic["validation_failures"] == [
        {
            "attempt": 1,
            "reasons": ["author_shape"],
            "details": [{"code": "author_shape", "path": "$", "rule": "shape"}],
        }
    ]
    assert diagnostic["adoption"] == "none"
    assert len([c for c in result["model_calls"] if c["stage"] == "synthesis"]) == 1
    assert "private-untrusted-key" not in json.dumps(result["output"])
    assert "do not persist rejected text" not in json.dumps(result["output"])


@pytest.mark.parametrize(
    "failure,code,path",
    [
        ("finding", "finding_dependency", "$.hypotheses[0].finding_refs"),
        ("unhashable", "finding_dependency", "$.hypotheses[0].finding_refs"),
        ("evidence", "invalid_evidence_references", "$.hypotheses[0]"),
        ("language", "invalid_limitations", "$.limitations[0]"),
        ("shape", "invalid_hypothesis_shape", "$.hypotheses[0]"),
    ],
)
async def test_author_preserves_specific_failure_without_rejected_text(
    failure, code, path
):
    case = policy_case()
    response = case["responses"]["synthesis"][0]["response"]
    h = {
        "claim": "추가 확인이 필요한 원인 후보일 가능성이 있다",
        "supporting_refs": {"$input": "/observation_refs"},
        "contradicting_refs": [],
        "missing_inputs": [],
        "finding_refs": ["finding-1"],
    }
    response["hypotheses"] = [h]
    if failure == "finding":
        h["finding_refs"] = ["private-rejected-id"]
    elif failure == "unhashable":
        h["finding_refs"] = [{"private-rejected-id": True}]
    elif failure == "evidence":
        h["supporting_refs"] = ["private-rejected-id"]
    elif failure == "language":
        response["limitations"] = ["private rejected text"]
    else:
        h["private-rejected-id"] = "private rejected text"
    result = await replay(case)
    record = next(
        e["snapshot"]
        for e in result["output"]["evidence"]
        if e["query_id"] == "rca_synthesis"
    )
    diagnostic = record["diagnostics"]
    # Only the offending claim is removed; the rest of the response is adopted.
    assert diagnostic["adoption"] == "validated_response"
    assert record["interpretation"]["findings"]
    # A bad limitation no longer discards the valid hypothesis next to it.
    assert len(record["hypotheses"]) == (1 if failure == "language" else 0)
    assert diagnostic["request_attempts"] == diagnostic["response_calls"] == 1
    assert diagnostic["validation_failures"] == []
    dropped = diagnostic["dropped_items"][0]
    assert (dropped["code"], dropped["path"], dropped["action"]) == (
        code,
        path,
        "dropped",
    )
    assert "private-rejected-id" not in json.dumps(result["output"])
    assert "private rejected text" not in json.dumps(result["output"])


async def test_valid_author_remains_adopted_without_failure_diagnostics():
    case = policy_case()
    result = await replay(case)
    # The accepted case is unchanged by the extra diagnostics.
    record = next(
        e["snapshot"]
        for e in result["output"]["evidence"]
        if e["query_id"] == "rca_synthesis"
    )
    assert record["diagnostics"]["adoption"] == "validated_response"
    assert record["diagnostics"]["validation_failures"] == []


def test_planned_author_explains_collected_data_without_review_or_followup():
    prompt = author_prompt({"incident_comparison": {}})
    assert "Fleet Intelligence has already raised the incident" in prompt
    assert "Grafana MCP metrics and stored host history" in prompt
    assert "Review feedback requests" not in prompt
    assert "If review_feedback is supplied" not in prompt
    assert "controls bounded follow-up" not in prompt
    assert "Explain alert_match/evidence_gap" not in prompt
    assert "Review feedback requests" not in author_prompt({})


@pytest.mark.parametrize("payload", [{}, {"incident_comparison": []}])
def test_every_author_analyzes_collected_sources_after_fleet_decision(payload):
    prompt = author_prompt(payload)
    assert "Fleet Intelligence has already raised the incident" in prompt
    assert "Analysis is required" in prompt
    assert "temporal changes, companion" in prompt
    assert "Use observed findings" in prompt
    assert (
        "merely defining an error and appending Runbook advice is insufficient"
        in prompt
    )
    assert "State unknowns explicitly" not in prompt
    assert "without claiming physical cause" not in prompt
    assert "controls bounded follow-up" not in prompt
    assert "Review feedback requests" not in prompt


def test_cross_source_inferred_analysis_is_accepted_with_real_references():
    response = {
        "interpretation": {
            "findings": [
                {
                    "id": "relationship",
                    "statement": "접근 오류 전후의 연결 오류 기록과 메트릭 변화가 함께 나타나 연결 경로 점검을 우선할 단서가 됩니다.",
                    "kind": "inferred",
                    "evidence_refs": ["log", "metric"],
                }
            ],
            "unknowns": [],
            "conflicts": [],
            "limitations": [],
        },
        "hypotheses": [],
        "limitations": [],
    }
    interpretation, candidates, _, errors = validate_author(
        response,
        {
            "input_evidence_refs": ["log", "metric"],
            "observation_refs": ["log", "metric"],
            "device_observations": [],
            "error_events": [],
            "query_quality": [],
        },
        None,
    )
    assert not errors
    assert interpretation["findings"] == response["interpretation"]["findings"]
    assert candidates == []


def test_supported_candidate_does_not_create_a_causal_confirmation_task():
    from rcca_agent.synthesis import validate_synthesis

    candidates = validate_synthesis(
        {
            "hypotheses": [
                {
                    "claim": "연결 경로의 문제가 동반됐을 가능성이 있다",
                    "supporting_refs": ["log"],
                    "contradicting_refs": [],
                    "missing_inputs": [],
                }
            ],
            "limitations": [],
        },
        ["log"],
        [],
        set(),
        [],
    )
    assert candidates[0]["causal_status"] == "candidate"
    assert candidates[0]["missing_inputs"] == []
