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
    # The unsupported unknown is dropped with its exact rule; the rest is adopted.
    assert record["diagnostics"]["dropped_items"][0] == dict(
        code="interpretation_missing_support",
        path="$.interpretation.unknowns[0].reason",
        rule="missing_support",
        action="dropped",
    )
    assert record["diagnostics"]["validation_failures"] == []
    assert record["diagnostics"]["adoption"] == "validated_response"
    assert record["interpretation"]["unknowns"] == []
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


def synthesis_record(result):
    return next(
        e["snapshot"]
        for e in result["output"]["evidence"]
        if e["query_id"] == "rca_synthesis"
    )


@pytest.mark.parametrize(
    "field,item,code",
    [
        # 2026-10-16 12:54 SXID 11001 (e04ce3ee): unknowns[0] unexpected_fields.
        (
            "unknowns",
            dict(
                statement="확인되지 않음", evidence_refs=[], reason="원천 없음", id="u"
            ),
            "interpretation_item",
        ),
        # 2026-10-16 12:49 XID 79 (8151e6fa): limitations[1] missing_support.
        (
            "limitations",
            dict(statement="근거가 연결되지 않은 한계", evidence_refs=[]),
            "interpretation_missing_support",
        ),
    ],
)
async def test_production_item_error_drops_only_that_item(field, item, code):
    case = policy_case()
    interpretation = case["responses"]["synthesis"][0]["response"]["interpretation"]
    interpretation[field] = interpretation[field] + [item]
    result = await replay(case)
    record = synthesis_record(result)
    diagnostics = record["diagnostics"]
    assert diagnostics["adoption"] == "validated_response"
    assert [d["code"] for d in diagnostics["dropped_items"]] == [code]
    assert record["interpretation"]["findings"]
    assert item not in record["interpretation"][field]
    evaluation = result["output"]["result"]["quality"]["rca_evaluation"]
    # Before salvage the whole author response was rejected and the goal unmet.
    assert evaluation["investigation"]["stop_reason"] == "goal_achieved"


async def test_invalid_criterion_answer_is_unknown_not_whole_rejection():
    case = policy_case()
    interpretation = case["responses"]["synthesis"][0]["response"]["interpretation"]
    interpretation["criterion_assessments"][0]["criterion_id"] = "bounded_conclusion"
    result = await replay(case)
    record = synthesis_record(result)
    assert record["diagnostics"]["adoption"] == "validated_response"
    assert record["diagnostics"]["dropped_items"][0]["code"] == "criterion_status"
    assert {r["status"] for r in record["interpretation"]["criterion_assessments"]} == {
        "unknown"
    }
    evaluation = result["output"]["result"]["quality"]["rca_evaluation"]
    # A malformed semantic answer must never complete the Runbook objective.
    assert evaluation["investigation"]["stop_reason"] != "goal_achieved"


async def test_author_view_uses_planned_budget_and_admits_observations_first():
    from rcca_agent.combined_synthesis import generate
    from rcca_agent.synthesis_context import SECTIONS, bounded_context

    class Model:
        configured, remaining, reserved_tokens, usage = True, 131072, 0, {}

        async def complete(self, prompt, view, stage):
            return None

    rows = [
        dict(evidence_refs=[f"m{i}"], labels={"i": str(i)}, samples=[["t", "1"]] * 8)
        for i in range(60)
    ]
    payload = {k: [] for k in SECTIONS} | {"metric_observations": rows}
    diagnostics = {}
    await generate(Model(), payload, diagnostics)
    # The former fixed 6,000-byte cap dropped every auxiliary source in production.
    assert diagnostics["input_bytes"] > 6000
    checks = [dict(check="json_object", evidence_refs=["log"], outcome="pass")] * 40
    small = bounded_context(
        {k: [] for k in SECTIONS}
        | {"evidence_checks": checks, "metric_observations": rows[:1]},
        1500,
    )
    assert small["metric_observations"], "passed checks must not crowd out metrics"


def test_reported_gpu_series_precede_siblings_in_author_input():
    # 2026-10-15 16:48: the 6KB view held GPU 0's power, not the XID GPU's.
    from rcca_agent.synthesis import synthesis_input

    evidence = [
        dict(
            id="m",
            query_id="D11",
            tool_status="ok",
            cluster_id="c",
            quality=dict(complete=True, original_samples=True),
            snapshot={
                "data": {
                    "result": [
                        {"metric": {"node": "n", "UUID": u}, "values": [[1, "60"]]}
                        for u in ("GPU-other", "GPU-reported")
                    ]
                }
            },
        )
    ]
    events = [dict(evidence_refs=["m"], inventory_gpu_candidate="GPU-reported")]
    data = dict(incident_time="t", scope={}, target={"node": "n"})
    payload = synthesis_input(data, evidence, [], [], [], events=events)
    assert payload["metric_observations"][0]["labels"]["UUID"] == "GPU-reported"


async def test_report_does_not_call_fallback_review_a_valid_analysis():
    case = policy_case()
    response = case["responses"]["synthesis"][0]["response"]
    case["responses"]["synthesis"][0]["response"] = response["interpretation"]
    result = await replay(case)
    text = json.dumps(result["output"]["result"]["narrative"], ensure_ascii=False)
    assert "LLM 작성 결과 미채택" in text
    assert "분석 품질: 확보된 근거 범위에서 타당" not in text
    assert "의미 미확인(review_accepted)" not in text
