"""Count distinct recorded incidents, without re-running RCA or reading its body."""

import re
from collections import defaultdict


def summarize(context):
    if context.get("incident_limit_exceeded"):
        return {
            "status": "blocked",
            "reason": "incident_limit_exceeded",
            "count": None,
            "previous_count": None,
            "change": None,
            "groups": [],
            "incidents": [],
            "status_as_of": context["data_cutoff_at"],
        }
    current = {row["id"]: row for row in context["incidents"]}
    previous = {row["id"]: row for row in context["previous_incidents"]}

    def group(rows):
        groups = defaultdict(list)
        for row in rows.values():
            target = row.get("target") or {}
            # A recorded GPU UUID is a grouping key, not a newly verified root cause.
            device = target.get("gpu_uuid")
            if device and row.get("symptom"):
                groups[
                    (
                        row["cluster_id"],
                        device,
                        row.get("symptom_key") or row["symptom"],
                        row["symptom"],
                    )
                ].append(row["id"])
        return groups

    now_groups, old_groups = group(current), group(previous)
    groups = [
        {
            "cluster_id": key[0],
            "gpu_uuid": key[1],
            "symptom": key[3],
            "count": len(now_groups.get(key, [])),
            "previous_count": len(old_groups.get(key, [])),
            "incident_ids": now_groups.get(key, []),
            "change": len(now_groups.get(key, [])) - len(old_groups.get(key, [])),
        }
        for key in sorted(now_groups.keys() | old_groups.keys())
    ]

    # Categories describe recorded alerts, not inferred causes or repeated failures.
    def categories(records):
        grouped = defaultdict(list)
        for row in records.values():
            target = row.get("target") or {}
            code = re.search(
                r"\b(SXID|XID)\s*[:#]?\s*(\d+)\b", row.get("symptom") or "", re.I
            )
            label = (
                f"{code[1].upper()} {code[2]}"
                if code
                else {"disk": "디스크·파일시스템"}.get(
                    target.get("component"), target.get("component")
                )
                or target.get("alertname")
                or "장애 종류 미확인"
            )
            grouped[(row["cluster_id"], label)].append(row)
        return grouped

    now_types, old_types = categories(current), categories(previous)
    types = []
    for key in sorted(now_types.keys() | old_types.keys()):
        events = now_types.get(key, [])
        types.append(
            {
                "cluster_id": key[0],
                "name": key[1],
                "count": len(events),
                "previous_count": len(old_types.get(key, [])),
                "nodes": sorted(
                    {
                        r["target"]["node"]
                        for r in events
                        if (r.get("target") or {}).get("node")
                    }
                ),
                "firing_count": sum(r.get("alarm_status") == "firing" for r in events),
                "test_count": sum(
                    (r.get("target") or {}).get("test_alarm") is True for r in events
                ),
                "incident_ids": [r["id"] for r in events],
            }
        )
    return {
        "categories": types,
        "status": "ready",
        "count": len(current),
        "previous_count": len(previous),
        "change": len(current) - len(previous),
        "groups": groups,
        "incidents": list(current.values()),
        "status_as_of": context["data_cutoff_at"],
        "unclassified_count": len(current)
        - sum(len(ids) for ids in now_groups.values()),
        "grouping_basis": "recorded_gpu_uuid_and_exact_symptom",
    }
