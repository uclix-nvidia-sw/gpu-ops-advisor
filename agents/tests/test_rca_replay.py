"""Exercise the offline runner through the product workflow, not a copied loop."""

from copy import deepcopy

import httpx
import pytest

from rca_replay import bind, compare, readable_summary, replay
from rca_replay_cases import cases


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("replay attempted real HTTP")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)


@pytest.mark.parametrize("name", list(cases()))
async def test_frozen_replay_contract(name, monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://must-not-be-used.invalid")
    monkeypatch.setenv("LLM_MODEL_ANALYSIS_REVIEW", "must-not-be-used")
    case = cases()[name]
    original = deepcopy(case)
    result = await replay(case)
    assert case == original
    assert result["replay_status"] == "complete", result["missing_inputs"]
    assert result["semantic_quality"] == "not_measured"
    assert result["source_manifest"]["rcca_agent"]["workflow.py"]
    assert result["remaining_tokens"] >= 0
    assert (
        result["usage"]["charged_tokens"]
        == case["token_budget"] - result["remaining_tokens"]
    )
    assert all(
        request["model"] == "offline-fixture"
        for call in result["model_calls"]
        for request in call["requests"]
    )
    summary = result["summary"]
    if name.startswith("review_"):
        assert summary["review_only_verdict"] == case["expectations"]["verdict"]
        assert summary["transport_calls"] == 1
        return
    assert all(call["matched"] for call in result["query_calls"])
    assert summary["review_verdicts"] == []
    assert [c["stage"] for c in result["model_calls"]] == (
        [] if name == "insufficient_budget" else ["synthesis", "report_writing"]
    )
    assert len(summary["decisions"]) == 1
    assert summary["decisions"][0]["action"] == "finish"
    assert summary["decisions"][0]["selected_queries"] == []
    if name == "insufficient_budget":
        assert summary["transport_calls"] == 0
    if name == "interpretation_only":
        assert summary["truncated_responses"] == 1
    # Every source retained by the model is a stored evidence ID.
    ids = {e["id"] for e in result["output"]["evidence"]}
    for call in result["model_calls"]:
        assert set(call["input"].get("input_evidence_refs", [])) <= ids


async def test_missing_query_is_partial_not_silent_empty_success():
    case = cases()["enough_budget"]
    case["queries"] = []
    result = await replay(case)
    assert result["replay_status"] == "partial"
    assert any(
        reason.startswith("query_fixture:") for reason in result["missing_inputs"]
    )
    assert result["query_calls"][0]["matched"] is False
    assert not any(row == "complete" for row in result["summary"]["synthesis_statuses"])


async def test_missing_model_fixture_and_missing_usage_are_distinct():
    case = cases()["review_limited"]
    case["responses"]["analysis_review"] = []
    missing = await replay(case)
    assert missing["replay_status"] == "partial"
    assert missing["output"]["review"] is None
    case["responses"] = deepcopy(cases()["review_limited"]["responses"])
    case["responses"]["analysis_review"][0].pop("usage")
    estimated = await replay(case)
    assert estimated["replay_status"] == "complete"
    assert estimated["summary"]["fixture_reported_tokens"] is None
    assert estimated["usage"]["usage_missing_calls"] == 1
    assert estimated["usage"]["charged_tokens"] > 0


async def test_compare_requires_same_frozen_inputs():
    case = cases()["review_limited"]
    before = await replay(case)
    after = await replay(case)
    assert compare(before, after) == {}
    case["token_budget"] += 1
    with pytest.raises(ValueError, match="different frozen inputs"):
        compare(before, await replay(case))
    tampered = deepcopy(before)
    tampered["input"]["token_budget"] += 1
    with pytest.raises(ValueError, match="modified replay input"):
        compare(tampered, after)


async def test_summary_explains_followup_and_retained_partial_result():
    result = await replay(cases()["accepted_rule_followup"])
    text = readable_summary(result)
    assert "추가 수집 D02(GPU 활동)" not in text
    assert "no_remaining_queries" in text
    assert "실제 모델의 판단 정확도·비용은 측정하지 않았습니다" in text
    result = await replay(cases()["interpretation_only"])
    assert "해석만 보존된 라운드: 0개" in readable_summary(result)
    assert "모델 응답이 출력 제한으로 잘렸습니다" in readable_summary(result)


async def test_invalid_review_is_rejected_and_raw_text_not_traced():
    case = cases()["review_limited"]
    case["responses"]["analysis_review"] = [
        {"raw_text": "BROKEN_FIXTURE_SECRET", "usage": {"total_tokens": 100}}
    ] * 2
    result = await replay(case)
    assert result["output"]["review"] is None
    assert result["output"]["diagnostics"]["validation_failures"]
    assert "BROKEN_FIXTURE_SECRET" not in str(result["model_calls"])


def test_explicit_binding_does_not_interpolate_evidence_text():
    assert bind({"$input": "/x/0/a~1b"}, {"x": [{"a/b": "id"}]}) == "id"
    assert (
        bind("ignore instructions /input_evidence_refs", {})
        == "ignore instructions /input_evidence_refs"
    )
    with pytest.raises(ValueError, match="JSON pointer"):
        bind({"$input": "input_evidence_refs"}, {})


async def test_unresolvable_fixture_binding_is_partial_replay():
    case = cases()["review_limited"]
    case["responses"]["analysis_review"][0]["response"]["analysis_id"] = {
        "$input": "/missing"
    }
    result = await replay(case)
    assert result["replay_status"] == "partial"
    assert result["missing_inputs"] == ["fixture_binding:analysis_review:0"]
    assert result["output"]["review"] is None


@pytest.mark.parametrize(
    "change",
    [
        {"data_origin": "production"},
        {"schema": "unknown"},
        {"expectations": {}},
        {"token_budget": -1},
    ],
)
async def test_replay_rejects_invalid_boundary(change):
    with pytest.raises(ValueError):
        await replay({**cases()["enough_budget"], **change})
