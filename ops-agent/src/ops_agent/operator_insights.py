"""Verified operator checks derived from existing report metrics and DB snapshots."""

from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo


def operator_insights(topic, data, context, db_evidence):
    """Add interpretation without recalculating metrics or asserting remediation."""
    topic_id = topic["topic_id"]
    if topic_id not in {"O01", "O05", "O08", "O11"}:
        return
    topic["quality"]["operator_analysis"] = "1.0"
    metrics = topic["metrics"]
    period = data["time_range"]

    def select(name):
        return [m for m in metrics if m["id"].split(".")[1] == name]

    def label(target):
        return (
            " / ".join(
                str(target[k])
                for k in (
                    "cluster_id",
                    "namespace",
                    "node",
                    "gpu_uuid",
                    "model",
                    "job",
                    "instance",
                )
                if target.get(k)
            )
            or "선택 범위"
        )

    def clock(span):
        zone = ZoneInfo(data.get("timezone", "Asia/Seoul"))
        return " ~ ".join(
            datetime.fromisoformat(span[k].replace("Z", "+00:00"))
            .astimezone(zone)
            .strftime("%Y-%m-%d %H:%M")
            for k in ("start", "end")
        )

    def add(
        category, priority, text, next_check, rows, *, target=None, span=None, **extra
    ):
        topic["findings"].append(
            dict(
                id=f"{topic_id}.check.{len(topic['findings'])}",
                category=category,
                priority=priority,
                text=text,
                next_check=next_check,
                target=target if target is not None else data["scope"],
                period=span if span is not None else period,
                value_refs=list(dict.fromkeys(m["id"] for m in rows)),
                evidence_refs=list(
                    dict.fromkeys(ref for m in rows for ref in m["evidence_refs"])
                ),
                **extra,
            )
        )

    if topic_id == "O08":
        grouped = defaultdict(lambda: dict(hourly=[], lows=[]))
        for name, field in (
            ("hourly_gpu_activity", "hourly"),
            ("observed_low_activity_seconds", "lows"),
        ):
            for m in select(name):
                target = m["target"]
                grouped[
                    (
                        target.get("cluster_id"),
                        target.get("namespace"),
                        target.get("model"),
                    )
                ][field].append(m)
        for key, group in sorted(grouped.items(), key=str):
            target = dict(zip(("cluster_id", "namespace", "model"), key))
            hourly = group["hourly"]
            valid = [m for m in hourly if m["value"] is not None]
            gaps = [m for m in hourly if m["value"] is None]
            lows = group["lows"]
            if lows:
                longest = max(lows, key=lambda m: m["value"])
                count = len({m["target"]["gpu_uuid"] for m in lows})
                add(
                    "low_activity",
                    2,
                    f"{label(target)}: GPU {count}대에서 5% 미만 활동이 30분 이상 이어진 구간 {len(lows)}건이 관측됐습니다. "
                    f"가장 긴 구간은 {clock(longest['period'])} ({longest['value'] / 60:g}분, {longest['target']['gpu_uuid']})입니다.",
                    "표시된 시간대의 작업 실행·대기·예약 목적을 확인하세요. 일부 GPU의 저활동이며 Namespace 전체의 유휴나 회수 가능성을 뜻하지 않습니다.",
                    lows,
                    target=target,
                    span=longest["period"],
                )
            elif valid:
                add(
                    "no_sustained_low_activity",
                    5,
                    f"{label(target)}: 유효 관측에서 5% 미만·30분 이상 연속 저활동 구간은 확인되지 않았습니다.",
                    "시간대별 활동률과 GPU 연결 대수를 함께 확인하세요. 관측되지 않은 구간과 제외된 GPU까지 정상이라는 의미는 아닙니다.",
                    valid,
                    target=target,
                )
            if valid:
                peak = max(valid, key=lambda m: m["value"])
                lowest = min(valid, key=lambda m: m["value"])
                if peak["value"] > lowest["value"]:
                    add(
                        "activity_pattern",
                        4,
                        f"{label(target)}: 같은 모델의 시간대별 평균 활동률은 {lowest['value']:.1f}% ~ {peak['value']:.1f}%입니다. "
                        f"가장 높은 시간대는 {clock(peak['period'])}입니다.",
                        "활동이 집중된 시간대의 작업 일정과 동시 연결 GPU 대수를 대조하세요. 평균값만으로 자원 부족이나 낭비를 판정하지 않습니다.",
                        [lowest, peak],
                        target=target,
                        span=peak["period"],
                    )
            if gaps:
                add(
                    "activity_gap",
                    1,
                    f"{label(target)}: 활동률을 계산하지 못한 시간 구간이 {len(gaps)}개 있습니다. 저활동과 구분해야 합니다.",
                    "해당 시간대에 연결 GPU가 있었는지 확인하고, GPU–Pod 신원 연결·공유·모델 충돌·수집 누락 사유를 대조하세요.",
                    gaps,
                    target=target,
                )
        if not grouped:
            add(
                "insufficient_evidence",
                1,
                "Namespace별 사용 패턴을 판단할 유효 GPU 연결·활동 자료가 없습니다.",
                "GPU 활동 표본과 Pod 신원 연결의 수집·누락 사유를 확인하세요. 자료 없음은 사용량 0이 아닙니다.",
                metrics,
            )

    elif topic_id == "O01":
        conditions = select("node_condition_seconds")
        attention = [
            m
            for m in conditions
            if m["value"] is not None
            and m["value"] > 0
            and (
                (
                    m["target"]["condition"] == "Ready"
                    and m["target"]["status"].lower() in {"false", "unknown"}
                )
                or (
                    m["target"]["condition"]
                    in {
                        "MemoryPressure",
                        "DiskPressure",
                        "PIDPressure",
                        "NetworkUnavailable",
                    }
                    and m["target"]["status"].lower() == "true"
                )
            )
        ]
        by_node = defaultdict(list)
        for m in attention:
            by_node[(m["target"]["cluster_id"], m["target"]["node"])].append(m)
        for key, rows in sorted(by_node.items()):
            target = dict(zip(("cluster_id", "node"), key))
            observed = "; ".join(
                f"{m['target']['condition']}={m['target']['status']} 누적 {m['value'] / 60:g}분"
                for m in rows
            )
            add(
                "node_attention",
                2,
                f"{label(target)}: 분석 기간의 Node 조건에 {observed}이 기록됐습니다.",
                "해당 Node의 상태 변화·이벤트를 대조하세요. 누적 관측이며 현재 장애나 GPU 고장을 확정하지 않습니다.",
                rows,
                target=target,
            )
        if not attention:
            valid = [m for m in conditions if m["value"] is not None]
            add(
                "node_observation_scope" if valid else "insufficient_evidence",
                5 if valid else 1,
                "관측된 Node 조건에서 Ready=false/unknown 또는 Pressure·NetworkUnavailable=true 기록은 확인되지 않았습니다."
                if valid
                else "Node 점검 대상을 판단할 유효 상태 관측이 없습니다.",
                "관측 범위와 자료 누락을 확인하세요. 이 결과만으로 모든 Node·GPU가 정상이라고 판정하지 않습니다.",
                conditions,
            )
        records = [
            m
            for m in metrics
            if m.get("quality", {}).get("measurement_time_verified") is False
        ]
        if records:
            add(
                "equipment_record_limit",
                5,
                "GPU 메모리·온도는 기간 내 마지막 기록값이며 실제 측정 시각이 확인되지 않았습니다.",
                "이 값만으로 현재 과열·메모리 부족을 판단하지 마세요. 점검할 장비의 실제 측정 시각과 유효 시계열을 확인하세요.",
                records,
            )

    elif topic_id == "O05":
        incidents = {i["id"]: i for i in context.get("incidents", [])}
        counts = select("incident_count")
        if not incidents:
            add(
                "no_incidents",
                5,
                "분석 기간 안에 발생해 저장된 사건은 없습니다.",
                "기간 이전부터 이어진 사건과 미수신 알람은 이 집계에 포함되지 않습니다. 장애가 전혀 없었다는 판정은 아닙니다.",
                counts,
            )
        for incident_id, incident in sorted(
            incidents.items(),
            key=lambda pair: (pair[1].get("occurred_at", ""), pair[0]),
        ):
            linked = [
                r
                for r in context.get("rca_results", [])
                if r.get("body", {}).get("incident_id") == incident_id
            ]
            actions = [
                a
                for a in context.get("actions", [])
                if a.get("body", {}).get("subject_type") == "incident"
                and a["body"].get("subject_id") == incident_id
            ]
            state = incident.get("alarm_status")
            status_text = {"firing": "알람 발생 중", "resolved": "알람 해제"}.get(
                state, "알람 상태 미확인"
            )
            target = {
                **(incident.get("target") or {}),
                "cluster_id": incident["cluster_id"],
            }
            symptom = str(
                target.get("title") or incident.get("symptom") or "등록된 사건"
            ).strip()[:200]
            if state == "firing":
                check = (
                    "최신 알람 상태를 확인한 뒤 공개 RCA의 확인 조건과 연결된 조치 후 확인 기록을 대조하세요."
                    if linked
                    else "최신 알람 상태를 확인한 뒤 RCA 조사 작업의 진행·실패 여부와 결과 발행 상태를 확인하세요."
                )
            elif state == "resolved":
                check = "알람이 해제된 뒤 장비·작업이 정상으로 돌아왔는지 실제 상태와 조치 후 확인 기록으로 검증하세요."
            else:
                check = "사건의 최신 알람 수신·해제 기록을 먼저 확인한 뒤 RCA 조사 상태와 조치 기록을 대조하세요."
            add(
                "incident_followup",
                2 if state == "firing" else (4 if state == "resolved" else 3),
                f"{label(target)} / 접수된 증상: {symptom}. 저장 시점 기준 {status_text}, 공개 RCA {len(linked)}건, 연결된 조치 기록 {len(actions)}건입니다.",
                check
                + " 알람 해제·분석 완료·조치 기록은 각각 별개이며 복구 완료를 뜻하지 않습니다.",
                counts,
                target=target,
                span={"at": incident.get("occurred_at", period["start"])},
                incident_id=incident_id,
                alarm_status=state or "unknown",
                status_as_of=context.get("data_cutoff_at"),
                rca_result_ids=[r["result_id"] for r in linked],
                action_record_ids=[a["id"] for a in actions],
            )
            topic["findings"][-1]["evidence_refs"] = [db_evidence["id"]]

    elif topic_id == "O11":
        targets = defaultdict(list)
        for name in ("target_down_seconds", "target_unknown_seconds"):
            for m in select(name):
                if m["value"] is not None and m["value"] > 0:
                    targets[tuple(sorted(m["target"].items()))].append(m)
        for key, rows in sorted(targets.items()):
            target = dict(key)
            durations = {m["id"].split(".")[1]: m["value"] for m in rows}
            add(
                "collection_gap",
                1,
                f"{label(target)}: 수집 실패 {durations.get('target_down_seconds', 0) / 60:g}분, "
                f"미관측 {durations.get('target_unknown_seconds', 0) / 60:g}분이 있습니다.",
                "해당 수집 대상과 관측 공백을 먼저 확인하세요. 영향을 받는 시간대의 낮은 활동·이상 없음 결론은 보류해야 합니다.",
                rows,
                target=target,
            )
        if not targets:
            ups = [m for m in select("target_up_seconds") if m["value"] is not None]
            add(
                "collection_scope" if ups else "insufficient_evidence",
                5 if ups else 1,
                "관측된 수집 대상에서는 실패·미관측 시간이 계산되지 않았습니다."
                if ups
                else "수집 대상별 정상·실패·미관측 시간을 판단할 자료가 없습니다.",
                "기대 수집 대상 목록이 없으므로 전체 장비 수집 완료를 보장하지 않습니다. 누락 대상이 없는지 확인하세요.",
                ups or metrics,
            )

    if (
        topic_id in {"O01", "O08"}
        and topic["missing_inputs"]
        and not any(
            f.get("category") in {"insufficient_evidence", "activity_gap"}
            for f in topic["findings"]
        )
    ):
        add(
            "analysis_limit",
            3,
            "일부 관측이나 계산 조건이 부족해 이 주제의 결과는 확인된 범위에 한정됩니다.",
            "상세의 자료 부족 사유와 제외된 대상을 확인하세요. 확인된 결과를 전체 장비·전체 시간으로 확대하지 마세요.",
            [m for m in metrics if m["value"] is None],
        )
