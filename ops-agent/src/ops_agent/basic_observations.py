"""Criteria 1.3 equipment records and monitoring target observations."""

import math
from collections import defaultdict

from agent_common.calculations import seconds, weighted_mean
from agent_common.contracts import metric, timestamp
from agent_common.normalize import intervals
from agent_common.observation import series
from .activity_trends import iso


def basic_observations(topic, data, collected):
    period = data["time_range"]
    start, end = timestamp(period["start"]), timestamp(period["end"])

    def put(
        name,
        value,
        unit,
        target,
        refs,
        method,
        *,
        at=None,
        reason="observation_missing",
    ):
        item = metric(
            f"{topic['topic_id']}.{name}.{len(topic['metrics'])}",
            value,
            unit,
            data,
            list(dict.fromkeys(refs)),
            method,
            reason,
        )
        item["target"] = target
        if at is not None:
            item["period"] = {"at": iso(at)}
        item["quality"]["display_basis"] = topic["quality"].get("display_basis", "")
        topic["metrics"].append(item)
        topic["evidence_refs"] = list(dict.fromkeys(topic["evidence_refs"] + refs))

    if topic["topic_id"] == "O01":
        # Snapshot bindings deliberately have hold=0: expose recorded points, never
        # manufacture period averages from repeated scrapes of a Fleet snapshot.
        for query, name, units, identity in (
            ("D03", "recorded_memory_used", {"MiB", "bytes"}, ("gpu_uuid",)),
            ("D04", "recorded_temperature", {"celsius"}, ("gpu_uuid",)),
            ("D15", "recorded_memory_free", {"MiB", "bytes"}, ("gpu_uuid",)),
            ("D16", "recorded_memory_total", {"MiB", "bytes"}, ("gpu_uuid",)),
            ("D18", "recorded_cpu_used", {"percent"}, ("node",)),
            ("D19", "recorded_node_load", {"load"}, ("node", "window")),
        ):
            for row in series(
                [
                    e
                    for e in collected.get(query, [])
                    if e["quality"].get("complete") is not False
                ]
            ):
                if (
                    row["max_hold_seconds"]
                    or row["unit"] not in units
                    or row["sample_type"] != "gauge"
                ):
                    continue
                labels = row["labels"]
                if any(not labels.get(key) for key in identity):
                    continue
                points = []
                for at, raw in row["samples"]:
                    try:
                        value = float(raw)
                        at = float(at)
                    except (ValueError, TypeError):
                        continue
                    if (
                        start <= float(at) < end
                        and math.isfinite(value)
                        and value >= 0
                        and (row["unit"] != "percent" or value <= 100)
                    ):
                        points.append((float(at), value))
                if not points:
                    continue
                latest = max(at for at, value in points)
                values = {value for at, value in points if at == latest}
                put(
                    name,
                    next(iter(values)) if len(values) == 1 else None,
                    row["unit"],
                    {
                        "cluster_id": row["cluster_id"],
                        **{key: labels[key] for key in identity},
                    },
                    row["evidence_refs"],
                    "latest_recorded_sample_measurement_time_unverified",
                    at=latest,
                    reason="conflicting_recorded_values",
                )
                topic["metrics"][-1]["quality"]["measurement_time_verified"] = False
        for row in intervals(collected.get("D20", []), period):
            labels = row["labels"]
            if not all(
                labels.get(key) for key in ("node", "condition", "status")
            ) or row["sample_type"] not in {"gauge", "info"}:
                continue
            valid = [(a, b) for a, b, value in row["intervals"] if value in {0, 1}]
            put(
                "node_condition_seconds",
                seconds([(a, b) for a, b, value in row["intervals"] if value == 1])
                if valid
                else None,
                "seconds",
                {
                    "cluster_id": row["cluster_id"],
                    **{key: labels[key] for key in ("node", "condition", "status")},
                },
                row["evidence_refs"],
                "observed_node_condition_true_intervals",
            )
        return

    if topic["topic_id"] != "O11":
        return
    groups = defaultdict(list)
    for row in intervals(collected.get("D10", []), period):
        labels = row["labels"]
        if labels.get("job") and labels.get("instance"):
            groups[(row["cluster_id"], labels["job"], labels["instance"])].append(row)
    for (cluster, job, instance), rows in sorted(groups.items()):
        target = dict(cluster_id=cluster, job=job, instance=instance)
        refs = [ref for row in rows for ref in row["evidence_refs"]]
        changes = defaultdict(list)
        for index, row in enumerate(rows):
            if row["sample_type"] != "gauge" or row["unit"] not in {"boolean", "state"}:
                continue
            for a, b, value in row["intervals"]:
                changes[a].append((index, value))
                changes[b].append((index, None))
        changes[start]
        changes[end]
        active, totals = {}, {0: 0.0, 1: 0.0}
        times = sorted(changes)
        for a, b in zip(times, times[1:]):
            for index, value in changes[a]:
                if value is None:
                    active.pop(index, None)
                else:
                    active[index] = value
            values = set(active.values())
            if len(values) == 1 and next(iter(values)) in totals:
                totals[next(iter(values))] += b - a
        for name, value in (
            ("target_up_seconds", totals[1]),
            ("target_down_seconds", totals[0]),
            ("target_unknown_seconds", end - start - sum(totals.values())),
        ):
            put(name, value, "seconds", target, refs, "observed_target_state_intervals")
    for row in intervals(collected.get("D22", []), period):
        labels = row["labels"]
        if (
            row["unit"] not in {"seconds", "s"}
            or row["sample_type"] != "gauge"
            or not labels.get("job")
            or not labels.get("instance")
        ):
            continue
        spans = [(a, b, value) for a, b, value in row["intervals"] if value >= 0]
        target = dict(
            cluster_id=row["cluster_id"], job=labels["job"], instance=labels["instance"]
        )
        for name, value in (
            ("scrape_duration_mean", weighted_mean(spans)),
            ("scrape_duration_max", max((v for a, b, v in spans), default=None)),
        ):
            put(
                name,
                value,
                "seconds",
                target,
                row["evidence_refs"],
                "observed_scrape_duration",
            )
