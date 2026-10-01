import copy
import json
from pathlib import Path

import pytest

from rcca_agent.report_labels import LABELS
from rcca_agent.synthesis import identifier_tokens, validate_synthesis
from rcca_agent.report import write_report


def reply(claim="보고된 장비 오류는 추가 확인이 필요합니다.", limitations=None):
    return {
        "hypotheses": [
            {
                "claim": claim,
                "supporting_refs": ["log"],
                "contradicting_refs": [],
                "missing_inputs": [],
            }
        ],
        "limitations": limitations or [],
    }


@pytest.mark.parametrize(
    "word",
    [
        "zero",
        "ONE",
        "twenty",
        "hundred",
        "thousand",
        "million",
        "percent",
        "half",
        "dozen",
        "single",
        "double",
        "twice",
        "하나",
        "둘",
        "셋",
        "넷",
        "다섯",
        "열",
        "스물",
        "한 대",
        "두개의",
        "세 번",
        "네 건",
        "다섯 명",
        "여섯 장",
        "일곱 시간",
        "여덟 분",
        "아홉 초",
        "영 퍼센트",
        "일프로",
        "이%",
        "삼 퍼센트",
        "전혀 없음",
        "모두 0",
    ],
)
def test_numeric_words_rejected_in_claims_and_limitations(word):
    text = f"관측 결과 {word} 상태는 확인이 필요합니다."
    with pytest.raises(ValueError, match="unregistered_numeric_claim"):
        validate_synthesis(reply(text), ["log"])
    with pytest.raises(ValueError, match="invalid_limitations"):
        validate_synthesis(reply(limitations=[text]), ["log"])


@pytest.mark.parametrize(
    "word",
    [
        "한계",
        "열화",
        "일부",
        "이상",
        "삼성",
        "이번",
        "영향",
        "일반",
        "두께",
        "세부",
        "네트워크",
    ],
)
def test_number_prefixes_do_not_reject_normal_words(word):
    assert validate_synthesis(reply(f"{word} 관련 조건을 확인해야 합니다."), ["log"])


@pytest.mark.parametrize(
    "text",
    [
        "The GPU needs confirmation.",
        "The GPU has physically fallen off the PCIe bus 가",
        "D05 XID 79",
    ],
)
def test_english_or_identifier_only_claim_rejected(text):
    with pytest.raises(ValueError, match="non_korean_claim"):
        validate_synthesis(
            reply(text),
            ["log"],
            [{"error_code": "xid:79", "evidence_refs": ["log"]}],
            ["D05"],
        )
    with pytest.raises(ValueError, match="invalid_limitations"):
        validate_synthesis(
            reply(limitations=[text]),
            ["log"],
            [{"error_code": "xid:79", "evidence_refs": ["log"]}],
            ["D05"],
        )


def test_korean_identifiers_and_cited_codes_preserved():
    view = {
        "target": {"node": "vessl-k8s-worker-01", "cluster_id": "cpc-2"},
        "purpose_ids": ["R01"],
        "query_quality": [{"query_id": "D05"}],
    }
    text = "cpc-2 vessl-k8s-worker-01 D05 R01 XID 79의 보고 내용을 확인해야 합니다."
    assert validate_synthesis(
        reply(text, [text]),
        ["log"],
        [{"error_code": "xid:79", "evidence_refs": ["log"]}],
        identifier_tokens(view),
    )


@pytest.mark.parametrize(
    "text",
    [
        "시각 정밀도 손실로 기간 확인이 제한됩니다.",
        "조회 시각 정밀도 축소로 확인이 제한됩니다.",
    ],
)
def test_precision_loss_requires_the_actual_query_reason(text):
    for quality in (
        [],
        [{"query_id": "D05", "quality": {"complete": True}}],
        [{"query_id": "D05", "quality": {"reason": "query_failed"}}],
    ):
        with pytest.raises(ValueError, match="invalid_limitations"):
            validate_synthesis(
                reply(limitations=[text]), ["log"], query_quality=quality
            )
    assert validate_synthesis(
        reply(limitations=[text]),
        ["log"],
        query_quality=[{"quality": {"reason": "time_precision_reduced"}}],
    )


@pytest.mark.parametrize(
    "text",
    [
        "장비 고장이 원인입니다.",
        "장비는 고장입니다.",
        "표본으로 보아 장비는 유휴입니다.",
    ],
)
def test_narrow_assertions_are_rejected(text):
    with pytest.raises(ValueError, match="unsupported_assertion"):
        validate_synthesis(reply(text), ["log"])


def test_label_mirrors_match():
    path = Path(__file__).resolve().parents[2] / "frontend/src/lib/rcaLabels.json"
    assert json.loads(path.read_text(encoding="utf-8")) == LABELS


@pytest.mark.asyncio
@pytest.mark.parametrize("old", [True, False])
async def test_report_all_queries_grouped_without_summing_samples(old):
    class Model:
        configured = False

    evidence = [
        dict(
            id=q,
            query_id=q,
            tool_status="partial" if old else "ok",
            quality={
                "complete": not old,
                "sample_count": 31,
                **({"reason": "time_precision_reduced"} if old else {}),
            },
        )
        for q in ("D05", "D09")
    ]
    evidence += [
        dict(
            id=f"node-{i}",
            query_id="D06",
            tool_status="ok",
            quality={"complete": True, "sample_count": 25},
        )
        for i in range(5)
    ]
    evidence += [
        dict(
            id="mapping",
            query_id="D08",
            tool_status="empty",
            quality={"complete": True, "sample_count": 0},
        )
    ]
    result = dict(
        result_status="partial",
        termination_reason="missing_data",
        cause_candidates=[],
        recommendations=[],
        missing_inputs=["error_code"],
        limitations=["관측은 원인 확정이 아닙니다."] * 2,
        quality={"analysis": {"status": "complete"}},
    )
    before = copy.deepcopy((result, evidence))
    await write_report(
        result,
        {
            "incident_time": "2026-10-01T00:00:00Z",
            "target": {"cluster_id": "cpc-2", "node": "node-a"},
        },
        {},
        evidence,
        Model(),
    )
    sections = {s["id"]: s["text"] for s in result["narrative"]}
    limits = sections["limits"]
    for query in ("D05", "D06", "D08", "D09"):
        assert limits.count(query + "(") == 1
    assert "5개 구간" in limits and "125" not in limits
    assert (
        "조회 시각 정밀도 축소" in limits
        if old
        else "time_precision_reduced" not in limits
    )
    assert "결과 없음(empty)" in limits and "부분 산출" in limits
    assert "응답 검증은 완료했지만" in limits
    assert limits.count("관측은 원인 확정이 아닙니다.") == 1
    assert "D08(GPU–Pod 할당)" in sections["next"]
    assert "상태 fact로" in sections["next"]
    assert "클러스터 cpc-2 · 노드 node-a" in sections["problem"]
    assert evidence == before[1]
    for key in before[0]:
        if key != "quality":
            assert result[key] == before[0][key]


def test_digit_free_typed_identifiers_are_not_english_prose():
    view = {
        "target": {
            "node": "physically-long-worker-name",
            "pod": "single",
            "namespace": "training",
        }
    }
    ids = identifier_tokens(view)
    assert ids == {"physically-long-worker-name", "single", "training"}
    assert validate_synthesis(
        reply("physically-long-worker-name single training 상태를 확인해야 합니다."),
        ["log"],
        identifiers=ids,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("reduced", [False, True])
async def test_synthesis_uses_query_quality_from_the_model_view(reduced):
    from rcca_agent.synthesis import synthesize

    class Model:
        configured = True

        async def complete(self, system, payload, **kwargs):
            return reply(limitations=["시각 정밀도 손실로 기간 확인이 제한됩니다."])

    payload = {
        "device_observations": [{"evidence_refs": ["log"]}],
        "metric_observations": [],
        "pod_relations": [],
        "observation_refs": ["log"],
        "query_quality": [
            {"quality": {"reason": "time_precision_reduced" if reduced else None}}
        ],
    }
    diagnostics = {}
    status, _, _ = await synthesize(Model(), payload, diagnostics)
    assert status == ("complete" if reduced else "failed")
    assert diagnostics["error_code"] == (None if reduced else "invalid_limitations")
