"""Semantic revision bounds and complete stage inputs within the existing budget."""

from copy import deepcopy

import pytest

from rca_replay_cases import review
from test_rca_llm_roles import Writer, material
from rcca_agent.report_writer import write_material_report
from rcca_agent.evidence_interpretation import call_stage


def rejection():
    value = review("revision_required")
    value["issues"] = [
        {
            "claim_id": "interpretation:findings:finding-1",
            "reason": "오류 보고와 물리적 고장을 구분하세요.",
            "evidence_refs": {"$input": "/input_evidence_refs"},
            "suggested_resolution": "자료에 기록된 오류로 한정하세요.",
        }
    ]
    return value


async def test_report_does_not_send_fixed_sources_twice():
    source = material()
    source["investigation_summary"] = [
        {
            "section": "comparison",
            "text": "기록을 비교했습니다. " * 5000,
            "evidence_refs": ["D09-ref"],
        }
    ]
    before = deepcopy(source)
    model = Writer()
    result = {"quality": {}}
    await write_material_report(result, source, model)
    assert source == before
    assert len(model.inputs) == 1
    assert "fixed_limitations" not in model.inputs[0]
    assert source["investigation_summary"][0]["text"] in str(result["narrative"])
    assert result["quality"]["report"]["method"] == "llm_composed"


@pytest.mark.parametrize("remaining,called", [(100000, True), (10000, False)])
async def test_dynamic_stage_budget_keeps_all_input_or_skips(remaining, called):
    class Model:
        configured = True
        reserved_tokens = 4096
        inputs = []

        async def complete(self, prompt, payload, **kwargs):
            self.inputs.append(deepcopy(payload))
            return {"ok": True}

    model = Model()
    model.remaining = remaining
    payload = {"material": "증거" * 5000}
    before = deepcopy(payload)
    _, diagnostic = await call_stage(
        model, "analysis_review", "review", payload, lambda x: x, max_bytes=None
    )
    assert bool(model.inputs) is called
    assert payload == before
    if called:
        assert model.inputs == [payload]
        assert diagnostic["input_bytes"] > 24000
    else:
        assert diagnostic["reason"] == "llm_token_budget_exhausted"
    assert model.remaining == remaining and model.reserved_tokens == 4096
