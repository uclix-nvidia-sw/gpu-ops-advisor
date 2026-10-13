"""Count distinct recorded incidents, without re-running RCA or reading its body."""

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
    return {
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
