"""Deterministic operator history from stored Incident identities, not log counts."""

from collections import Counter

from agent_common.contracts import incident_source, timestamp

from .incident import alert_clues
from .fleet_events import STATUS_UUID


def host_history(context, data):
    source = context.get("host_incidents")
    if not source:
        return None
    target = data.get("target", {})
    clusters = {c["cluster_id"] for c in data["scope"]["clusters"]}
    result = {
        "schema": "rca-host-history/1",
        "period": source["period"],
        "complete": source["complete"],
        "rows": [],
        "repeats": [],
    }
    seen = set()
    for record in source["rows"]:
        item = record["body"]
        identity = item.get("target") or {}
        if item.get("cluster_id") not in clusters or item.get("id") in seen:
            continue
        machine, node = (
            target.get("machine_id"),
            (target.get("node") or target.get("k8s_node_name")),
        )
        if machine:
            if identity.get("machine_id") != machine:
                continue
        elif (
            not node or (identity.get("node") or identity.get("k8s_node_name")) != node
        ):
            continue
        at = item.get("occurred_at")
        try:
            if (
                not timestamp(source["period"]["start"])
                <= timestamp(at)
                <= timestamp(source["period"]["end"])
            ):
                continue
        except (ValueError, TypeError):
            continue
        seen.add(item["id"])
        try:
            clues = alert_clues(incident_source(record.get("snapshot") or {}))
        except ValueError:
            clues = {"error_codes": [], "reason": item.get("symptom", "")}
        reported_uuids = set(STATUS_UUID.findall(clues.get("reason") or ""))
        reported_gpu = (
            next(iter(reported_uuids))
            if len(reported_uuids) == 1
            and any(c.startswith("xid:") for c in clues["error_codes"])
            else None
        )
        first = item.get("episode_started_at") or item.get("first_seen") or at
        last = item.get("last_observed_at") or item.get("last_seen") or at
        span = None
        last_capped = False
        try:
            if timestamp(last) > timestamp(source["period"]["end"]):
                last = source["period"]["end"]
                last_capped = True
            if timestamp(last) >= timestamp(first):
                span = timestamp(last) - timestamp(first)
        except (ValueError, TypeError):
            pass
        result["rows"].append(
            {
                "incident_id": item["id"],
                "occurred_at": at,
                "first_report": first,
                "last_report": last,
                "last_report_capped": last_capped,
                "reported_span_seconds": span,
                "codes": clues["error_codes"],
                "gpu_uuid": identity.get("gpu_uuid") or reported_gpu,
                "reason": clues.get("reason", ""),
                "current": item["id"] == data["incident_id"],
            }
        )
    result["rows"].sort(
        key=lambda r: (timestamp(r["occurred_at"]), r["incident_id"]), reverse=True
    )
    counts = Counter(
        (r["gpu_uuid"], code) for r in result["rows"] for code in r["codes"]
    )
    result["repeats"] = [
        {"gpu_uuid": gpu, "code": code, "incident_count": n}
        for (gpu, code), n in counts.items()
        if n > 1
    ]
    return result


def history_summary(history):
    if not history:
        return []
    refs = history["evidence_refs"]
    period = history["period"]
    rows = [
        {
            "section": "comparison",
            "text": f"호스트 사건 이력: {period['start']} ~ {period['end']}, 등록 사건 {len(history['rows'])}건. 사건 ID별로 집계했습니다.",
            "evidence_refs": refs,
        }
    ]
    for repeat in history["repeats"]:
        rows.append(
            {
                "section": "comparison",
                "text": f"{repeat['gpu_uuid'] or '이 호스트'}에서 {repeat['code'].upper()} 관련 사건 {repeat['incident_count']}건이 등록됐습니다. 이전 사건의 대상 장치·동반 오류를 함께 대조해 우선 점검 대상을 정하세요.",
                "evidence_refs": refs,
            }
        )
    return rows
