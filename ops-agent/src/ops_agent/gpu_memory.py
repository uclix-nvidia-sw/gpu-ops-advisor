"""Optional device memory on the same verified GPU/hour as activity; Ops only."""

from collections import defaultdict
import math

from agent_common.contracts import metric, timestamp
from .report_interpretation import hourly_pair_for

QUERY = "hourly_gpu_memory"
VERSION = "gpu-memory-v1"
MEASURES = {
    f"{field}_{measure}"
    for field in ("used", "free")
    for measure in ("sum", "count", "min", "max")
}


def identity(labels):
    return tuple(
        sorted((k, v) for k, v in labels.items() if k not in {"measure", "__name__"})
    )


def indexed(evidence, query):
    values = defaultdict(list)
    for e in evidence:
        if e["query_id"] != query or e["tool_status"] != "ok":
            continue
        allowed = e["scope"]["clusters"][0].get("namespaces")
        for series in e["snapshot"]["series"]:
            labels = series["metric"]
            if labels.get("cluster_id") != e["cluster_id"] or (
                allowed is not None and labels.get("namespace") not in allowed
            ):
                continue
            for at, value in series["values"]:
                try:
                    at, value = float(at), float(value)
                except (ValueError, TypeError):
                    continue
                values[(at, identity(labels), labels.get("measure"))].append(value)
    return values


def enrich_memory(topic, evidence, data):
    """Append optional fields/metrics, preserving all existing calculations and IDs."""
    current = [e for e in evidence if e["time_range"] == data["time_range"]]
    memory = indexed(current, QUERY)
    activity = indexed(current, "hourly_gpu_activity")
    identities = defaultdict(list)
    for at, labels, measure in activity:
        if measure == "sample_count":
            d = dict(labels)
            identities[(at, d.get("cluster_id"), d.get("UUID"))].append(labels)
    memory_identities = defaultdict(set)
    for at, labels, measure in memory:
        d = dict(labels)
        memory_identities[(at, d.get("cluster_id"), d.get("UUID"))].add(labels)
    for row in topic["rows"]:
        refs = [
            e["id"]
            for e in current
            if e["query_id"] == QUERY and e["cluster_id"] == row["cluster_id"]
        ]
        hours = []
        for hour in row["hours"]:
            at = timestamp(hour["end"])
            samples, used, free = 0, 0, 0
            reason = "memory_observation_missing"
            valid = hour["activity_percent"] is not None and bool(hour["gpu_ids"])
            for gpu in hour["gpu_ids"] if valid else []:
                candidates = identities[(at, row["cluster_id"], gpu)]
                # Transition proof covers activity only. Do not assume memory followed it.
                if len(candidates) != 1 or memory_identities[
                    (at, row["cluster_id"], gpu)
                ] != set(candidates):
                    valid, reason = False, "memory_identity_unverified"
                    break
                labels = candidates[0]
                d = dict(labels)
                if (d.get("namespace"), d.get("modelName")) != (
                    row["namespace"],
                    row["gpu_model"],
                ):
                    valid, reason = False, "memory_identity_unverified"
                    break
                vals = {m: memory.get((at, labels, m), []) for m in MEASURES}
                if any(len(v) != 1 or not math.isfinite(v[0]) for v in vals.values()):
                    valid = False
                    break
                vals = {m: v[0] for m, v in vals.items()}
                count = activity[(at, labels, "sample_count")]
                if (
                    len(count) != 1
                    or any(vals[f"{f}_count"] != count[0] for f in ("used", "free"))
                    or not 238 <= count[0] <= 242
                ):
                    valid, reason = False, "memory_samples_mismatch"
                    break
                # Reject DCGM sentinel/invalid values as well as negative or inconsistent sums.
                if (
                    any(
                        not (
                            0 <= vals[f"{f}_min"] <= vals[f"{f}_max"] < 2**31
                            and vals[f"{f}_min"] * count[0]
                            <= vals[f"{f}_sum"]
                            <= vals[f"{f}_max"] * count[0] + 1e-6
                        )
                        for f in ("used", "free")
                    )
                    or vals["used_sum"] + vals["free_sum"] <= 0
                ):
                    valid, reason = False, "invalid_memory_aggregate"
                    break
                samples += count[0]
                used += vals["used_sum"]
                free += vals["free_sum"]
            if samples != hour["sample_count"]:
                valid = False
            hours.append(
                {
                    "start": hour["start"],
                    "end": hour["end"],
                    "used_gib_per_gpu": used / samples / 1024
                    if valid and samples
                    else None,
                    "free_gib_per_gpu": free / samples / 1024
                    if valid and samples
                    else None,
                    "sample_count": samples if valid else 0,
                    "reason": None if valid and samples else reason,
                }
            )
        valid_hours = [h for h in hours if h["used_gib_per_gpu"] is not None]
        count = sum(h["sample_count"] for h in valid_hours)
        row["gpu_memory"] = {
            "version": VERSION,
            "hours": hours,
            "evidence_refs": refs,
            "status": "available"
            if valid_hours and len(valid_hours) == len(hours)
            else "partial"
            if valid_hours
            else "unavailable",
            "used_gib_per_gpu": sum(
                h["used_gib_per_gpu"] * h["sample_count"] for h in valid_hours
            )
            / count
            if count
            else None,
            "free_gib_per_gpu": sum(
                h["free_gib_per_gpu"] * h["sample_count"] for h in valid_hours
            )
            / count
            if count
            else None,
        }
        target = {
            "cluster_id": row["cluster_id"],
            "namespace": row["namespace"],
            "model": row["gpu_model"],
        }
        pair, _ = hourly_pair_for(topic, target)
        # Supplement the existing editorial focus rather than invent another comparison.
        focus = next(
            (h for h in valid_hours if pair and h["end"] == pair[1]["period"]["end"]),
            None,
        )
        if focus is None and not pair:
            focus = next(iter(reversed(valid_hours)), None)
        finding = next(
            (f for f in topic["findings"] if f.get("target") == target), None
        )
        if focus is None or finding is None:
            continue
        ids = []
        for field in ("used", "free"):
            m = metric(
                f"namespace_usage.memory_{field}.{len(topic['metrics'])}",
                focus[f"{field}_gib_per_gpu"],
                "GiB",
                data,
                refs,
                VERSION,
            )
            m.update(target=target, period={k: focus[k] for k in ("start", "end")})
            topic["metrics"].append(m)
            ids.append(m["id"])
        finding["memory_refs"] = ids
        finding["value_refs"] += ids
        finding["evidence_refs"] = list(dict.fromkeys(finding["evidence_refs"] + refs))
    topic["evidence_refs"] = list(
        dict.fromkeys(
            topic["evidence_refs"]
            + [e["id"] for e in current if e["query_id"] == QUERY]
        )
    )
    topic["quality"]["gpu_memory_version"] = VERSION
