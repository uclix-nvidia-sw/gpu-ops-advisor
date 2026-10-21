"""Fixed outputs test orchestration and validation, not model accuracy."""

from legacy_review_fixtures import RUBRIC


def review_reply(payload, verdict="undetermined", issues=None):
    status = {
        "acceptable": "pass",
        "revision_required": "needs_revision",
        "undetermined": "undetermined",
    }[verdict]
    return {
        "analysis_id": payload["draft"]["analysis_id"],
        "verdict": verdict,
        "issues": issues or [],
        "followup_questions": [],
        "criteria": {
            key: {
                "status": status,
                "reason": "고정 응답으로 실행 계약을 검증합니다.",
                "evidence_refs": payload["input_evidence_refs"][:1],
            }
            for key in RUBRIC
        },
    }


def interpretation_reply():
    return {key: [] for key in ("findings", "unknowns", "conflicts", "limitations")}
