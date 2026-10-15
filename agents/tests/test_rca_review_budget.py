"""A review-requested revision that cannot run must not resurrect rejected claims.

The sequences replay production jobs 648dd3f1 (claim-level objection, revision
synthesis out of budget) and bccd8ea7 (draft-wide objection) from 2026-10-15.
"""

from copy import deepcopy
import json
import time

import pytest

from agent_common.observation import Observation
from agent_common.rca_evaluation import validate_evaluation
from rcca_agent.evaluation import (
    RETAINED_LIMIT,
    UNRESOLVED_LIMIT,
    collection_status,
    evaluate_analysis,
)
from rcca_agent.evidence_interpretation import interpret_evidence
from evaluation_fixtures import interpretation_reply, review_reply
from test_rca_evaluation import DATA, observation

# Production text named "XID 79"; fixture evidence registers no number, so it is omitted.
REJECTED = (
    "펌웨어 또는 드라이버 오류로 인해 가짜 오류 이벤트가 생성되었을 가능성이 있다"
)
KEPT = "관측한 장비 증상은 추가 확인이 필요합니다."
QUESTIONS = [
    {
        "question": "해당 GPU 노드의 펌웨어 버전과 드라이버 버전은 무엇인가?",
        "query_ids": ["D02"],
        "expected_effect": "소프트웨어 기원 가설을 확인하거나 배제합니다.",
    }
]


def hypothesis(claim, refs):
    return {
        "claim": claim,
        "supporting_refs": refs,
        "contradicting_refs": [],
        "missing_inputs": ["producer_confirmation"],
    }


class Script:
    """Fixed model replies; the budget drops to zero once the review objects."""

    configured = True

    def __init__(self, claims, objection, round_verdict="revision_required"):
        self.claims, self.objection, self.round_verdict = (
            claims,
            objection,
            round_verdict,
        )
        self.remaining = 100000
        self.usage = {}
        self.stages = []
        self.drafts = []

    async def complete(self, system, payload, *, stage):
        self.stages.append(stage)
        if stage == "evidence_interpretation":
            return interpretation_reply()
        if stage == "synthesis":
            refs = payload["observation_refs"]
            return {
                "hypotheses": [hypothesis(c, refs) for c in self.claims],
                "limitations": [],
            }
        assert stage == "analysis_review"
        self.drafts.append(deepcopy(payload["draft"]))
        if self.round_verdict == "acceptable":
            return review_reply(payload, "acceptable")
        reply = review_reply(payload, "revision_required", self.objection(payload))
        reply["followup_questions"] = QUESTIONS
        # As in production: the review leaves no room for the revision synthesis.
        self.remaining = 0
        return reply


def assemble(candidates):
    return list(candidates), [
        {
            "text": "조건 확인 후 담당자가 검토하세요.",
            "eligibility": "eligible",
            "execution": "not_performed",
            "evidence_refs": ["log"],
            "value_refs": [],
        }
    ]


def payload():
    return {
        "observation_refs": [],
        "device_observations": [],
        "pod_relations": [],
        "metric_observations": [],
    }


async def evaluate(model, state, round_no=0):
    obs = Observation({}, {"queries": {}}, DATA, time.monotonic() + 60)
    obs.evidence.append(observation("partial", False))
    output = await evaluate_analysis(
        obs, DATA, {}, [], payload(), assemble, model, state, round_no, ["D02"]
    )
    body = {
        key: output["draft"][key]
        for key in ("cause_candidates", "recommendations", "limitations")
    }
    body["quality"] = {
        "rca_evaluation": {
            "schema_version": "1",
            "analysis_id": output["draft"]["analysis_id"],
            "collection": collection_status(["D09"], {"D09": [obs.evidence[0]]}),
            "evidence": output["evidence"],
            "review": output["review"],
            "investigation": {
                "status": "finished",
                "stop_reason": output["stop_reason"] or "no_available_followup",
                "evidence_refs": [],
            },
        }
    }
    validate_evaluation(body, obs.evidence)
    return output, obs


def claim_objection(claim):
    def objection(payload):
        target = next(
            c["id"]
            for c in payload["draft"]["claims"]
            if c["id"].startswith("cause:") and claim in c["statement"]
        )
        return [
            {
                "claim_id": target,
                "reason": "인용된 증거가 이 주장을 지원하지 않습니다.",
                "evidence_refs": ["log"],
                "suggested_resolution": "근거가 없으면 주장을 제거하세요.",
            }
        ]

    return objection


def draft_objection(payload):
    return [
        {
            "claim_id": None,
            "reason": "대체 설명을 고려하지 않았습니다.",
            "evidence_refs": ["log"],
            "suggested_resolution": "대안을 함께 검토하세요.",
        }
    ]


@pytest.mark.asyncio
async def test_rejected_claim_is_dropped_and_fallback_is_not_reviewed():
    # Replays 648dd3f1: the only hypothesis is rejected, the revision cannot run.
    model = Script([REJECTED], claim_objection(REJECTED))
    state = {"revisions": 0}
    output, obs = await evaluate(model, state)
    assert model.stages == ["evidence_interpretation", "synthesis", "analysis_review"]
    assert len(model.drafts) == 1  # no second review of a deterministic fallback
    text = json.dumps(output["draft"], ensure_ascii=False)
    assert REJECTED not in text
    assert output["draft"]["cause_candidates"] == []
    assert UNRESOLVED_LIMIT in output["draft"]["limitations"]
    assert output["draft"]["recommendations"][0]["eligibility"] == "withheld"
    assert output["review"]["execution_status"] == "skipped"
    assert output["review"]["reason"] == "review_revision_unavailable"
    assert output["review"]["failure_reason"] == "llm_context_budget_exhausted"
    assert output["review"]["verdict"] is None
    assert output["stop_reason"] == "llm_budget_exhausted"
    # The unresolved objection still steers evidence selection.
    assert output["review_output"]["followup_questions"] == QUESTIONS
    assert "safe_model_candidates" not in state
    records = [e["query_id"] for e in obs.evidence]
    assert records.count("analysis_review") == 2  # model review + skipped record


@pytest.mark.asyncio
async def test_unflagged_claim_survives_when_revision_cannot_run():
    model = Script([REJECTED, KEPT], claim_objection(REJECTED))
    output, _ = await evaluate(model, {"revisions": 0})
    claims = [c["claim"] for c in output["draft"]["cause_candidates"]]
    assert claims == [KEPT]
    assert REJECTED not in json.dumps(output["draft"], ensure_ascii=False)
    assert UNRESOLVED_LIMIT in output["draft"]["limitations"]
    assert model.stages.count("analysis_review") == 1


@pytest.mark.asyncio
async def test_draft_wide_objection_keeps_no_model_claim():
    # Replays bccd8ea7: every issue targets the whole draft (claim_id null).
    model = Script([REJECTED, KEPT], draft_objection)
    output, _ = await evaluate(model, {"revisions": 0})
    assert output["draft"]["cause_candidates"] == []
    assert model.stages.count("analysis_review") == 1
    assert output["review"]["reason"] == "review_revision_unavailable"


@pytest.mark.asyncio
async def test_later_round_retains_only_review_accepted_claims():
    state = {"revisions": 0}
    accepted = Script([KEPT], None, round_verdict="acceptable")
    first, _ = await evaluate(accepted, state, 0)
    assert first["review"]["verdict"] == "acceptable"
    assert [c["claim"] for c in state["safe_model_candidates"]] == [KEPT]

    exhausted = Script([REJECTED], None, round_verdict="acceptable")
    exhausted.remaining = 0
    second, _ = await evaluate(exhausted, state, 1)
    assert "analysis_review" not in exhausted.stages
    assert [c["claim"] for c in second["draft"]["cause_candidates"]] == [KEPT]
    assert RETAINED_LIMIT in second["draft"]["limitations"]
    assert second["review"]["reason"] == "synthesis_unavailable"
    assert second["stop_reason"] == "llm_budget_exhausted"


@pytest.mark.asyncio
async def test_interpretation_reports_budget_when_observations_do_not_fit():
    class Empty:
        configured = True
        remaining = 0

    _, diagnostics = await interpret_evidence(Empty(), {"observation_refs": ["log"]})
    assert diagnostics["reason"] == "llm_context_budget_exhausted"
    _, diagnostics = await interpret_evidence(Empty(), {"observation_refs": []})
    assert diagnostics["reason"] == "no_usable_evidence"
