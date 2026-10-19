"""Deterministic source-report summaries, not model findings or health facts."""

from datetime import datetime
from zoneinfo import ZoneInfo

from .requirement_diagnostics import _scoped_reports


def report_scope(row):
    """Compare explicit producer identity only, without inferring device aliases."""
    return (
        row.get("cluster_id"),
        tuple(sorted(row.get("target", {}).items())),
        row.get("component"),
    )


def event_devices_by_scope(events):
    devices = {}
    for event in events:
        if (
            event.get("status") == "reported_event"
            and event.get("time_basis") == "producer_event_time"
            and event.get("event_time")
            and event.get("evidence_refs")
            and event.get("reported_device")
        ):
            devices.setdefault(report_scope(event), set()).add(event["reported_device"])
    return devices


def summarize_reports(health, events, data):
    reports, events = _scoped_reports(health, events, data)
    groups = {}
    devices = event_devices_by_scope(events)
    for kind, rows in (("event", events), ("state", reports)):
        for row in rows:
            scope = report_scope(row)
            event_devices = devices.get(scope, set())
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
                addresses = row.get("reported_pci_addresses", [])
                if row.get("error_code") and addresses:
                    detail = (
                        row["error_code"].upper()
                        + " · "
                        + ", ".join(addresses)
                        + " 상태 보고 · "
                        + row.get("raw_health", "")
                    )
                    if event_devices and not event_devices.intersection(addresses):
                        detail = "다른 장치의 참고 기록: " + detail
                elif row.get("reason"):
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
            key = (kind, where, detail, scope)
            group = groups.setdefault(key, {"times": [], "refs": [], "count": 0})
            group["context_only"] = bool(
                kind == "state"
                and event_devices
                and not event_devices.intersection(
                    row.get("reported_pci_addresses", [])
                )
            )
            group["count"] += 1
            group["times"].append(at)
            group["refs"].extend(row["evidence_refs"])
    result = []
    shown_locations = set()
    for (kind, where, detail, _), group in groups.items():
        times = sorted(
            group["times"],
            key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")),
        )

        def display(value):
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return moment.astimezone(
                ZoneInfo(data.get("timezone") or "Asia/Seoul")
            ).isoformat(timespec="seconds")

        span = (
            display(times[0])
            if times[0] == times[-1]
            else f"{display(times[0])} ~ {display(times[-1])}"
        )
        location = where + ": " if where not in shown_locations else ""
        shown_locations.add(where)
        basis = "생산자 이벤트 시각" if kind == "event" else "로그 기록 시각"
        result.append(
            {
                "text": f"{location}{detail} {group['count']}건을 수집했습니다. {basis}: {span}.",
                "evidence_refs": list(dict.fromkeys(group["refs"])),
                "context_only": group["context_only"],
            }
        )
    return result
