"""Offline transition proposals; never approve, publish or contact a service."""

from copy import deepcopy
import argparse
import json
from pathlib import Path

from agent_common.contracts import content_hash


CONTEXT_PURPOSES = {
    "D02": (
        "사건 범위의 GPU 활동을 보조 관측합니다. 노드 범위로 수집했다면 오류 장치와의 연결은 미확인으로 유지하며, "
        "사용률만으로 GPU·NVSwitch·노드의 고장, 접근 가능성 또는 복구를 판단하지 않습니다."
    ),
    "D03": "같은 GPU의 메모리 사용량을 보조 관측합니다. 메모리 오류나 복구의 직접 증거가 아닙니다.",
    "D04": "같은 GPU의 온도 원본을 보조 관측합니다. 모델별 기준과 시각 확인 없이 과열 원인을 확정하지 않습니다.",
    "D11": "같은 GPU의 소비 전력 원본을 보조 관측합니다. 전원 연결 상태나 전원 고장의 직접 증거가 아닙니다.",
    "D33": "같은 GPU의 해당 ECC 원본 카운터를 보조 관측합니다. 누적값을 이번 사건의 증가량으로 해석하지 않습니다.",
    "D34": "같은 GPU의 해당 ECC 원본 카운터를 보조 관측합니다. 카운터 종류·초기화·시각을 확인해야 합니다.",
    "D44": "같은 GPU의 PCIe replay 원본 카운터를 보조 관측합니다. AER 원문이나 PCIe 고장 판정을 대신하지 않습니다.",
}


def propose_transition(row):
    """Preserve authored semantics and expose holds instead of inventing a decoder."""
    candidate = {
        key: deepcopy(row[key])
        for key in (
            "knowledge_key",
            "kind",
            "visibility",
            "scope",
            "compatibility",
            "source_refs",
            "content",
        )
    }
    content = candidate["content"]
    category = content.get("classification", {}).get("category")
    holds = []
    if "content_hash" in row and (
        row["content_hash"] != content_hash(content)
        or row.get("reviewed_content_hash") != row["content_hash"]
    ):
        holds.append("source_hash_mismatch")
    if category in {"unresolved_code", "informational"}:
        holds.append("code_meaning_or_auxiliary_relevance_requires_review")
    if not content.get("sources"):
        holds.append("source_missing")
    steps = content.get("observation_plan", [])
    optional = [s for s in steps if not s["required"]]
    if any(s["query_id"] not in CONTEXT_PURPOSES for s in optional):
        holds.append("unsupported_auxiliary_query")
    if content.get("operator_guidance") or any(s.get("selection") for s in optional):
        holds.append("existing_structured_content_requires_merge_review")
    if holds:
        return None, {"status": "held", "reasons": holds}

    prerequisites = (
        ["observations"]
        if category == "general_investigation"
        else ["reported_error_code", "reported_producer_contract"]
    )
    for step in optional:
        # These queries provide context, not the missing causal fact itself.
        step["selection"] = {
            "missing_any": ["causal_confirmation_evidence", "normalized_health"],
            "requires_all": prerequisites.copy(),
            "independent": True,
        }
        step["purpose"] = CONTEXT_PURPOSES[step["query_id"]]
    if category == "general_investigation":
        # Explicit rules replace the broad unknown_value-triggered query policy.
        content["unexpected_evidence"]["additional_queries"] = []
    content["limitations"].append(
        "RCA는 GPU·NVSwitch·노드 조사 범위입니다. Pod·워크로드 조회를 추가하지 않습니다. "
        "보조 관측 성공은 오류 장치 연결·현재 상태·원인 확인의 조건을 자동 충족하지 않습니다."
    )
    return candidate, {
        "status": "proposal_requires_semantic_review",
        "before_content_hash": content_hash(row["content"]),
        "after_content_hash": content_hash(content),
        "queries": [s["query_id"] for s in optional],
        "remaining_review": [
            "query_relevance_for_this_code",
            "operator_guidance_and_source_applicability",
            "deployed_profile_compatibility",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from .runbook_admin import check

    profile = json.loads(args.profile.read_text("utf-8"))
    latest = {}
    for row in json.loads(args.snapshot.read_text("utf-8")):
        if row.get("kind") != "runbook" or row.get("state") != "published":
            continue
        key = row["knowledge_key"]
        if key not in latest or row["revision"] > latest[key]["revision"]:
            latest[key] = row
    # Exclusive output directory prevents stale proposals surviving a later hold.
    args.output.mkdir(parents=True, exist_ok=False)
    reviews = []
    for key, row in sorted(latest.items()):
        candidate, review = propose_transition(row)
        review.update(knowledge_key=key, base_revision=row["revision"])
        if candidate:
            check(candidate, profile, runtime=True)
            # Use a hash as filename; knowledge keys are untrusted file input.
            name = content_hash(candidate["content"]) + ".json"
            (args.output / name).write_text(
                json.dumps(candidate, ensure_ascii=False, indent=2), "utf-8"
            )
            review.update(
                proposal_file=name, contract="passed_against_supplied_profile"
            )
        reviews.append(review)
    (args.output / "review.json").write_text(
        json.dumps(
            {"status": "not_approved_not_published", "entries": reviews},
            ensure_ascii=False,
            indent=2,
        ),
        "utf-8",
    )


if __name__ == "__main__":
    main()
