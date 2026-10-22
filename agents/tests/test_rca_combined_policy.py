"""Two-stage author/reviewer and Runbook goal completion with original scope checks."""

from copy import deepcopy
import json

import pytest

from agent_common.contracts import content_hash
from rcca_agent.runbook_contract import validate_runbook
from rca_replay import replay
from rca_replay_cases import ROOT, cases, reply


def policy_case(kind="xid"):
    case = cases()["enough_budget"]
    case["id"] = "combined_" + kind
    case["empty_unscripted_queries"] = True
    code, key = ("79", "RB-XID-79") if kind == "xid" else ("11001", "RB-SXID-11001")
    profile = case["attempt"]["profile"]
    profile["rca"]["generation_mode"] = "combined"
    profile["health_contracts"] = json.loads(
        (ROOT / "agents/tests/fixtures/config-v7.json").read_text()
    )["health_contracts"]
    profile["queries"]["D44"] = {
        "source": "mimir",
        "metric": "fixture_replay",
        "unit": "count",
        "max_hold_seconds": 30,
        "revision": "fixture-v1",
        "validated": True,
    }
    data = case["attempt"]["claim"]["input"]
    data["target"] = {"node": "node-1"}
    data["incident_snapshot"] = {
        "alert": {"labels": {"reason": kind.upper() + " " + code}}
    }
    raw = {
        "attributes": {
            "component": "accelerator-nvidia-error-" + kind,
            "health": "Unhealthy",
            "log_type": "component_data",
            "reason": kind.upper() + " " + code,
        },
        "resources": {"machine.id": "machine-1", "k8s.node.name": "node-1"},
    }
    case["queries"][0]["arguments"]["logql"] = '{node="node-1"}'
    case["queries"][0]["response"]["data"]["result"][0]["values"][0][1] = json.dumps(
        raw
    )
    book = case["attempt"]["context"]["runbooks"][0]
    book.update(
        knowledge_key=key,
        content=json.loads(
            (ROOT / f"agents/tests/fixtures/{key}-published-legacy.json").read_text(
                encoding="utf-8"
            )
        )["content"],
    )
    book.update(
        content_hash=content_hash(book["content"]),
        reviewed_content_hash=content_hash(book["content"]),
    )
    author = {
        "interpretation": {
            "findings": [
                {
                    "id": "finding-1",
                    "statement": "대상 노드의 오류 보고를 확인했습니다. 근본 원인과 현재 상태는 미확정입니다.",
                    "kind": "observed",
                    "evidence_refs": {"$input": "/observation_refs"},
                }
            ],
            "unknowns": [],
            "conflicts": [],
            "limitations": [],
        },
        "hypotheses": [],
        "limitations": ["원인과 현재 상태는 별도 확인이 필요합니다."],
    }
    case["responses"].pop("evidence_interpretation")
    case["responses"]["synthesis"] = [reply(author)] * 2
    return case


@pytest.mark.parametrize("kind", ["xid", "sxid"])
async def test_new_policy_revision_is_selected_while_old_published_revision_remains(
    kind,
):
    case = policy_case(kind)
    current = case["attempt"]["context"]["runbooks"][0]
    old = deepcopy(current)
    old["id"] = "old-published-revision"
    old["content"].pop("decision_policy")
    old["content"]["schema"] = "gpu-rca-runbook/1.0"
    old["content_hash"] = old["reviewed_content_hash"] = content_hash(old["content"])
    current["revision"] = old["revision"] + 1
    case["attempt"]["context"]["runbooks"].insert(0, old)
    result = await replay(case)
    assert not result["missing_inputs"]
    evaluation = result["output"]["result"]["quality"]["rca_evaluation"]
    assert evaluation["investigation"]["stop_reason"] == "no_available_followup"
    assert sum(c["matched"] for c in result["query_calls"]) == 1
    assert [b["id"] for b in result["output"]["result"]["runbook_revisions"]] == [
        current["id"]
    ]
    assert "objective" not in evaluation["investigation"]


@pytest.mark.parametrize("kind", ["xid", "sxid"])
async def test_published_legacy_policy_is_not_silently_upgraded(kind):
    case = policy_case(kind)
    book = case["attempt"]["context"]["runbooks"][0]
    book["content"].pop("decision_policy")
    book["content"]["schema"] = "gpu-rca-runbook/1.0"
    book["content_hash"] = book["reviewed_content_hash"] = content_hash(book["content"])
    for response in case["responses"]["synthesis"]:
        response["response"]["interpretation"].pop("criterion_assessments", None)
    result = await replay(case)
    assert not any(
        e["query_id"] == "analysis_review" for e in result["output"]["evidence"]
    )
    frozen = next(
        e["snapshot"]
        for e in result["output"]["evidence"]
        if e["query_id"] == "runbook"
    )
    assert frozen == book["content"]
    assert "decision_policy" not in frozen
    assert result["output"]["result"]["quality"]["analysis"]["followups"] == 0


async def test_valid_interpretation_survives_invalid_causal_refs_and_is_reviewed():
    case = policy_case()
    case["responses"]["synthesis"][0]["response"]["hypotheses"] = [
        {
            "claim": "관측한 증상은 추가 확인이 필요합니다.",
            "supporting_refs": ["invented"],
            "contradicting_refs": [],
            "finding_refs": ["finding-1"],
            "missing_inputs": [],
        }
    ]
    result = await replay(case)
    ev = result["output"]["result"]["quality"]["rca_evaluation"]
    record = next(
        e["snapshot"]
        for e in result["output"]["evidence"]
        if e["query_id"] == "rca_synthesis"
    )
    # The invented-ref hypothesis is removed; the valid remainder is adopted.
    assert record["diagnostics"]["adoption"] == "validated_response"
    assert record["hypotheses"] == []
    assert [d["code"] for d in record["diagnostics"]["dropped_items"]] == [
        "invalid_evidence_references"
    ]
    assert ev["evidence"]["interpretation"]["findings"]
    assert ev["review"]["reason"] == "not_requested"
    assert len([c for c in result["model_calls"] if c["stage"] == "synthesis"]) == 1


@pytest.mark.parametrize("kind", ["xid", "sxid"])
async def test_scope_mismatch_blocks_goal_even_with_forged_model_satisfaction(kind):
    case = policy_case(kind)
    query = case["queries"][0]
    raw = json.loads(query["response"]["data"]["result"][0]["values"][0][1])
    raw["resources"]["k8s.node.name"] = "other-node"
    query["response"]["data"]["result"][0]["values"][0][1] = json.dumps(raw)
    result = await replay(case)
    assert (
        result["output"]["result"]["quality"]["rca_evaluation"]["investigation"][
            "stop_reason"
        ]
        != "goal_achieved"
    )


@pytest.mark.parametrize(
    "mutation",
    ["legacy", "unknown_query", "required_query", "blocker", "code_criteria"],
)
def test_runbook_policy_rejects_unsafe_contract(mutation):
    case = policy_case()
    book = deepcopy(case["attempt"]["context"]["runbooks"][0])
    content = book["content"]
    policy = content["decision_policy"]
    if mutation == "legacy":
        content["schema"] = "gpu-rca-runbook/1.0"
    if mutation == "unknown_query":
        policy["followup_links"][0]["query_id"] = "D999"
    if mutation == "required_query":
        policy["followup_links"][0]["required"] = False
    if mutation == "blocker":
        policy["blocking_conditions"].pop()
    if mutation == "code_criteria":
        policy["completion_criteria"][0]["required"] = False
    with pytest.raises(ValueError):
        validate_runbook(
            book,
            case["attempt"]["profile"]["queries"],
            list(case["attempt"]["profile"]["queries"]),
        )


def test_source_identity_ignores_record_uuid_order_and_duplicates():
    from rcca_agent.workflow import observation_hashes

    first = {
        "id": "one",
        "cluster_id": "c",
        "scope": {"clusters": []},
        "time_range": {"start": "s", "end": "e"},
        "tool_status": "ok",
        "snapshot": {
            "data": {"result": [{"metric": {"gpu": "a"}, "values": [[1, "3"]]}]}
        },
    }
    duplicate = {**deepcopy(first), "id": "two", "created_at": "later"}
    original = observation_hashes({"D02": [first]})
    assert observation_hashes({"D02": [duplicate, first]}) == original
    duplicate["snapshot"]["data"]["result"][0]["values"].append([2, "4"])
    assert observation_hashes({"D02": [duplicate]}) - original


async def test_new_required_fact_cannot_be_bypassed_by_goal_policy():
    case = policy_case()
    book = case["attempt"]["context"]["runbooks"][0]
    book["content"]["required_evidence"].append("normalized_health")
    book.update(
        content_hash=content_hash(book["content"]),
        reviewed_content_hash=content_hash(book["content"]),
    )
    result = await replay(case)
    assert (
        result["output"]["result"]["quality"]["rca_evaluation"]["investigation"][
            "stop_reason"
        ]
        != "goal_achieved"
    )


async def test_report_editor_failure_preserves_frozen_material_and_code_report():
    case = policy_case()
    case["responses"]["report_writing"] = [
        {"raw_text": "not json", "usage": {"total_tokens": 100}}
    ] * 2
    result = await replay(case)
    assert not result["missing_inputs"]
    output = result["output"]["result"]
    frozen = next(
        row["snapshot"]
        for row in result["output"]["evidence"]
        if row["query_id"] == "rca_result_frozen"
    )
    assert frozen["material"]["evaluation"] == output["quality"]["rca_evaluation"]
    assert output["quality"]["report"]["method"] == "deterministic_fallback"
    assert output["narrative"]


async def test_report_cannot_change_rca_conclusion(monkeypatch):
    from rcca_agent import workflow

    original = workflow.write_report

    async def corrupt(result, *args):
        await original(result, *args)
        result["limitations"].clear()

    monkeypatch.setattr(workflow, "write_report", corrupt)
    with pytest.raises(ValueError, match="report changed frozen"):
        await replay(policy_case())
