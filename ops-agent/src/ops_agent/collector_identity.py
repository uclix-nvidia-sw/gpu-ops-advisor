"""Reconcile collector handoffs only with matching, disjoint source evidence."""

from collections import defaultdict
import math

from .identity_transitions import identity

COLLECTOR_LABELS = {"instance", "exporter_pod"}
JOB_FIELDS = {
    "kube_job_created": "created",
    "kube_job_status_start_time": "started",
    "kube_job_status_completion_time": "completed",
}


def groups(evidence):
    query = evidence["query_id"]
    output = defaultdict(list)
    if query not in {"hourly_pod_identity", "hourly_gpu_jobs"}:
        return output
    for series in evidence["snapshot"]["series"]:
        labels = series["metric"]
        key = tuple((k, v) for k, v in identity(labels) if k not in COLLECTOR_LABELS)
        for at, value in series["values"]:
            output[(float(at), key)].append((labels, value))
    return output


def source_values(rows, query):
    sources = defaultdict(dict)
    for labels, value in rows:
        source = identity(labels)
        field = labels.get("measure") if query == "hourly_gpu_jobs" else "sample_count"
        if field in sources[source]:
            return None  # Duplicate records are not a collector handoff.
        value = float(value)
        if not math.isfinite(value):
            return None
        sources[source][field] = value
    return sources


def verified(at, rows, query, bounds):
    sources = source_values(rows, query)
    if not sources or len(sources) < 2:
        return False
    by_metric = defaultdict(list)
    observed = defaultdict(dict)
    for row in bounds:
        labels = row["labels"]
        source = identity(labels)
        metric = row.get("metric_name", "kube_pod_info")
        values = row["values"]
        if (
            source not in sources
            or metric in observed[source]
            or not at - 3600 <= row["first"] <= row["last"] < at
            or row["min_gap"] < 14
            or row["max_gap"] > 30
            or values["sample_count"] <= 0
        ):
            return False
        if query == "hourly_pod_identity":
            if (
                metric != "kube_pod_info"
                or values["minimum"] != 1
                or values["maximum"] != 1
            ):
                return False
            observed[source][metric] = {"sample_count": values["sample_count"]}
        else:
            field = JOB_FIELDS.get(metric)
            if field is None:
                return False
            observed[source][metric] = {
                field + "_min": values["minimum"],
                field + "_max": values["maximum"],
            }
        by_metric[metric].append(row)
    if set(observed) != set(sources):
        return False
    for source, metrics in observed.items():
        values = {k: v for fields in metrics.values() for k, v in fields.items()}
        if values != sources[source]:
            return False
        if (
            query == "hourly_gpu_jobs"
            and not {"created_min", "created_max"} <= values.keys()
        ):
            return False
    for segments in by_metric.values():
        segments.sort(key=lambda row: row["first"])
        if any(
            not 0 < b["first"] - a["last"] <= 30 for a, b in zip(segments, segments[1:])
        ):
            return False
    labels = rows[0][0]
    if query == "hourly_pod_identity":
        segments = by_metric["kube_pod_info"]
        count = sum(s["sample_count"] for s in sources.values())
        return bool(
            labels.get("uid")
            and labels.get("node")
            and 238 <= count <= 242
            and segments[0]["first"] - (at - 3600) <= 30
            and at - segments[-1]["last"] <= 30
        )
    # Job gauges have no UID: the unchanged lifetime checks must still succeed.
    return True


def series_for(evidence):
    """Keep snapshots immutable; only verified handoffs lose collector-only labels."""
    query = evidence["query_id"]
    if query not in {"hourly_pod_identity", "hourly_gpu_jobs"}:
        return evidence["snapshot"]["series"]
    series = evidence["snapshot"]["series"]
    if any(len(s["values"]) != len({float(t) for t, _ in s["values"]}) for s in series):
        return series  # Preserve the existing duplicate-timestamp rejection.
    checks = evidence.get("quality", {}).get("collector_handoffs", [])
    output = []
    merged = defaultdict(list)
    for (at, key), rows in groups(evidence).items():
        sources = source_values(rows, query)
        proof = [
            c
            for c in checks
            if c["at"] == at and tuple(map(tuple, c["identity"])) == key
        ]
        safe = sources is not None and (
            len(sources) == 1
            or (len(proof) == 1 and verified(at, rows, query, proof[0]["bounds"]))
        )
        if not safe:
            output.extend(
                {"metric": labels, "values": [[at, value]]} for labels, value in rows
            )
            continue
        values = defaultdict(list)
        for source in sources.values():
            for field, value in source.items():
                values[field].append(value)
        for field, observed in values.items():
            value = (
                sum(observed)
                if query == "hourly_pod_identity"
                else min(observed)
                if field.endswith("_min")
                else max(observed)
            )
            labels = dict(key)
            if query == "hourly_gpu_jobs":
                labels["measure"] = field
            merged[tuple(sorted(labels.items()))].append([at, str(value)])
    output.extend(
        {"metric": dict(key), "values": values} for key, values in merged.items()
    )
    return output
