"""04 §5: original-sample intervals, union/intersection and left-hold integration."""

from collections import defaultdict
from math import isfinite


def union(intervals):
    out = []
    for start, end in sorted((a, b) for a, b in intervals if b > a):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(end, out[-1][1]))
        else:
            out.append((start, end))
    return out


def intersect(a, b):
    return union((max(x, u), min(y, v)) for x, y in a for u, v in b)


def seconds(intervals):
    return sum(b - a for a, b in union(intervals))


def sample_intervals(samples, start, end, max_hold):
    """Conflicting duplicate timestamps invalidate that interval; never extrapolate beyond max_hold."""
    points = defaultdict(set)
    for t, value in samples:
        try:
            t = float(t)
            if not isfinite(t):
                continue
            points[t]
            v = float(value)
            if isfinite(v):
                points[t].add(v)
            else:
                points[t].add(None)
        except (TypeError, ValueError):
            if isinstance(t, float) and isfinite(t):
                points[t].add(None)
            continue
    times = sorted(points)
    out = []
    for i, t in enumerate(times):
        stop = min(end, t + max_hold, times[i + 1] if i + 1 < len(times) else end)
        if len(points[t]) == 1 and None not in points[t] and stop > max(t, start):
            out.append((max(t, start), stop, next(iter(points[t]))))
    return out


def weighted_mean(intervals):
    duration = sum(b - a for a, b, _ in intervals)
    return sum((b - a) * v for a, b, v in intervals) / duration if duration else None


def weighted_p95(intervals):
    duration = sum(b - a for a, b, _ in intervals)
    if not duration:
        return None
    elapsed = 0
    for a, b, v in sorted(intervals, key=lambda x: x[2]):
        elapsed += b - a
        if elapsed >= duration * 0.95:
            return v


def energy(intervals):
    return (
        sum(max(v, 0) * (b - a) for a, b, v in intervals if v >= 0) / 3600000
        if intervals
        else None
    )


def allocation_hours(rows, mode="exclusive"):
    devices = defaultdict(list)
    for r in rows:
        if r.get("mode") == mode:
            key = (
                r["cluster_id"],
                r["gpu_uuid"],
                r.get("instance_id") if mode == "mig" else None,
            )
            devices[key].append((r["start"], r["end"]))
    return sum(seconds(intervals) for intervals in devices.values()) / 3600


def low_activity(allocation, activity, start, end):
    valid = intersect(allocation, [(a, b) for a, b, v in activity if 0 <= v <= 100])
    low = intersect(allocation, [(a, b) for a, b, v in activity if 0 <= v < 5])
    duration, low_seconds = seconds(valid), seconds(low)
    coverage = duration / (end - start) if end > start else 0
    ratio = low_seconds / duration if duration else None
    status = "insufficient_data"
    reason = (
        "short_allocation_window"
        if end - start < 3600
        else "insufficient_joint_coverage"
    )
    if end - start >= 3600 and coverage >= 0.95 and ratio is not None:
        status = "low_activity_candidate" if ratio >= 0.9 else "active_observed"
        reason = None
    return dict(
        status=status,
        reason=reason,
        coverage=coverage,
        low_ratio=ratio,
        low_gpu_hours=low_seconds / 3600 if duration else None,
        active_observed=duration > low_seconds,
    )


def low_activity_windows(rows, activities):
    """Do not combine distinct Pods or allocation episodes to reach 60 minutes."""
    episodes = defaultdict(list)
    for r in rows:
        if r.get("mode") == "exclusive" and r.get("pod_uid") and r.get("episode"):
            episodes[
                (r["cluster_id"], r["gpu_uuid"], r["pod_uid"], r["episode"])
            ].append((r["start"], r["end"]))
    out = []
    for key, intervals in episodes.items():
        a, b = min(x[0] for x in intervals), max(x[1] for x in intervals)
        while a < b:
            end = min(a + 3600, b)
            activity = [
                (max(a, x), min(end, y), v)
                for x, y, v in activities.get(key[:2], [])
                if min(end, y) > max(a, x)
            ]
            out.append(
                dict(
                    target=key,
                    start=a,
                    end=end,
                    **low_activity(intersect(intervals, [(a, end)]), activity, a, end),
                )
            )
            a = end
    return out


def normalize_health(raw, contract=None):
    """Only a deployed, validated producer mapping can assign health meaning."""
    out = dict(
        raw_health=raw.get("health"),
        check_status="unknown",
        normalized_health="unknown",
        component=raw.get("component"),
        severity="unknown",
        target=raw.get("target", {}),
        observed_at=raw.get("observed_at"),
        producer_contract=raw.get("producer_contract"),
        parser_revision=(contract or {}).get("revision"),
        evidence_refs=raw.get("evidence_refs", []),
    )
    if not contract or raw.get("producer_contract") != contract.get(
        "producer_contract"
    ):
        return out
    check = contract.get("checks", {}).get(raw.get("check_status"), "unknown")
    out["check_status"] = (
        check
        if check in {"valid", "unavailable", "skipped", "initializing", "unknown"}
        else "unknown"
    )
    if check == "valid":
        mapped = contract.get("health", {}).get(raw.get("health"), {})
        out["normalized_health"] = mapped.get("normalized_health", "unknown")
        out["severity"] = mapped.get("severity", "unknown")
    return out
