"""Explain existing exclusions without feeding diagnostics back into calculation."""

from collections import defaultdict


REASONS = {
    "transition_query_budget_reserved": "후속 메모리·작업·문맥 수집과 수집기 검증의 최대 조회 예산을 남기기 위해 연결 변경 검증을 실행하지 않음",
    "transition_query_budget_exhausted": "추가 조회 예산이 소진되어 연결 변경 검증을 실행하지 못함",
    "transition_deadline_exhausted": "검증 시간 한도에 도달하여 연결 변경 검증을 실행하지 못함",
    "base_query_unavailable": "기본 조회 자료가 없어 연결 변경 검증을 실행하지 못함",
    "transition_verification_unavailable": "연결 변경 조회 또는 응답 처리를 완료하지 못함",
    "gpu_identity_unverified": "GPU 신원 수·고유성 또는 동일 노드·모델 조건 불충족",
    "gpu_attribution_unverified": "GPU·노드 라벨 충돌 또는 공유·MIG 귀속 미확인",
    "gpu_interval_unverified": "GPU 시간대의 표본 수·시간 경계·비중복 연속 조건 불충족",
    "pod_identity_missing": "연결 구간에 대응하는 Pod 신원 자료가 없음",
    "pod_uid_unverified": "Pod UID가 없거나 서로 다른 UID가 관측됨",
    "pod_node_unverified": "Pod 노드가 GPU 노드와 다르거나 미배정 구간이 연결 이전에 끝나지 않음",
    "pod_samples_unverified": "Pod 표본 값 또는 수집 간격 조건 불충족",
    "pod_continuity_unverified": "Pod 관측 구간이 겹치거나 연속되지 않음",
    "pod_coverage_unverified": "배정된 Pod 관측이 GPU 연결 구간을 충분히 덮지 못함",
    "pod_interval_unverified": "Pod UID·노드·표본·연결 구간 조건을 확인하지 못함",
    "transition_aggregate_mismatch": "연결 검증 증거와 원래 집계의 값·신원 수가 일치하지 않음",
    "transition_check_unresolved": "추가 조회는 완료했으나 해당 신원의 검증 증거가 확보되지 않음",
    "identity_labels_missing": "GPU·Namespace·Pod·노드·모델 식별 정보 부족",
    "identity_labels_conflict": "GPU·노드 식별 정보 불일치",
    "duplicate_or_changed_gpu_identity": "GPU 연결 변경 또는 중복 여부 미확인",
    "invalid_activity_aggregate": "활동률 집계 검증 실패",
    "pod_identity_unverified": "Pod 신원과 집계 표본 대조 조건 불충족",
    "incomplete_hour_or_sampling_interval": "시간대 표본 수 또는 수집 주기 조건 불충족",
    "shared_or_mig_attribution_unverified": "공유 GPU·MIG 귀속 미확인",
    "unobserved_hour": "시간대 관측 없음",
    "report_query_failed": "기본 집계 조회 실패",
    "report_datasource_unavailable": "자료 조회 경로 미확인",
    "query_unavailable": "기본 집계 조회 불가",
    "report_query_limit_exceeded": "전체 조회 횟수 상한 초과",
    "report_response_limit_exceeded": "조회 자료 크기 상한 초과",
    "report_point_limit_exceeded": "조회 표본 수 상한 초과",
    "invalid_prometheus_matrix": "집계 응답 형식 오류",
    "partial_or_invalid_prometheus_response": "불완전한 집계 응답",
}


def observation_diagnostics(periods, compared, evidence, *, missing_clusters=()):
    """Keep period, row-hour and GPU-hour units distinct; never infer old skip causes."""
    details, messages, collection, summary = [], [], [], []
    unattributed_messages = []
    for cluster in missing_clusters:
        reason = "현재 기간에 선택 범위의 Namespace 귀속 GPU 관측 없음"
        summary.append(reason)
        current_period = next(
            period for role, period, _, _ in periods if role == "current"
        )
        unavailable = any(
            e["cluster_id"] == cluster
            and e["time_range"] == current_period
            and e["query_id"]
            in {
                "hourly_gpu_activity",
                "hourly_pod_identity",
                "hourly_gpu_identity_count",
            }
            and e["tool_status"] != "ok"
            for e in evidence
        )
        detail = (
            "현재 기간 기본 조회가 완료되지 않아 귀속 관측을 확인할 수 없습니다."
            if unavailable
            else "유휴 상태인지 수집 누락인지는 확인하지 않았습니다."
        )
        messages.append(f"{cluster}: {reason}. {detail}")
    for role, period, rows, excluded in periods:
        period_name = "현재 기간" if role == "current" else "이전 기간"
        excluded_by_row = defaultdict(list)
        for item in excluded:
            excluded_by_row[
                tuple(item[k] for k in ("cluster_id", "namespace", "gpu_model"))
            ].append(item)
        audits = {}
        for e in evidence:
            if e["query_id"] != "hourly_gpu_activity" or e["time_range"] != period:
                continue
            quality = e["quality"]
            entries = quality.get("transition_verification", [])
            for entry in entries:
                for gpu in entry["gpu_ids"]:
                    audits[(e["cluster_id"], entry["hour_end"], gpu)] = entry
            if "transition_verification" in quality:
                skipped = defaultdict(set)
                for entry in entries:
                    if entry["status"] == "not_checked":
                        skipped[entry["reason"]].update(
                            (entry["hour_end"], gpu) for gpu in entry["gpu_ids"]
                        )
                collection.append(
                    dict(
                        cluster_id=e["cluster_id"],
                        period_role=role,
                        time_range=period,
                        checked_batches=sum(a["status"] == "checked" for a in entries),
                        failed_batches=sum(
                            a["status"] == "query_failed" for a in entries
                        ),
                        skipped_gpu_hours=None
                        if quality.get("transition_skip_reason")
                        else sum(
                            len(a["gpu_ids"])
                            for a in entries
                            if a["status"] == "not_checked"
                        ),
                        skipped_hours=None
                        if quality.get("transition_skip_reason")
                        else len(
                            {
                                a["hour_end"]
                                for a in entries
                                if a["status"] == "not_checked"
                            }
                        ),
                        skip_reason=quality.get("transition_skip_reason"),
                        skipped_by_reason=[
                            dict(
                                code=code,
                                hours=len({at for at, _ in items}),
                                gpu_hours=len(items),
                            )
                            for code, items in sorted(skipped.items())
                        ],
                        evidence_refs=[e["id"]],
                    )
                )
            if reason := quality.get("transition_skip_reason"):
                summary.append(REASONS[reason])
                messages.append(
                    f"{e['cluster_id']} · {period_name}: {REASONS[reason]}. 검증 대상 시간 수는 확인하지 못했습니다."
                )
        for row in rows:
            if row["quality_status"] == "ready":
                continue
            key = tuple(row[k] for k in ("cluster_id", "namespace", "gpu_model"))
            invalid = {h["end"] for h in row["hours"] if h["activity_percent"] is None}
            reasons = defaultdict(set)
            for h in row["hours"]:
                if h["end"] in invalid:
                    for reason in h["reasons"]:
                        reasons[reason].add(h["end"])
            for item in excluded_by_row[key]:
                at = item["hour_end"]
                if (
                    at not in invalid
                    or not key[1]
                    or item["reason"]
                    not in {
                        "duplicate_or_changed_gpu_identity",
                        "pod_identity_unverified",
                        "incomplete_hour_or_sampling_interval",
                    }
                ):
                    continue
                if item["proof_mismatch"]:
                    reasons["transition_aggregate_mismatch"].add(at)
                audit = audits.get((key[0], at, item["gpu_id"]))
                if not audit:
                    continue
                if audit.get("reason"):
                    reasons[audit["reason"]].add(at)
                else:
                    rejected = [
                        r["reason"]
                        for r in audit.get("rejected", [])
                        if r["gpu_id"] == item["gpu_id"]
                        and (
                            "namespace" not in r
                            or (r["namespace"] == key[1] and r["pod"] == item["pod"])
                        )
                    ]
                    for reason in rejected:
                        reasons[reason].add(at)
                    if (
                        not rejected
                        and not item["proof_mismatch"]
                        and item["reason"] == "duplicate_or_changed_gpu_identity"
                    ):
                        reasons["transition_check_unresolved"].add(at)
            specific_hours = set().union(
                *(
                    hours
                    for code, hours in reasons.items()
                    if code
                    not in {"duplicate_or_changed_gpu_identity", "unobserved_hour"}
                )
            )
            reasons["duplicate_or_changed_gpu_identity"].difference_update(
                specific_hours
            )
            reasons = {code: hours for code, hours in reasons.items() if hours}
            target = (
                f"{key[0]} / {key[1] or 'Namespace 미표기'} / {key[2] or '모델 미확인'}"
            )
            counts = [
                dict(code=code, hours=len(hours), text=REASONS.get(code, code))
                for code, hours in sorted(reasons.items())
            ]
            if key[1]:
                summary.extend(r["text"] for r in counts)
            text = f"{target} · {period_name}: {row['expected_hours']}시간 중 {row['valid_hours']}시간을 활동률에 반영했습니다. "
            text += "; ".join(f"{r['text']} {r['hours']}시간" for r in counts) + "."
            if not key[1]:
                text += " Namespace에 귀속하지 못한 GPU 관측이며 Namespace 활동 판정에는 포함하지 않습니다. 미할당 여부와 전체 GPU 귀속의 완전성은 미확인입니다."
            (messages if key[1] else unattributed_messages).append(text)
            details.append(
                dict(
                    cluster_id=key[0],
                    namespace=key[1],
                    gpu_model=key[2],
                    period_role=role,
                    time_range=period,
                    valid_hours=row["valid_hours"],
                    expected_hours=row["expected_hours"],
                    excluded_hours=len(invalid),
                    reasons=counts,
                    text=text,
                    evidence_refs=row["evidence_refs"],
                )
            )
        if not rows:
            summary.append(f"{period_name} Namespace 활동 관측 없음")
            messages.append(
                f"{period_name}: Namespace 활동을 산출할 관측 행이 없습니다."
            )
    for row in compared:
        if row["namespace"] and row["comparison_status"] in {
            "previous_not_observed",
            "current_not_observed",
        }:
            period_name = (
                "이전"
                if row["comparison_status"] == "previous_not_observed"
                else "현재"
            )
            messages.append(
                f"{row['cluster_id']} / {row['namespace'] or 'Namespace 미표기'} / {row['gpu_model'] or '모델 미확인'}: {period_name} 기간의 대응 관측이 없어 기간 비교를 보류했습니다."
            )
            summary.append(f"{period_name} 기간의 대응 관측이 없어 비교 보류")
        elif (
            row["namespace"] and row["comparison_status"] == "insufficient_observation"
        ):
            current_short = row["valid_hours"] < row["expected_hours"]
            previous_short = (
                row["previous_valid_hours"] < row["previous_expected_hours"]
            )
            short_period = (
                "현재·이전 기간"
                if current_short and previous_short
                else "현재 기간"
                if current_short
                else "이전 기간"
            )
            messages.append(
                f"{row['cluster_id']} / {row['namespace']} / {row['gpu_model'] or '모델 미확인'}: "
                f"현재 {row['valid_hours']}/{row['expected_hours']}시간·"
                f"이전 {row['previous_valid_hours']}/{row['previous_expected_hours']}시간을 확인했으며, "
                f"{short_period}의 관측 시간이 부족해 기간 비교를 보류했습니다."
            )
            summary.append(f"{short_period}의 관측 시간이 부족해 비교 보류")
    if messages:
        messages.append(
            "검증 미실행은 신원 충돌 확인을 뜻하지 않습니다. 제외 사유별 시간은 겹칠 수 있으며, 일부 신원의 검증 성공이 해당 시간 전체의 유효성을 뜻하지는 않습니다."
        )
    return dict(
        version="ops-observation-diagnostics-v4",
        clusters_without_current_attribution=list(missing_clusters),
        unattributed_messages=list(dict.fromkeys(unattributed_messages)),
        messages=list(dict.fromkeys(messages)),
        summary=list(dict.fromkeys(summary)),
        rows=details,
        collection=collection,
    )
