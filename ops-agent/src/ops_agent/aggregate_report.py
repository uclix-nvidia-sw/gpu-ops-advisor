"""Daily/weekly Ops report: dedicated collection, calculations and evidence."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from agent_common.contracts import base_result, metric, result_status
from agent_common.observation import evidence_stamp
from agent_common.runtime import attempt_context
from agent_common.llm import explain

from . import incident_summary, namespace_summary
from .report_contract import MAX_BYTES, VERSION, previous_period, validate
from .report_queries import ReportQueries


def topic(name, refs):
    return dict(
        topic_id=name,
        status="blocked",
        metrics=[],
        findings=[],
        facts=[],
        recommendations=[],
        evidence_refs=refs,
        missing_inputs=[],
        quality={"calculation_version": VERSION},
    )


def build_result(claim, context, evidence):
    data, previous = claim["input"], previous_period(claim["input"])
    result = base_result(claim, context["data_cutoff_at"])
    topics = []
    for name in data["topic_ids"]:
        inputs = [
            e
            for e in evidence
            if (e["query_id"] == "report_incident_snapshot")
            == (name == "incident_summary")
        ]
        refs = [e["id"] for e in inputs]
        t = topic(name, refs)

        def put(name, value, unit, target=None, period=None):
            m = metric(
                f"{t['topic_id']}.{name}.{len(t['metrics'])}",
                value,
                unit,
                data,
                refs,
                "observed_sample_aggregate_v1",
                "insufficient_observation" if value is None else None,
            )
            if target is not None:
                m["target"] = target
            if period is not None:
                m["period"] = period
            t["metrics"].append(m)
            return m["id"]

        if name == "namespace_usage":
            current, errors = namespace_summary.summarize(
                [e for e in inputs if e["time_range"] == data["time_range"]],
                data["time_range"],
            )
            before, old_errors = namespace_summary.summarize(
                [e for e in inputs if e["time_range"] == previous], previous
            )
            rows = namespace_summary.compare(current, before)
            t["rows"] = rows
            t["missing_inputs"] = sorted(set(errors + old_errors))
            for i, row in enumerate(rows):
                target = {k: row[k] for k in ("cluster_id", "namespace", "gpu_model")}
                target["model"] = target.pop("gpu_model")
                ids = [
                    put("activity_percent", row["activity_percent"], "percent", target),
                    put(
                        "observed_gpu_count",
                        row["observed_gpu_count"],
                        "physical_gpu",
                        target,
                    ),
                    put(
                        "previous_activity_percent",
                        row["previous_activity_percent"],
                        "percent",
                        target,
                        previous,
                    ),
                    put(
                        "change",
                        row["change_percentage_points"],
                        "percentage_points",
                        target,
                    ),
                ]
                for hour in row["hours"]:
                    put(
                        "hourly_activity",
                        hour["activity_percent"],
                        "percent",
                        target,
                        {"start": hour["start"], "end": hour["end"]},
                    )
                scope = f"{row['cluster_id']} / {row['namespace'] or 'Namespace 미표기'} / {row['gpu_model'] or '모델 미확인'}"
                if row["activity_percent"] is None:
                    text = (
                        f"{scope}: 신원·관측 조건이 부족해 활동률 판단을 보류했습니다."
                    )
                else:
                    text = f"{scope}: 확인된 {row['valid_hours']}개 시간대의 관측 표본 평균 활동률은 {row['activity_percent']:.2f}%입니다."
                    if row["change_percentage_points"] is not None:
                        text += f" 직전 같은 기간보다 {row['change_percentage_points']:+.2f}%p 변했습니다."
                    if row["low_activity_hours"] is not None:
                        text += f" 시간대 평균 5% 미만은 {row['low_activity_hours']}개 시간대입니다. 연속 저활동 시간이나 회수 가능량은 아닙니다."
                windows = row.get("low_activity_windows", [])
                summary_text = text
                if windows:

                    def kst(value):
                        return (
                            datetime.fromisoformat(value.replace("Z", "+00:00"))
                            .astimezone(timezone(timedelta(hours=9)))
                            .strftime("%m/%d %H:%M")
                        )

                    text += " 낮은 시간대: " + ", ".join(
                        kst(w["start"]) + "~" + kst(w["end"]) for w in windows[:3]
                    )
                    if len(windows) > 3:
                        text += f" 외 {len(windows) - 3}개 구간"
                    text += ". 시간대 평균의 묶음이며 구간 내 모든 순간의 저활동을 뜻하지 않습니다."
                t["findings"].append(
                    {
                        "id": f"namespace-pattern-{i}",
                        "target": target,
                        "text": text,
                        "summary_text": summary_text,
                        "evidence_refs": refs,
                        "value_refs": ids,
                    }
                )
            t["status"] = (
                "ready"
                if rows
                and all(
                    r["quality_status"] == "ready"
                    and r["comparison_status"] == "comparable"
                    for r in rows
                )
                and not t["missing_inputs"]
                else "partial"
                if any(r["activity_percent"] is not None for r in rows)
                else "blocked"
            )
            if not rows:
                t["missing_inputs"].append("namespace_observations_missing")
        else:
            summary = incident_summary.summarize(context)
            t["summary"] = summary
            ids = [
                put("count", summary["count"], "events"),
                put(
                    "previous_count",
                    summary["previous_count"],
                    "events",
                    period=previous,
                ),
                put("change", summary["change"], "events"),
            ]
            t["status"] = summary["status"]
            if summary["count"] is None:
                t["missing_inputs"] = [summary["reason"]]
                text = "사건 조회 상한을 넘어 건수와 증감 판단을 보류했습니다."
            else:
                repeated = sum(g["count"] > 1 for g in summary["groups"])
                text = f"기간 내 저장된 사건은 {summary['count']}건이며 직전 기간보다 {summary['change']:+d}건 변했습니다. 같은 GPU UUID·동일 증상으로 묶인 반복 그룹은 {repeated}개입니다. 알림 상태는 보고서 작성 시점 기준이며 RCA 완료·복구 완료와 다릅니다."
            t["findings"].append(
                {
                    "id": "incident-period-summary",
                    "text": text,
                    "evidence_refs": refs,
                    "value_refs": ids,
                }
            )
            for i, group in enumerate(
                sorted(summary.get("groups", []), key=lambda g: -g["count"])[:3]
            ):
                if group["count"] < 2:
                    continue
                t["findings"].append(
                    {
                        "id": f"incident-repeat-{i}",
                        "text": f"{group['cluster_id']} / {group['gpu_uuid']}: 같은 증상 ‘{group['symptom']}’의 사건이 이번 기간 {group['count']}건, 이전 기간 {group['previous_count']}건입니다. 반복 발생 여부를 기존 조사와 함께 확인하세요. 원인이 같다고 판정한 것은 아닙니다.",
                        "evidence_refs": refs,
                        "value_refs": ids,
                    }
                )
        topics.append(t)
    result.update(
        topics=topics,
        result_status=result_status(topics),
        evidence_refs=[e["id"] for e in evidence],
        comparison_range=previous,
        limitations=[
            "활동률은 Namespace에 연결된 GPU의 관측 표본 평균이며 독점 소비량·할당 효율이 아닙니다.",
            "GPU·Pod 신원과 관측 중복을 시간대 단위로 검사합니다. 미관측은 0%가 아닙니다. 공유 설정 이력은 확인하지 않으므로 독점 사용을 보장하지 않습니다.",
            "수집 주기는 15초 계약이며 불완전한 시간대와 다른 수집 주기는 비교에서 제외합니다.",
            "사건 반복은 저장된 UUID와 동일 증상 기준입니다. 원인을 재분석하거나 조치를 수행하지 않습니다.",
        ],
    )
    result["quality"].update(
        report_format=VERSION,
        calculation_version=VERSION,
        sampling_interval_seconds=15,
        low_activity_threshold_percent=5,
        bucket_seconds=3600,
    )
    if len(json.dumps(result, ensure_ascii=False).encode()) > MAX_BYTES:
        raise ValueError("report_result_limit_exceeded")
    return result


async def run(tools):
    ctx = attempt_context.get()
    claim, data, context = ctx["claim"], ctx["claim"]["input"], ctx["context"]
    validate(data)
    evidence = []
    collector = ReportQueries(tools, data, ctx["deadline"])
    if "namespace_usage" in data["topic_ids"]:
        for cluster in data["scope"]["clusters"]:
            for period in (data["time_range"], previous_period(data)):
                evidence.extend(await collector.collect(cluster, period))
    if "incident_summary" in data["topic_ids"]:
        evidence.append(
            dict(
                id=str(uuid4()),
                query_id="report_incident_snapshot",
                query_version=VERSION,
                cluster_id=None,
                scope=data["scope"],
                time_range=data["time_range"],
                input={
                    "comparison_range": previous_period(data),
                    "data_cutoff_at": context["data_cutoff_at"],
                },
                tool_status="ok",
                quality={"repeatable_read": True},
                snapshot=context,
                **evidence_stamp(),
            )
        )
    task = asyncio.create_task(
        asyncio.to_thread(build_result, claim, context, evidence)
    )
    try:
        result = await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise
    statements = [
        f
        for t in sorted(
            result["topics"], key=lambda t: t["topic_id"] != "incident_summary"
        )
        for f in t["findings"]
    ]
    # Keep model input bounded. All calculated findings remain visible in the topic.
    editorial = {
        "facts": statements[:30],
        "limitations": [],
        "narrative_status": "omitted",
    }
    try:
        await explain(
            editorial,
            ctx["llm"],
            'Choose up to three supplied operational findings, prioritizing period changes and repeated incidents. Return JSON {"fact_ids": [ids]}. Select IDs only; do not infer causes or allocation policy.',
        )
    except (ValueError, TypeError, KeyError):
        editorial["narrative_status"] = "failed"
    selected = editorial.get("narrative") or statements[:3]
    result["narrative"] = [
        {
            **s,
            "title": "사용 패턴과 변화"
            if s["id"].startswith("namespace")
            else "사건과 반복 현황",
        }
        for s in selected[:3]
    ]
    result["narrative_status"] = editorial["narrative_status"]
    result["quality"]["report"] = {
        "status": "complete",
        "method": "llm_prioritized"
        if editorial["narrative_status"] == "complete"
        else "deterministic_fallback",
    }
    result["llm_usage"] = ctx["llm"].usage
    result["quality"]["query_count"] = collector.calls
    if len(json.dumps(result, ensure_ascii=False).encode()) > MAX_BYTES:
        raise ValueError("report_result_limit_exceeded")
    return {"result": result, "evidence": evidence}
