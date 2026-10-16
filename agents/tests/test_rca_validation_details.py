"""Validation boundaries retain safe field-level causes and accepted output."""

from copy import deepcopy
import json

import pytest

from evaluation_fixtures import interpretation_reply, review_reply
from rca_replay import replay
from rcca_agent.analysis_review import analysis_draft, validate_review
from rcca_agent.combined_synthesis import author_prompt
from rcca_agent.evidence_interpretation import (
    ResponseValidationError,
    call_stage,
    validate_interpretation,
)
from rcca_agent.workflow import choose_followup
from test_rca_combined_policy import policy_case


def valid_interpretation():
    return {
        **interpretation_reply(),
        "findings": [
            dict(
                id="f",
                statement="Observed report",
                kind="observed",
                evidence_refs=["log"],
            )
        ],
    }


@pytest.mark.parametrize(
    "edit,code,path,rule",
    [
        (
            {"unknowns": ["private text"]},
            "interpretation_item",
            "$.unknowns[0]",
            "object_type",
        ),
        (
            {"unknowns": [{"statement": "Unknown", "evidence_refs": []}]},
            "interpretation_missing_support",
            "$.unknowns[0].reason",
            "missing_support",
        ),
        (
            {"conflicts": [{"statement": "Conflict"}]},
            "interpretation_item",
            "$.conflicts[0].evidence_refs",
            "missing_field",
        ),
        (
            {"limitations": [{"statement": "Limit", "evidence_refs": ["private-ref"]}]},
            "interpretation_refs",
            "$.limitations[0].evidence_refs[0]",
            "unknown_reference",
        ),
        (
            {"limitations": [{"statement": "Limit", "evidence_refs": [{}]}]},
            "interpretation_refs",
            "$.limitations[0].evidence_refs[0]",
            "string_type",
        ),
        (
            {
                "findings": [
                    dict(id="f", statement="Report", kind={}, evidence_refs=["log"])
                ]
            },
            "interpretation_kind",
            "$.findings[0].kind",
            "invalid_enum",
        ),
        (
            {"private-field": "private text"},
            "interpretation_shape",
            "$",
            "unexpected_fields",
        ),
    ],
)
def test_interpretation_failure_preserves_fixed_code_and_exact_path(
    edit, code, path, rule
):
    with pytest.raises(ResponseValidationError) as caught:
        validate_interpretation({**valid_interpretation(), **edit}, {"log"})
    assert caught.value.diagnostic == dict(code=code, path=path, rule=rule)
    assert "private" not in json.dumps(caught.value.diagnostic)


@pytest.mark.parametrize(
    "edit,code,path",
    [
        ({"criterion_id": "bounded"}, "criterion_status", ".criterion_id"),
        ({"status": []}, "criterion_status", ".status"),
        ({"finding_refs": ["other"]}, "criterion_finding_refs", ".finding_refs[0]"),
        (
            {"evidence_refs": ["diagnostic"]},
            "criterion_requires_observations",
            ".evidence_refs[0]",
        ),
    ],
)
def test_criterion_ids_and_observation_domain_are_not_relaxed(edit, code, path):
    value = valid_interpretation()
    value["criterion_assessments"] = [
        dict(
            criterion_id="revision:bounded",
            status="satisfied",
            finding_refs=["f"],
            evidence_refs=["log"],
        )
    ]
    value["criterion_assessments"][0].update(edit)
    with pytest.raises(ResponseValidationError) as caught:
        validate_interpretation(
            value, {"log", "diagnostic"}, {"revision:bounded"}, {"log"}
        )
    assert caught.value.diagnostic["code"] == code
    assert caught.value.diagnostic["path"] == "$.criterion_assessments[0]" + path


async def test_prompt_conditions_and_corrected_response_reach_adoption_and_review():
    case = policy_case()
    interpretation = case["responses"]["synthesis"][0]["response"]["interpretation"]
    interpretation["unknowns"] = [dict(statement="Unconfirmed", evidence_refs=[])]
    bad = await replay(deepcopy(case))
    record = next(
        e["snapshot"]
        for e in bad["output"]["evidence"]
        if e["query_id"] == "rca_synthesis"
    )
    details = record["diagnostics"]["validation_failures"][0]["details"]
    assert details[0] == dict(
        code="interpretation_missing_support",
        path="$.interpretation.unknowns[0].reason",
        rule="missing_support",
    )
    assert details[1]["code"] == "interpretation_dependency"
    assert record["diagnostics"]["adoption"] == "none"
    interpretation["unknowns"][0]["reason"] = (
        "No available source establishes current health"
    )
    good = await replay(case)
    record = next(
        e["snapshot"]
        for e in good["output"]["evidence"]
        if e["query_id"] == "rca_synthesis"
    )
    assert record["diagnostics"]["adoption"] == "validated_response"
    assert record["interpretation"]["unknowns"] == interpretation["unknowns"]
    assert record["diagnostics"]["validation_failures"] == []
    ev = good["output"]["result"]["quality"]["rca_evaluation"]
    assert ev["review"]["execution_status"] == "complete"
    assert ev["investigation"]["stop_reason"] == "goal_achieved"
    prompt = author_prompt({"decision_assessment": {"policies": []}})
    assert "ONLY unknowns may cite []" in prompt
    assert "nonempty reason" in prompt
    assert "Copy its full key" in prompt
    assert "NOT short id" in prompt


@pytest.mark.parametrize(
    "change,code,path",
    [
        ("ref", "review_criterion_refs", "$.criteria.grounding.evidence_refs[0]"),
        ("missing", "review_criterion", "$.criteria.grounding.reason"),
        ("verdict", "review_criterion_verdict", "$.verdict"),
        ("query", "review_query", "$.followup_questions[0].query_ids[0]"),
    ],
)
async def test_stage_repair_retains_detail_and_uses_it_without_raw_response(
    change, code, path
):
    draft = analysis_draft([], [], [], {})
    good = review_reply({"draft": draft, "input_evidence_refs": ["log"]}, "acceptable")
    bad = deepcopy(good)
    if change == "ref":
        bad["criteria"]["grounding"]["evidence_refs"] = ["private-ref"]
    elif change == "missing":
        del bad["criteria"]["grounding"]["reason"]
    elif change == "verdict":
        bad["verdict"] = "undetermined"
    else:
        bad["followup_questions"] = [
            dict(question="Check", expected_effect="Clarify", query_ids=["private-ref"])
        ]

    class Model:
        configured = True
        requests = []

        async def complete(self, prompt, payload, **kwargs):
            self.requests.append(payload)
            return bad if len(self.requests) == 1 else good

    model = Model()
    value, diagnostics = await call_stage(
        model,
        "analysis_review",
        "prompt",
        {},
        lambda v: validate_review(v, draft, {"log"}, {"D09"}),
    )
    assert value == good
    assert diagnostics["execution_status"] == "complete"
    assert diagnostics["attempts"] == 2
    detail = diagnostics["validation_details"][0]["details"][0]
    assert detail["code"] == code
    assert detail["path"] == path
    assert model.requests[1]["validation_details"] == [detail]
    assert "private-ref" not in json.dumps(diagnostics)
    assert "private-ref" not in json.dumps(model.requests)


async def test_invalid_json_keeps_its_own_failure_instead_of_shape_failure():
    class Model:
        configured = True
        last_failure = "llm_invalid_output"

        async def complete(self, *args, **kwargs):
            return None

    value, diagnostics = await call_stage(
        Model(),
        "evidence_interpretation",
        "prompt",
        {},
        lambda v: validate_interpretation(v, set()),
    )
    assert value is None
    assert diagnostics["reason"] == "llm_invalid_output"
    assert diagnostics["validation_details"][0]["details"] == [
        dict(code="invalid_json", path="$", rule="json_syntax")
    ]


async def test_selection_records_rejected_item_even_after_successful_repair():
    class Model:
        configured = True
        calls = 0

        async def complete(self, *args, **kwargs):
            self.calls += 1
            return {"query_ids": ["private-ref"] if self.calls == 1 else ["D09"]}

    diagnostics = {}
    assert await choose_followup(Model(), ["D09"], [], diagnostics) == ["D09"]
    detail = diagnostics["validation_details"][0]["details"][0]
    assert detail["path"] == "$.query_ids[0]"
    assert detail["rule"] == "unknown_reference"
    assert "private-ref" not in json.dumps(diagnostics)
