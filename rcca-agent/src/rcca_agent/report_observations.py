"""Deterministic source-report summaries, not model findings or health facts."""

from datetime import datetime

from .requirement_diagnostics import _scoped_reports


def summarize_reports(health, events, data):
    reports, events = _scoped_reports(health, events, data)
    groups = {}
    for kind, rows in (("event", events), ("state", reports)):
        for row in rows:
            if not row.get("evidence_refs"):
                continue
            if kind == "event":
                if row.get("time_basis") != "producer_event_time":
                    continue
                at = row.get("event_time")
                detail = "오류 이벤트 " + row["error_code"]
                if row.get("reported_device"):
                    detail += " · 보고된 장치 " + row["reported_device"]
            else:
                if row.get("time_basis") != "loki_recorded_at":
                    continue
                at = row.get("observed_at")
                detail = "컴포넌트 " + row["component"] + " 상태 보고"
                if row.get("raw_health"):
                    detail += " · 보고된 상태 " + row["raw_health"]
                if row.get("reason"):
                    detail += " · 보고 사유: " + row["reason"]
            if not at:
                continue
            target = row["target"]
            where = "클러스터 " + row["cluster_id"]
            where += " · 대상 " + (
                target.get("node")
                or target.get("machine_id")
                or target.get("gpu_uuid")
                or target.get("pod_uid", "")
            )
            if target.get("machine_id") and target.get("node"):
                where += " · machine_id " + target["machine_id"]
            key = (kind, where, detail)
            group = groups.setdefault(key, {"times": [], "refs": [], "count": 0})
            group["count"] += 1
            group["times"].append(at)
            group["refs"].extend(row["evidence_refs"])
    result = []
    for (kind, where, detail), group in groups.items():
        times = sorted(
            group["times"],
            key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")),
        )
        span = times[0] if times[0] == times[-1] else f"{times[0]} ~ {times[-1]}"
        basis = "생산자 이벤트 시각" if kind == "event" else "로그 기록 시각"
        result.append(
            {
                "text": f"{where}: {detail} {group['count']}건을 수집했습니다. {basis}: {span}.",
                "evidence_refs": list(dict.fromkeys(group["refs"])),
            }
        )
    return result
