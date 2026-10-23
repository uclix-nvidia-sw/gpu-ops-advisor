"""Bounded hourly sample aggregates, with conservative attribution checks."""

from collections import defaultdict
import math

from agent_common.contracts import timestamp

from .report_contract import MAX_GPU_SERIES, MAX_NAMESPACES, iso
from .identity_transitions import identity
from .collector_identity import series_for

MEASURES = {"activity_sum", "sample_count", "minimum", "maximum"}


def number(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("non_finite_aggregate")
    return value


def summarize(evidence, period):
    start, end = (timestamp(period[k]) for k in ("start", "end"))
    expected = set(range(int(start) + 3600, int(end) + 1, 3600))
    activity, identities, gpu_identities = {}, defaultdict(list), defaultdict(list)
    errors, refs = defaultdict(set), [e["id"] for e in evidence]
    transitions = defaultdict(list)
    for e in evidence:
        if e["query_id"] == "gpu_identity_transitions":
            if e["tool_status"] == "ok":
                for check in e["snapshot"]["checks"]:
                    labels = check["labels"]
                    allowed = e["scope"]["clusters"][0].get("namespaces")
                    if (
                        labels.get("cluster_id") != e["cluster_id"]
                        or (
                            allowed is not None
                            and labels.get("namespace") not in allowed
                        )
                        or check["at"] not in expected
                    ):
                        raise ValueError("invalid_transition_scope")
                    transitions[(check["at"], identity(labels))].append(check)
            continue
        if e["tool_status"] != "ok":
            errors[e["cluster_id"]].add(
                e["quality"].get("reason") or "query_unavailable"
            )
            continue
        for series in series_for(e):
            labels = series["metric"]
            if labels.get("cluster_id") != e["cluster_id"]:
                raise ValueError("aggregate_cluster_mismatch")
            allowed = e["scope"]["clusters"][0].get("namespaces")
            if (
                e["query_id"] != "hourly_gpu_identity_count"
                and allowed is not None
                and labels.get("namespace") not in allowed
            ):
                raise ValueError("aggregate_namespace_mismatch")
            seen = set()
            for at, value in series["values"]:
                at, value = number(at), number(value)
                if at not in expected or at in seen:
                    raise ValueError("invalid_aggregate_time")
                seen.add(at)
                if e["query_id"] == "hourly_gpu_activity":
                    measure = labels.get("measure")
                    if measure not in MEASURES:
                        raise ValueError("unknown_aggregate_measure")
                    key = (
                        at,
                        tuple(
                            sorted(
                                (k, v)
                                for k, v in labels.items()
                                if k not in {"measure", "__name__"}
                            )
                        ),
                    )
                    row = activity.setdefault(
                        key, {"labels": labels, "at": at, "values": {}}
                    )
                    if measure in row["values"]:
                        raise ValueError("duplicate_aggregate_measure")
                    row["values"][measure] = value
                elif e["query_id"] == "hourly_pod_identity":
                    identities[
                        (
                            at,
                            labels.get("cluster_id"),
                            labels.get("namespace"),
                            labels.get("pod"),
                            labels.get("node"),
                        )
                    ].append((labels, value))
                elif e["query_id"] == "hourly_gpu_identity_count":
                    gpu_identities[
                        (at, labels.get("cluster_id"), labels.get("UUID"))
                    ].append((labels, value))
    devices = {
        (r["labels"].get("cluster_id"), r["labels"].get("UUID"))
        for r in activity.values()
    }
    if len(devices) > MAX_GPU_SERIES:
        raise ValueError("report_gpu_limit_exceeded")
    by_gpu = defaultdict(list)
    for row in activity.values():
        labels = row["labels"]
        by_gpu[(row["at"], labels.get("cluster_id"), labels.get("UUID"))].append(row)
    groups = {}
    for row in activity.values():
        labels, values, at = row["labels"], row["values"], row["at"]
        checks = transitions[(at, identity(labels))]
        gpu_checks = gpu_identities[(at, labels.get("cluster_id"), labels.get("UUID"))]
        verified = (
            len(checks) == 1
            and checks[0]["values"] == values
            and len(gpu_checks) == 1
            and gpu_checks[0][1] == checks[0]["source_identity_count"]
        )
        key = (
            labels.get("cluster_id"),
            labels.get("namespace", ""),
            labels.get("modelName", ""),
        )
        group = groups.setdefault(
            key,
            {
                "cluster_id": key[0],
                "namespace": key[1],
                "gpu_model": key[2],
                "gpu_ids": set(),
                "hours": {},
            },
        )
        bucket = group["hours"].setdefault(
            at,
            {
                "end": iso(at),
                "start": iso(at - 3600),
                "activity_sum": 0,
                "sample_count": 0,
                "reasons": set(),
                "gpu_ids": set(),
                "nodes": set(),
            },
        )
        reason = None
        if not all(
            labels.get(k) for k in ("UUID", "namespace", "pod", "Hostname", "modelName")
        ):
            reason = "identity_labels_missing"
        elif (
            labels.get("node", labels["Hostname"]) != labels["Hostname"]
            or labels.get("uuid", labels["UUID"]) != labels["UUID"]
        ):
            reason = "identity_labels_conflict"
        elif len(by_gpu[(at, key[0], labels["UUID"])]) != 1 and not verified:
            reason = "duplicate_or_changed_gpu_identity"
        elif (
            set(values) != MEASURES
            or not (0 <= values["minimum"] <= values["maximum"] <= 100)
            or not (0 < values["sample_count"] == int(values["sample_count"]))
            or not (
                values["minimum"] * values["sample_count"]
                <= values["activity_sum"]
                <= values["maximum"] * values["sample_count"] + 1e-6
            )
        ):
            reason = "invalid_activity_aggregate"
        else:
            pods = identities[(at, key[0], key[1], labels["pod"], labels["Hostname"])]
            if not pods or (
                not verified and (len(pods) != 1 or not pods[0][0].get("uid"))
            ):
                reason = "pod_identity_unverified"
            elif verified and (
                {p[0].get("uid") for p in pods} != {checks[0]["pod_uid"]}
                or sum(p[1] for p in pods) != checks[0]["pod_sample_count"]
            ):
                reason = "pod_identity_unverified"
            elif (
                not 238 <= values["sample_count"] <= 242 or not 238 <= pods[0][1] <= 242
            ) and not verified:
                reason = "incomplete_hour_or_sampling_interval"
            else:
                identities_for_gpu = gpu_identities[(at, key[0], labels["UUID"])]
                if not verified and (
                    len(identities_for_gpu) != 1 or identities_for_gpu[0][1] != 1
                ):
                    reason = "duplicate_or_changed_gpu_identity"
                elif (
                    labels["UUID"].startswith("MIG-")
                    or any(
                        labels.get(k) is not None
                        for k in (
                            "GPU_I_ID",
                            "GPU_I_PROFILE",
                            "GPU_CI_ID",
                            "instance_id",
                        )
                    )
                    or labels.get("allocation_mode") in {"shared", "mig"}
                ):
                    reason = "shared_or_mig_attribution_unverified"
        if reason:
            bucket["reasons"].add(reason)
            continue
        bucket["activity_sum"] += values["activity_sum"]
        if verified:
            bucket["verified_connection_change"] = True
        bucket["sample_count"] += values["sample_count"]
        bucket["gpu_ids"].add(labels["UUID"])
        bucket["nodes"].add(labels["Hostname"])
        group["gpu_ids"].add(labels["UUID"])
    if len({(k[0], k[1]) for k in groups}) > MAX_NAMESPACES:
        raise ValueError("report_namespace_limit_exceeded")
    output = []
    for key, group in sorted(groups.items()):
        hours = []
        for at in sorted(expected):
            bucket = group["hours"].get(
                at,
                {
                    "start": iso(at - 3600),
                    "end": iso(at),
                    "activity_sum": 0,
                    "sample_count": 0,
                    "reasons": {"unobserved_hour"},
                    "gpu_ids": set(),
                    "nodes": set(),
                },
            )
            reasons = sorted(bucket["reasons"] | errors[key[0]])
            count = bucket["sample_count"]
            hours.append(
                {
                    **bucket,
                    "gpu_ids": sorted(bucket["gpu_ids"]),
                    "nodes": sorted(bucket["nodes"]),
                    "reasons": reasons,
                    "activity_percent": bucket["activity_sum"] / count
                    if count and not reasons
                    else None,
                }
            )
        valid = [h for h in hours if h["activity_percent"] is not None]
        activity_sum = sum(h["activity_sum"] for h in valid)
        count = sum(h["sample_count"] for h in valid)
        low_windows = []
        for hour in valid if len(valid) == len(expected) else []:
            if hour["activity_percent"] >= 5:
                continue
            if low_windows and low_windows[-1]["end"] == hour["start"]:
                low_windows[-1]["end"] = hour["end"]
            else:
                low_windows.append({"start": hour["start"], "end": hour["end"]})
        output.append(
            {
                **group,
                "gpu_ids": sorted(group["gpu_ids"]),
                "hours": hours,
                "nodes": sorted({node for h in valid for node in h["nodes"]}),
                "activity_sum": activity_sum,
                "sample_count": count,
                "activity_percent": activity_sum / count if count else None,
                "observed_gpu_count": len({gpu for h in valid for gpu in h["gpu_ids"]})
                if count
                else None,
                "valid_hours": len(valid),
                "expected_hours": len(expected),
                "verified_transition_hours": sum(
                    bool(h.get("verified_connection_change")) for h in valid
                ),
                "low_activity_windows": low_windows,
                "low_activity_hours": sum(h["activity_percent"] < 5 for h in valid)
                if len(valid) == len(expected)
                else None,
                "quality_status": "ready"
                if len(valid) == len(expected)
                else "partial"
                if valid
                else "blocked",
                "evidence_refs": refs,
            }
        )
    return output, sorted({reason for reasons in errors.values() for reason in reasons})


def compare(current, previous):
    old = {(r["cluster_id"], r["namespace"], r["gpu_model"]): r for r in previous}
    out = []
    for row in current:
        key = (row["cluster_id"], row["namespace"], row["gpu_model"])
        before = old.pop(key, None)
        compatible = (
            before is not None
            and row["quality_status"] == before["quality_status"] == "ready"
        )
        out.append(
            {
                **row,
                "previous_activity_percent": before["activity_percent"]
                if before
                else None,
                "change_percentage_points": row["activity_percent"]
                - before["activity_percent"]
                if compatible
                else None,
                "previous_valid_hours": before["valid_hours"] if before else 0,
                "previous_expected_hours": before["expected_hours"]
                if before
                else row["expected_hours"],
                "comparison_status": "comparable"
                if compatible
                else "previous_not_observed"
                if before is None
                else "insufficient_observation",
            }
        )
    for row in old.values():
        out.append(
            {
                **row,
                "hours": [],
                "nodes": [],
                "activity_sum": 0,
                "sample_count": 0,
                "activity_percent": None,
                "observed_gpu_count": None,
                "valid_hours": 0,
                "low_activity_hours": None,
                "low_activity_windows": [],
                "quality_status": "blocked",
                "previous_activity_percent": row["activity_percent"],
                "previous_valid_hours": row["valid_hours"],
                "previous_expected_hours": row["expected_hours"],
                "change_percentage_points": None,
                "comparison_status": "current_not_observed",
            }
        )
    return out
