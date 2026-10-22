"""Role boundaries, original-source preservation, budgets and failure publication."""

from copy import deepcopy

import pytest

from agent_common.contracts import content_hash
from agent_common.llm import RemoteUncertain
from rcca_agent.report_writer import (
    write_material_report,
    report_sources,
    validate_report,
)
from rcca_agent.synthesis_context import bounded_context, encoded_size
from legacy_review_fixtures import review_payload, analysis_draft
from rcca_agent.evidence_interpretation import ResponseValidationError
from rcca_agent.evaluation import BASE_LIMIT
from rca_report_fixture import report_reply
from rca_replay import replay
from test_rca_combined_policy import policy_case


def material():
    return {
        "evaluation": {
            "analysis_id": "analysis-1",
            "evidence": {
                "execution_status": "complete",
                "interpretation": {
                    "findings": [
                        {
                            "id": "f1",
                            "kind": "observed",
                            "statement": "XID 79 보고를 확인했습니다.",
                            "evidence_refs": ["D09-ref"],
                        }
                    ],
                    "unknowns": [
                        {
                            "statement": "현재 상태는 확인하지 못했습니다.",
                            "evidence_refs": [],
                        }
                    ],
                    "limitations": [
                        {
                            "statement": "단일 출처 보고입니다.",
                            "evidence_refs": ["D09-ref"],
                        }
                    ],
                },
            },
            "review": {"execution_status": "complete", "verdict": "acceptable"},
            "investigation": {"stop_reason": "goal_achieved"},
            "collection": {"query_results": []},
        },
        "cause_candidates": [],
        "recommendations": [],
        "limitations": [BASE_LIMIT, "모델이 작성한 한계 문장입니다."],
        "missing_inputs": [],
        "analysis": {"raw_log": "DO NOT SEND RAW LOGS"},
    }


class Writer:
    configured = True
    remaining = 100000
    reserved_tokens = 0
    request_attempt_limit = 3
    usage = {}

    def __init__(self, failure=None):
        self.failure = failure
        self.inputs = []

    async def complete(self, system, payload, **kwargs):
        assert self.request_attempt_limit == 1
        self.inputs.append(deepcopy(payload))
        self.usage = {"calls": 1, "request_attempts": 1, "total_tokens": 42}
        if self.failure == "remote":
            raise RemoteUncertain("unknown")
        if self.failure == "truncated":
            self.last_failure = "llm_output_truncated"
            return None
        response = report_reply(payload)
        if self.failure == "number":
            response["sections"][0]["text"] += " 99999"
        if self.failure == "refs":
            response["sections"][0]["source_ids"] = ["invented"]
        return response


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "number", "refs", "truncated"])
async def test_writer_only_rephrases_frozen_material_once(failure):
    source = material()
    before = content_hash(source)
    result = {"quality": {}}
    model = Writer(failure)
    await write_material_report(result, source, model)
    assert content_hash(source) == before
    assert len(model.inputs) == 1
    assert "DO NOT SEND RAW LOGS" not in str(model.inputs)
    assert model.request_attempt_limit == 3
    report = result["quality"]["report"]
    assert report["method"] == (
        "llm_composed" if failure is None else "deterministic_fallback"
    )
    assert report["writer"]["usage"]["total_tokens"] == 42
    assert report["material_hash"] == before
    limits = next(r["text"] for r in result["narrative"] if r["id"] == "limits")
    # Model-authored caveats stay in diagnostics; the report keeps fixed ones.
    assert "단일 출처 보고입니다." not in limits
    assert "모델이 작성한 한계 문장입니다." not in limits
    assert BASE_LIMIT in limits
    if failure in {"number", "refs"}:
        assert report["writer"]["validation_details"][0]["details"][0][
            "path"
        ].startswith("$.sections[0]")
        assert "99999" not in str(result["narrative"])


@pytest.mark.asyncio
async def test_report_failure_does_not_retry_unknown_remote_execution():
    model = Writer("remote")
    with pytest.raises(RemoteUncertain):
        await write_material_report({"quality": {}}, material(), model)
    assert len(model.inputs) == 1
    assert model.request_attempt_limit == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["unconfigured", "budget", "input"])
async def test_report_preflight_keeps_complete_sources_and_never_raises_budget(mode):
    model = Writer()
    source = material()
    if mode == "unconfigured":
        model.configured = False
    if mode == "budget":
        model.remaining = 1
    finding = source["evaluation"]["evidence"]["interpretation"]["findings"][0]
    if mode == "input":
        source["cause_candidates"] = [
            {"claim": "관측" * 20000, "supporting_refs": ["D09-ref"]}
        ]
    remaining = model.remaining
    result = {"quality": {}}
    await write_material_report(result, source, model)
    assert not model.inputs
    assert model.remaining == remaining
    assert result["quality"]["report"]["writer"]["execution_status"] == "skipped"
    assert finding["statement"] in str(result["narrative"])
    assert BASE_LIMIT in str(result["narrative"])


def test_report_cannot_drop_sections_or_cross_reference_other_sections():
    sources = report_sources(material())
    payload = {
        "sections": ["problem", "cause"],
        "source_items": [r for r in sources if r["section"] in {"problem", "cause"}],
    }
    response = report_reply(payload)
    response["sections"][0]["source_ids"] = response["sections"][1]["source_ids"]
    with pytest.raises(ResponseValidationError):
        validate_report(response, payload)
    response = report_reply(payload)
    response["sections"].pop()
    with pytest.raises(ResponseValidationError):
        validate_report(response, payload)


def test_inventory_dedup_preserves_each_observation_and_distinct_inventory():
    inventory = [
        {"gpu_uuid": f"GPU-{i}", "bus_id": str(i), "verified": False} for i in range(8)
    ]
    rows = [
        {
            "gpu_candidates": inventory,
            "observed_at": str(i),
            "evidence_refs": [f"ref-{i}"],
        }
        for i in range(4)
    ]
    rows[-1] = {**rows[-1], "gpu_candidates": [{"gpu_uuid": "different"}]}
    payload = {"device_observations": deepcopy(rows)}
    view = bounded_context(payload, 16000)
    assert payload["device_observations"] == rows
    assert len(view["gpu_inventories"]) == 2
    assert len(view["device_observations"]) == 4
    expanded = deepcopy(view)
    tables = expanded.pop("gpu_inventories")
    for row, original in zip(expanded["device_observations"], rows):
        row["gpu_candidates"] = tables[row.pop("gpu_inventory_ref")]
        assert row == original
    assert encoded_size(view) < encoded_size(expanded)
    assert view["observation_refs"] == [f"ref-{i}" for i in range(4)]


def test_review_sends_claim_once_in_both_modes():
    for interpretation in (
        None,
        material()["evaluation"]["evidence"]["interpretation"],
    ):
        draft = analysis_draft([], [], [], {}, interpretation)
        payload = review_payload(draft, {}, [])
        assert (
            not {"cause_candidates", "recommendations", "interpretation"}
            & payload["draft"].keys()
        )
        assert payload["draft"]["analysis_id"] == draft["analysis_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["xid", "sxid"])
async def test_three_roles_and_goal_stop_with_no_ordering_call(kind):
    result = await replay(policy_case(kind))
    assert not result["missing_inputs"]
    assert [row["stage"] for row in result["model_calls"]] == [
        "synthesis",
        "report_writing",
    ]
    output = result["output"]["result"]
    assert (
        output["quality"]["rca_evaluation"]["investigation"]["stop_reason"]
        == "no_available_followup"
    )
    assert output["quality"]["report"]["method"] == "llm_composed"
    assert "runbook_guidance" in output["quality"]
    assembly = result["output"]["evidence"][-1]["snapshot"]
    assert assembly["execution_status"] == "complete"
    assert assembly["attempts"] == 1
    assert assembly["input_material_hash"] == assembly["material_hash"]


def test_report_retains_counter_evidence_and_withheld_action_conditions():
    source = material()
    source["cause_candidates"] = [
        {
            "claim": "점검이 필요한 후보입니다.",
            "supporting_refs": ["support"],
            "contradicting_refs": ["counter"],
        }
    ]
    source["recommendations"] = [
        {
            "text": "점검을 검토하세요.",
            "eligibility": "withheld",
            "preconditions": ["대상 확인"],
            "evidence_refs": ["support"],
        }
    ]
    source["evaluation"]["evidence"]["interpretation"]["unknowns"][0]["reason"] = (
        "현재 시점 자료가 없습니다."
    )
    rows = report_sources(source)
    # Model unknowns are not report prose; coded gaps and fixed text are.
    assert not any("현재 시점 자료가 없습니다." in row["text"] for row in rows)
    assert any(
        "counter" in row["evidence_refs"] and row["section"] == "limits" for row in rows
    )
    assert any(
        "보류된 권고" in row["text"] and "대상 확인" in row["text"] for row in rows
    )


async def test_planned_author_meaning_and_caveats_are_not_rewritten_by_writer():
    source = material()
    source["evaluation"]["review"] = {"reason": "not_requested"}
    source["reported_observations"] = [
        {"text": "기록된 오류", "evidence_refs": ["D09-ref"]}
    ]
    interpretation = source["evaluation"]["evidence"]["interpretation"]
    interpretation["findings"][0]["statement"] = (
        "전력과 사용률의 변화가 오류 보고 구간에 함께 관측됩니다. 인과 관계는 확인되지 않았습니다."
    )
    result = {"quality": {}}
    llm = Writer()
    await write_material_report(result, source, llm)
    items = result["quality"]["report"]["source_items"]
    assert any(
        s["fixed"]
        and s["section"] == "cause"
        and interpretation["findings"][0]["statement"] in s["text"]
        for s in items
    )
    text = str(result["narrative"])
    assert interpretation["findings"][0]["statement"] in text
    assert "단일 출처 보고입니다." in text
    assert not any("전력" in str(i.get("source_items")) for i in llm.inputs)
