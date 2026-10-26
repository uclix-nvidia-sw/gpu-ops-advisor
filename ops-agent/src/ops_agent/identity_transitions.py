"""Verify only changed GPU hours; keep compact bounds instead of raw samples."""

from collections import defaultdict
import math


def identity(labels):
    return tuple(
        sorted((k, v) for k, v in labels.items() if k not in {"measure", "__name__"})
    )


def sample_bounds(series, at, cluster):
    bounds = []
    for row in series:
        labels = dict(identity(row["metric"]))
        points = [(float(t), float(v)) for t, v in row["values"]]
        if (
            labels.get("cluster_id") != cluster
            or not points
            or any(
                not math.isfinite(t) or not math.isfinite(v) or not at - 3600 <= t < at
                for t, v in points
            )
        ):
            raise ValueError("invalid_transition_samples")
        gaps = [b[0] - a[0] for a, b in zip(points, points[1:])]
        if any(gap <= 0 for gap in gaps):
            raise ValueError("invalid_transition_samples")
        values = [v for _, v in points]
        bounds.append(
            dict(
                labels=labels,
                first=points[0][0],
                last=points[-1][0],
                min_gap=min(gaps, default=15),
                max_gap=max(gaps, default=0),
                values=dict(
                    activity_sum=sum(values),
                    sample_count=len(values),
                    minimum=min(values),
                    maximum=max(values),
                ),
            )
        )
    return bounds


def verified_transitions(gpus, pods, at, expected_counts, namespaces, *, rejected=None):
    """A whole GPU hour must be continuous, disjoint, and match the hourly identity count."""
    grouped = defaultdict(list)
    for row in gpus:
        grouped[row["labels"].get("UUID")].append(row)
    verified = []

    def reject(gpu, reason, labels=None):
        if rejected is not None and gpu in expected_counts:
            rejected.append(
                {
                    "gpu_id": gpu,
                    "reason": reason,
                    **(
                        {"namespace": labels["namespace"], "pod": labels.get("pod", "")}
                        if labels
                        else {}
                    ),
                }
            )

    for gpu, rows in grouped.items():
        rows.sort(key=lambda r: r["first"])
        if (
            len(rows) < 2
            or len(rows) != expected_counts.get(gpu)
            or len({identity(r["labels"]) for r in rows}) != len(rows)
            or len(
                {
                    (r["labels"].get("Hostname"), r["labels"].get("modelName"))
                    for r in rows
                }
            )
            != 1
        ):
            reject(gpu, "gpu_identity_unverified")
            continue
        if any(
            not r["labels"].get("Hostname")
            or not r["labels"].get("modelName")
            or r["labels"].get("node", r["labels"].get("Hostname"))
            != r["labels"].get("Hostname")
            or r["labels"].get("uuid", gpu) != gpu
            or gpu.startswith("MIG-")
            or r["labels"].get("allocation_mode") in {"shared", "mig"}
            or any(
                k in r["labels"]
                for k in ("GPU_I_ID", "GPU_I_PROFILE", "GPU_CI_ID", "instance_id")
            )
            for r in rows
        ):
            reject(gpu, "gpu_attribution_unverified")
            continue
        if (
            not 238 <= sum(r["values"]["sample_count"] for r in rows) <= 242
            or rows[0]["first"] - (at - 3600) > 30
            or at - rows[-1]["last"] > 30
            or any(r["min_gap"] < 14 or r["max_gap"] > 30 for r in rows)
            or any(not 0 < b["first"] - a["last"] <= 30 for a, b in zip(rows, rows[1:]))
        ):
            reject(gpu, "gpu_interval_unverified")
            continue
        for row in rows:
            labels = row["labels"]
            if not labels.get("namespace") or (
                namespaces is not None and labels["namespace"] not in namespaces
            ):
                continue
            matches = [
                p
                for p in pods
                if all(
                    p["labels"].get(k) == labels.get(g)
                    for k, g in (
                        ("cluster_id", "cluster_id"),
                        ("namespace", "namespace"),
                        ("pod", "pod"),
                    )
                )
            ]
            if not matches:
                reject(gpu, "pod_identity_missing", labels)
                continue
            matches.sort(key=lambda p: p["first"])
            uids = {p["labels"].get("uid") for p in matches}
            if (
                len(uids) != 1
                or not all(uids)
                or any(
                    p["labels"].get("node") != labels.get("Hostname")
                    or p["values"]["minimum"] != 1
                    or p["values"]["maximum"] != 1
                    or p["min_gap"] < 14
                    or p["max_gap"] > 30
                    for p in matches
                )
                or any(
                    not 0 < b["first"] - a["last"] <= 30
                    for a, b in zip(matches, matches[1:])
                )
                or matches[0]["first"] > row["first"] + 15
                or matches[-1]["last"] < row["last"] - 15
            ):
                reject(gpu, "pod_interval_unverified", labels)
                continue
            verified.append(
                {
                    **row,
                    "at": at,
                    "pod_uid": next(iter(uids)),
                    "pod_sample_count": sum(
                        p["values"]["sample_count"] for p in matches
                    ),
                    "source_identity_count": len(rows),
                }
            )
    return verified
