import asyncio
from copy import deepcopy
import time

import pytest

from agent_common.llm import LLM, RemoteUncertain
from agent_common.settings import Settings
from agent_common.observation import Observation
from agent_common.rca_evaluation import source_evaluation, validate_evaluation
from rcca_agent.analysis_review import analysis_draft, validate_review
from rcca_agent.evaluation import collection_status, evaluate_analysis
from rcca_agent.evidence_interpretation import (
    call_stage,
    inspection_context,
    validate_interpretation,
)
from rcca_agent.synthesis_context import bounded_context, encoded_size
from evaluation_fixtures import interpretation_reply, review_reply
from test_rca_analysis import analysis_reply


PERIOD = {"start": "2026-09-15T00:00:00Z", "end": "2026-09-15T01:00:00Z"}
DATA = {
    "scope": {"clusters": [{"cluster_id": "c", "namespaces": None}]},
    "time_range": PERIOD,
}


def observation(status="ok", complete=True):
    return {
        "id": "log",
        "query_id": "D09",
        "cluster_id": "c",
        "scope": DATA["scope"],
        "time_range": PERIOD,
        "tool_status": status,
        "quality": {"complete": complete},
        "snapshot": {
            "data": {
                "result": [
                    {
                        "stream": {},
                        "values": [
                            ["1789430400000000000", "unreadable . GPU-A error report"]
                        ],
                    }
                ]
            }
        },
    }


@pytest.mark.parametrize(
    "entries,expected",
    [
        ([observation()], "complete"),
        ([observation("empty")], "complete"),
        ([observation("partial", False)], "partial"),
        ([observation(), observation("unavailable", False)], "partial"),
        ([observation("unavailable", False)], "failed"),
        ([], "failed"),
    ],
)
def test_collection_is_transport_only(entries, expected):
    result = collection_status(["D09"], {"D09": entries})
    assert result["status"] == expected
    assert "verdict" not in result
    assert collection_status([], {})["status"] == "not_requested"
    assert collection_status(["D09"], {}, True)["reason"] == "fast_path"


def test_unparseable_source_and_literal_identity_are_not_promoted_or_discarded():
    original = observation()
    copy = deepcopy(original)
    health = [{"target": {"node": "gpu-a."}, "evidence_refs": ["log"]}]
    view = inspection_context(
        {**DATA, "target": {"node": "gpu-a"}}, [original], health, []
    )
    assert view["raw_excerpts"][0]["interpretation_only"] is True
    assert view["evidence_checks"][0]["reason"] == "literal_comparison_only"
    assert view["evidence_checks"][0]["outcome"] == "fail"
    assert original == copy
    original["cluster_id"] = "outside"
    assert not inspection_context(DATA, [original], [], [])["raw_excerpts"]


def test_diagnostics_and_interpretation_cannot_create_usable_observations():
    payload = {
        "evidence_checks": [
            {"evidence_refs": ["failed-request"], "outcome": "unknown"}
        ],
        "interpretation_findings": [
            {"kind": "inferred", "evidence_refs": ["failed-request"]}
        ],
    }
    view = bounded_context(payload, 6000)
    assert view["observation_refs"] == []
    assert view["input_evidence_refs"] == ["failed-request"]
    response = interpretation_reply()
    response["findings"] = [
        {
            "id": "f",
            "statement": "오타일 수 있습니다.",
            "kind": "inferred",
            "evidence_refs": ["log"],
        }
    ]
    assert validate_interpretation(response, {"log"}) == response
    for edit in (
        {"kind": "verified"},
        {"evidence_refs": ["invented"]},
        {"measurement": 2},
    ):
        bad = deepcopy(response)
        bad["findings"][0].update(edit)
        with pytest.raises(ValueError):
            validate_interpretation(bad, {"log"})


def test_rubric_verdict_refs_and_draft_hash_are_bound():
    draft = analysis_draft([], [], ["GPU 연결 미확인"], {})
    payload = {"draft": draft, "input_evidence_refs": ["log"]}
    good = review_reply(payload, "acceptable")
    assert validate_review(good, draft, {"log"}, set()) == good
    for change in ("status", "refs", "id", "missing_criterion", "unknown_query"):
        bad = deepcopy(good)
        if change == "status":
            bad["criteria"]["grounding"]["status"] = "needs_revision"
        elif change == "refs":
            bad["criteria"]["grounding"]["evidence_refs"] = ["invented"]
        elif change == "id":
            bad["analysis_id"] = "older-draft"
        elif change == "missing_criterion":
            del bad["criteria"]["alternatives"]
        else:
            bad["followup_questions"] = [
                {
                    "question": "확인",
                    "expected_effect": "판단 변경",
                    "query_ids": ["arbitrary"],
                }
            ]
        with pytest.raises(ValueError):
            validate_review(bad, draft, {"log"}, set())
    assert analysis_draft([], [], [], {})["analysis_id"] != draft["analysis_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [RemoteUncertain, asyncio.CancelledError, TimeoutError]
)
async def test_remote_uncertainty_and_cancellation_never_become_a_verdict(failure):
    class Model:
        configured = True

        async def complete(self, *args, **kwargs):
            raise failure()

    with pytest.raises(failure):
        await call_stage(Model(), "analysis_review", "prompt", {}, lambda x: x)


@pytest.mark.asyncio
async def test_invalid_stage_repairs_once_without_storing_raw_output():
    class Model:
        configured = True
        count = 0

        async def complete(self, *args, **kwargs):
            self.count += 1
            return {"secret-rejected-output": "never persisted"}

    model = Model()
    value, diagnostics = await call_stage(
        model,
        "evidence_interpretation",
        "prompt",
        {},
        lambda v: validate_interpretation(v, set()),
    )
    assert value is None and model.count == 2
    assert diagnostics["execution_status"] == "failed"
    assert "secret-rejected-output" not in str(diagnostics)


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["evidence_interpretation", "analysis_review"])
@pytest.mark.parametrize(
    "size_blocked,tokens_blocked",
    [(True, False), (False, True), (True, True), (False, False)],
)
async def test_stage_limit_checks_are_independent_and_preserve_boundaries(
    stage, size_blocked, tokens_blocked
):
    payload, prompt = {"text": "한글 원문"}, "fixture"
    size = encoded_size(payload)
    required = size + len(prompt.encode()) + 512

    class Model(LLM):
        calls = 0

        async def complete(self, *args, **kwargs):
            self.calls += 1
            return {}

    model = Model(
        Settings(
            kind="rca",
            llm_base_url="http://fixture.invalid",
            llm_model="fixture",
            llm_api_key="fixture",
        ),
        time.monotonic() + 30,
        required + 100 + (0 if tokens_blocked else 1),
        lambda _: None,
    )
    model.reserved_tokens = 100
    value, diagnostic = await call_stage(
        model, stage, prompt, payload, lambda v: v, max_bytes=size - int(size_blocked)
    )
    blocked = size_blocked or tokens_blocked
    assert model.calls == (0 if blocked else 1)
    assert diagnostic["execution_status"] == ("skipped" if blocked else "complete")
    assert (value is None) == blocked
    assert diagnostic["reason"] == (
        "llm_input_size_exceeded"
        if size_blocked
        else "llm_token_budget_exhausted"
        if tokens_blocked
        else None
    )
    check = diagnostic["request_checks"][0]
    assert check["input_size_exceeded"] is size_blocked
    assert check["token_budget_exhausted"] is tokens_blocked
    assert check["input_bytes"] == size
    assert (
        check["remaining_tokens"] - check["reserved_tokens"]
        == check["available_tokens"]
    )
    assert check["required_tokens"] == required
    assert (
        check["output_token_cap"]
        == model.request_budget(prompt, payload, stage)["output_token_cap"]
    )
    assert "한글 원문" not in str(diagnostic)


@pytest.mark.asyncio
async def test_repair_size_failure_retains_first_call_and_both_checks():
    class Model:
        configured = True
        remaining = 1000000
        count = 0

        async def complete(self, *args, **kwargs):
            self.count += 1
            return {"invalid": "never store this raw reply"}

    model = Model()
    value, diagnostic = await call_stage(
        model,
        "evidence_interpretation",
        "prompt",
        {},
        lambda v: validate_interpretation(v, set()),
        max_bytes=20,
    )
    assert value is None and model.count == 1
    assert diagnostic["execution_status"] == "failed"
    assert diagnostic["reason"] == "llm_input_size_exceeded"
    assert [c["model_called"] for c in diagnostic["request_checks"]] == [True, False]
    assert diagnostic["request_checks"][1]["input_bytes"] > 20
    assert diagnostic["validation_failures"] == ["invalid_stage_output"]
    assert "never store" not in str(diagnostic)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["llm_http_error", "llm_deadline_exhausted", "llm_output_truncated"]
)
async def test_transport_failure_is_not_reclassified_as_input_or_token_limit(failure):
    class Model:
        configured = True
        last_failure = failure

        async def complete(self, *args, **kwargs):
            return None

    if failure == "llm_deadline_exhausted":
        with pytest.raises(TimeoutError):
            await call_stage(Model(), "analysis_review", "prompt", {}, lambda v: v)
    else:
        value, diagnostic = await call_stage(
            Model(), "analysis_review", "prompt", {}, lambda v: v
        )
        assert value is None and diagnostic["reason"] == failure
        assert diagnostic["attempts"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    [
        "limited_valid",
        "repair",
        "unresolved",
        "budget_after_repair",
        "model_failure",
        "fallback_model_failure",
        "fallback_rejected",
        "oversized_review",
    ],
)
async def test_round_reviews_final_rules_and_handles_repairs_and_limits(mode):
    obs = Observation({}, {"queries": {}}, DATA, time.monotonic() + 60)
    obs.evidence.append(observation("partial", False))
    state = {"revisions": 0}
    stages = []
    seen_drafts = []

    class Model:
        configured = True
        remaining = 100000
        usage = {}

        async def complete(self, system, payload, *, stage):
            stages.append(stage)
            if stage == "evidence_interpretation":
                return interpretation_reply()
            if stage == "synthesis":
                return analysis_reply(payload["observation_refs"])
            assert stage == "analysis_review"
            seen_drafts.append(deepcopy(payload["draft"]))
            assert any(
                c["id"] == "recommendation:0" for c in payload["draft"]["claims"]
            )
            if mode == "model_failure" or (
                mode == "fallback_model_failure" and len(seen_drafts) > 2
            ):
                return None
            if (
                mode == "limited_valid"
                or (mode == "repair" and len(seen_drafts) > 1)
                or (len(seen_drafts) > 2 and mode != "fallback_rejected")
            ):
                return review_reply(payload, "acceptable")
            if mode == "budget_after_repair" and len(seen_drafts) == 2:
                self.remaining = 0
            issue = {
                "claim_id": None,
                "reason": "관측 공백으로 원인을 배제할 수 없습니다.",
                "evidence_refs": ["log"],
                "suggested_resolution": "한계를 밝히고 단정을 제거하세요.",
            }
            return review_reply(payload, "revision_required", [issue])

    def assemble(candidates):
        return candidates, [
            {
                "text": "조건 확인 후 담당자가 검토하세요."
                * (1000 if mode == "oversized_review" else 1),
                "eligibility": "eligible",
                "execution": "not_performed",
                "evidence_refs": ["log"],
                "value_refs": [],
            }
        ]

    output = await evaluate_analysis(
        obs,
        DATA,
        {},
        [],
        {
            "observation_refs": [],
            "device_observations": [],
            "pod_relations": [],
            "metric_observations": [],
        },
        assemble,
        Model(),
        state,
        0,
        [],
    )
    assert stages[0:3] == (
        ["evidence_interpretation", "synthesis"]
        if mode == "oversized_review"
        else ["evidence_interpretation", "synthesis", "analysis_review"]
    )
    assert output["review"]["analysis_id"] == output["draft"]["analysis_id"]
    assert all(
        c["causal_status"] == "candidate" for c in output["draft"]["cause_candidates"]
    )
    if mode in {"unresolved", "budget_after_repair"}:
        assert not output["draft"]["cause_candidates"]
        assert output["draft"]["recommendations"][0]["eligibility"] == "withheld"
        assert seen_drafts[0]["analysis_id"] != output["draft"]["analysis_id"]
    if mode == "oversized_review":
        assert output["review"]["verdict"] is None
        assert output["review"]["reason"] == "llm_input_size_exceeded"
        assert output["stop_reason"] == "analysis_unresolved"
        record = next(e for e in obs.evidence if e["query_id"] == "analysis_review")
        assert (
            record["quality"]["request_checks"] == record["snapshot"]["request_checks"]
        )
        assert record["quality"]["attempts"] == 0
    elif mode == "budget_after_repair":
        assert output["review"]["execution_status"] == "skipped"
        assert output["review"]["verdict"] is None
        assert output["review"]["reason"] == "draft_changed_after_review"
        assert output["stop_reason"] == "llm_budget_exhausted"
        assert output["review"]["failure_reason"] == "llm_token_budget_exhausted"
    elif mode in {"fallback_model_failure", "fallback_rejected"}:
        assert output["review"]["verdict"] is None
        assert output["review"]["reason"] == "draft_changed_after_review"
        assert output["stop_reason"] == (
            "revision_limit_reached"
            if mode == "fallback_rejected"
            else "analysis_unresolved"
        )
        if mode == "fallback_rejected":
            assert not output["draft"]["cause_candidates"]
            assert not output["draft"]["recommendations"]
    elif mode == "model_failure":
        assert output["review"]["verdict"] is None
    else:
        assert output["review"]["verdict"] == "acceptable"
    assert state["revisions"] <= 1
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
                "stop_reason": "no_available_followup",
                "evidence_refs": [],
            },
        }
    }
    validate_evaluation(body, obs.evidence)
    body["limitations"] = ["different final text"]
    with pytest.raises(ValueError, match="changed after review"):
        validate_evaluation(body, obs.evidence)
    source = source_evaluation(body)
    assert "evidence_refs" not in str(source)
    assert source["review_verdict"] == output["review"]["verdict"]


def test_legacy_and_unknown_extension_are_not_reviewed():
    validate_evaluation({"quality": {}}, [])
    assert source_evaluation({})["review_status"] == "legacy_unreviewed"
    unknown = source_evaluation(
        {
            "quality": {
                "rca_evaluation": {
                    "schema_version": "99",
                    "review": {"verdict": "acceptable"},
                }
            }
        }
    )
    assert (
        unknown["review_status"] == "unsupported_schema"
        and unknown["review_verdict"] is None
    )
    with pytest.raises(ValueError, match="unsupported"):
        validate_evaluation(
            {"quality": {"rca_evaluation": {"schema_version": "99"}}}, []
        )


@pytest.mark.asyncio
async def test_transport_reserves_review_budget_even_after_truncated_synthesis():
    import json
    import httpx
    from agent_common.llm import LLM
    from agent_common.settings import Settings

    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length" if len(requests) == 1 else "stop",
                        "message": {"content": "{}"},
                    }
                ],
                "usage": {"total_tokens": 3000 if len(requests) == 1 else 100},
            },
        )

    settings = Settings(
        kind="rca",
        llm_base_url="http://fixture.invalid/v1",
        llm_model="fixture",
        llm_api_key="fixture",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        llm = LLM(settings, time.monotonic() + 30, 10000, lambda _: None, http)
        llm.reserved_tokens = 7000
        assert await llm.complete("prompt", {}, stage="synthesis") is None
        assert llm.last_failure == "llm_output_truncated"
        assert len(requests) == 1 and requests[0]["max_tokens"] < 3000
        assert llm.remaining == 7000
        llm.reserved_tokens = 0
        assert await llm.complete("review", {}, stage="analysis_review") == {}
        assert len(requests) == 2 and llm.remaining == 6900


@pytest.mark.asyncio
@pytest.mark.parametrize("reported", [True, False])
async def test_usage_distinguishes_reported_tokens_from_conservative_charge(reported):
    import httpx
    import json

    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "{}"}}],
                **({"usage": {"total_tokens": 10}} if reported else {}),
            },
        )

    settings = Settings(
        kind="rca",
        llm_base_url="http://fixture.invalid/v1",
        llm_model="fixture",
        llm_api_key="fixture",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        llm = LLM(settings, time.monotonic() + 30, 10000, lambda _: None, http)
        llm.reserved_tokens = 2000
        budget = llm.request_budget("prompt", {}, "analysis_review")
        assert await llm.complete("prompt", {}, "analysis_review") == {}
        assert requests[0]["max_tokens"] == budget["output_token_cap"]
        charged = (
            10
            if reported
            else budget["prompt_token_bound"] + budget["output_token_cap"]
        )
        assert llm.usage["total_tokens"] == (10 if reported else 0)
        assert llm.usage["charged_tokens"] == 10000 - llm.remaining == charged
        assert llm.usage["estimated_tokens"] == (0 if reported else charged)
        assert llm.usage["usage_missing_calls"] == (0 if reported else 1)
