"""Synthetic replay cases; scripted verdicts test contracts, not model quality."""

from copy import deepcopy
import json
from pathlib import Path

from agent_common.contracts import content_hash
from legacy_review_fixtures import RUBRIC, analysis_draft


ROOT = Path(__file__).resolve().parents[2]
PERIOD = {"start": "2026-09-15T00:00:00Z", "end": "2026-09-15T00:01:00Z"}


def reply(value, **extra):
    return {"response": value, "usage": {"total_tokens": 1000}, **extra}


def review(verdict="acceptable"):
    status = {
        "acceptable": "pass",
        "undetermined": "undetermined",
        "revision_required": "needs_revision",
    }[verdict]
    refs = {"$input": "/input_evidence_refs"}
    return {
        "analysis_id": {"$input": "/draft/analysis_id"},
        "verdict": verdict,
        "issues": [],
        "followup_questions": [],
        "criteria": {
            key: {
                "status": status,
                "reason": "고정 응답: 참조와 실행 계약 검사이며 의미 품질 측정이 아닙니다.",
                "evidence_refs": refs,
            }
            for key in RUBRIC
        },
    }


def workflow_case():
    profile = json.loads(
        (ROOT / "agents/tests/fixtures/config-v7.json").read_text(encoding="utf-8")
    )
    profile["clusters"] = {
        "c": {
            "loki_uid": "logs",
            "loki_selector": {},
            "mimir_uid": "metrics",
            "metric_selector": {},
        }
    }
    profile["health_contracts"] = {
        "fixture": {
            "producer_contract": "fixture",
            "revision": "fixture-v1",
            "checks": {"valid": "valid"},
            "health": {
                "Degraded": {"normalized_health": "degraded", "severity": "warning"}
            },
        }
    }
    profile["queries"]["D09"]["max_hold_seconds"] = 60
    book = json.loads(
        (ROOT / "rcca-agent/runbooks/RB-GENERAL-GPU-NODE.json").read_text(
            encoding="utf-8"
        )
    )
    content = book["content"]
    # Keep optional queries available, but no permission to collect in the single-round case.
    content["unexpected_evidence"].update(additional_queries=[], fallback="stop")
    book = dict(
        id="fixture-general-revision",
        knowledge_key=book["knowledge_key"],
        revision=1,
        compatibility={"cluster_id": "c"},
        content=content,
        content_hash=content_hash(content),
        reviewed_content_hash=content_hash(content),
    )
    data = dict(
        incident_id="00000000-0000-4000-8000-000000000001",
        evidence_version=1,
        incident_time=PERIOD["start"],
        time_range=PERIOD,
        scope={"clusters": [{"cluster_id": "c", "namespaces": None}]},
        target={"gpu_uuid": "GPU-1"},
        purpose_ids=["R01"],
        incident_snapshot={"evidence": {}},
    )
    raw = dict(
        producer_contract="fixture",
        health="Degraded",
        check_status="valid",
        target=data["target"],
        component="gpu",
        observed_at=PERIOD["start"],
    )
    interpretation = {
        "findings": [
            {
                "id": "finding-1",
                "statement": "장비 상태 보고가 있습니다. 원인은 미확정입니다.",
                "kind": "observed",
                "evidence_refs": {"$input": "/observation_refs"},
            }
        ],
        "unknowns": [],
        "conflicts": [],
        "limitations": [],
    }
    synthesis = {
        "hypotheses": [
            {
                "claim": "관측한 장비 증상은 추가 확인이 필요합니다.",
                "supporting_refs": {"$input": "/observation_refs"},
                "contradicting_refs": [],
                "missing_inputs": ["producer_confirmation"],
            }
        ],
        "limitations": [],
    }
    return {
        "schema": "rca-replay/1",
        "id": "enough_budget",
        "data_origin": "synthetic",
        "mode": "workflow",
        "expectations": {
            "description": "해석·분석·검토를 완료해도 원인 확정으로 바꾸지 않는다.",
            "critical_loss": "해석 또는 근거 참조 손실, 검토 누락",
            "repetitions": 1,
        },
        "token_budget": 200000,
        "output_caps": {"default": 4096, "synthesis": 16384},
        "attempt": {
            "claim": {
                "job_id": "00000000-0000-4000-8000-000000000002",
                "kind": "rca",
                "input": data,
                "versions": {},
            },
            "profile": profile,
            "context": {
                "data_cutoff_at": PERIOD["end"],
                "runbooks": [book],
                "incidents": [],
            },
        },
        "queries": [
            {
                "tool": "query_loki_logs",
                "arguments": {
                    "datasourceUid": "logs",
                    "logql": "{}",
                    "startRfc3339": PERIOD["start"],
                    "endRfc3339": PERIOD["end"],
                    "limit": 4999,
                    "direction": "forward",
                },
                "response": {
                    "data": {
                        "result": [
                            {
                                "stream": {},
                                "values": [["1789430400000000000", json.dumps(raw)]],
                            }
                        ]
                    }
                },
            },
            {
                "tool": "query_prometheus",
                "arguments": {
                    "datasourceUid": "metrics",
                    "expr": 'DCGM_FI_DEV_GPU_UTIL{UUID="GPU-1"}[61s]',
                    "queryType": "instant",
                    "endTime": PERIOD["end"],
                },
                "response": {
                    "data": {
                        "result": [
                            {
                                "metric": {"UUID": "GPU-1"},
                                "values": [[1789430400, "2"], [1789430430, "2"]],
                            }
                        ]
                    }
                },
            },
        ],
        "responses": {
            "evidence_interpretation": [reply(interpretation)] * 2,
            "synthesis": [reply(synthesis)] * 2,
            "analysis_review": [reply(review())] * 2,
            "report_writing": [{**reply({}), "compose_sources": True}],
        },
    }


def cases():
    enough = workflow_case()
    short = deepcopy(enough)
    short.update(id="insufficient_budget", token_budget=100)
    short["expectations"]["description"] = (
        "호출 전 예산 부족을 기록하고 검토 통과로 바꾸지 않는다."
    )
    partial = deepcopy(enough)
    partial["id"] = "interpretation_only"
    partial["expectations"]["description"] = (
        "분석 출력이 잘려도 검증된 해석과 실패 사유는 남는다."
    )
    partial["responses"]["synthesis"] = [reply({}, finish_reason="length")] * 2
    followup = deepcopy(enough)
    followup["id"] = "followup_changes_review"
    followup["expectations"]["description"] = (
        "첫 검토는 판단 불가, 명시 규칙으로 D02 수집 후 두 번째 검토는 타당."
    )
    book = followup["attempt"]["context"]["runbooks"][0]
    book["content"]["unexpected_evidence"]["additional_queries"] = ["D02"]
    book["content"]["observation_plan"][1]["selection"] = {
        "missing_any": ["causal_confirmation_evidence"],
        "requires_all": ["observations"],
        "independent": True,
    }
    book.update(
        content_hash=content_hash(book["content"]),
        reviewed_content_hash=content_hash(book["content"]),
    )
    followup["responses"]["analysis_review"] = [
        reply(review("undetermined")),
        reply(review()),
    ]
    accepted = deepcopy(followup)
    accepted["id"] = "accepted_rule_followup"
    accepted["expectations"]["description"] = (
        "품질 검토 통과 뒤에도 명시 규칙 조회는 실행하는 현재 기준선을 보존한다."
    )
    accepted["responses"]["analysis_review"] = [reply(review())] * 2
    result = {case["id"]: case for case in (enough, short, partial, followup, accepted)}
    for name, statement, criterion, source in (
        (
            "limited",
            "오류 보고는 확인했으나 원인은 미확정입니다.",
            None,
            "GPU-A: 오류 보고. 원인 정보 없음.",
        ),
        (
            "overclaim",
            "드라이버가 오류의 원인입니다.",
            "grounding",
            "GPU-A: 오류 보고. 원인 정보 없음.",
        ),
        (
            "typo",
            "GPU.A와 GPU-A는 같은 장비입니다.",
            "identity_time",
            "로그에는 GPU.A, 알람에는 GPU-A. 연결 근거 없음.",
        ),
        (
            "gap",
            "관측이 없는 시간에도 장비는 정상입니다.",
            "limitations",
            "00:00 정상 보고. 00:01~00:30은 수집 공백.",
        ),
        (
            "conflict",
            "동일 시각의 모든 보고는 정상입니다.",
            "contradictions",
            "같은 대상·시각의 정상 보고와 오류 보고가 함께 있음.",
        ),
        (
            "unused",
            "오류 보고가 없어 아무것도 알 수 없습니다.",
            "evidence_use",
            "GPU-A의 오류 보고가 존재. 원인은 미확정.",
        ),
    ):
        view = {
            "input_evidence_refs": ["log"],
            "observation_refs": ["log"],
            "raw_excerpts": [{"text": source, "evidence_refs": ["log"]}],
            "context_selection": {},
        }
        draft = analysis_draft(
            [
                dict(
                    id="analysis-1",
                    claim=statement,
                    causal_status="candidate",
                    supporting_refs=["log"],
                    contradicting_refs=[],
                )
            ],
            [],
            ["현재 상태와 원인은 미확정입니다."],
            view,
        )
        response = review()
        if criterion:
            response["verdict"] = "revision_required"
            response["criteria"][criterion]["status"] = "needs_revision"
            response["issues"] = [
                {
                    "claim_id": "cause:analysis-1",
                    "reason": "원문이 허용하는 범위를 넘어섰습니다.",
                    "evidence_refs": ["log"],
                    "suggested_resolution": "확인된 보고와 미확정 부분을 구분하세요.",
                }
            ]
        case = {
            "schema": "rca-replay/1",
            "id": "review_" + name,
            "mode": "review",
            "data_origin": "synthetic",
            "expectations": {
                "verdict": response["verdict"],
                "criterion": criterion,
                "reason": source,
                "evidence_refs": ["log"],
                "repetitions": 1,
                "semantic_label_status": "proposed_not_human_adjudicated",
            },
            "token_budget": 100000,
            "output_caps": enough["output_caps"],
            "draft": draft,
            "view": view,
            "allowed_queries": [],
            "responses": {"analysis_review": [reply(response)]},
        }
        result[case["id"]] = case
    return result
