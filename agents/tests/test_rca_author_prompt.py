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
    assert example["hypotheses"][0]["finding_refs"] == [
        example["interpretation"]["findings"][0]["id"]
    ]
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
    assert len(candidates) == 1


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
    assert diagnostic["adoption"] == "interpretation_only"
    assert record["interpretation"]["findings"]
    assert record["hypotheses"] == []
    assert diagnostic["request_attempts"] == diagnostic["response_calls"] == 1
    failure = diagnostic["validation_failures"][0]
    assert failure["reasons"] == ["analysis_invalid"]
    assert failure["details"][0]["code"] == code
    assert failure["details"][0]["path"] == path
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
