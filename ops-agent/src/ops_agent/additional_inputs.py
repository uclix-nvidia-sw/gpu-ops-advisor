"""Independent optional observations from mapping section 6.

No conditional investigation is enabled without its question and consumer rules.
"""

from agent_common.calculations import weighted_mean
from agent_common.contracts import metric
from agent_common.normalize import intervals

ADDITIONS = {
    "O01": ("D15", "D16", "D18", "D19", "D20"),
    "O02": ("D22",),
    "O03": ("D03", "D15"),
    "O04": ("D03", "D15"),
    "O05": ("D09", "D22"),
    "O06": ("D09", "D20"),
    "O07": ("D06", "D20", "D21"),
    "O08": ("D10", "D22"),
    "O09": ("D22",),
    "O10": ("D10", "D22"),
    "O11": ("D22",),
}


def apply_additional_inputs(topic, data, collected):
    """Keep optional failures separate from existing topic status and metrics."""
    selected = ADDITIONS[topic["topic_id"]]
    topic["quality"]["additional_inputs"] = [
        {
            "query_id": q,
            "evidence_refs": [e["id"] for e in collected.get(q, [])],
            "statuses": [e["tool_status"] for e in collected.get(q, [])],
            "reasons": sorted(
                {e["quality"].get("reason", "") for e in collected.get(q, [])} - {""}
            ),
        }
        for q in selected
    ]
    topic["evidence_refs"] = list(
        dict.fromkeys(
            topic["evidence_refs"]
            + [e["id"] for q in selected for e in collected.get(q, [])]
        )
    )
    if topic["topic_id"] != "O01":
        return
    period = data["time_range"]

    def put(name, value, unit, refs, target, method, reason):
        item = metric(
            "O01." + name, value, unit, data, list(dict.fromkeys(refs)), method, reason
        )
        item["target"] = target
        item["quality"]["optional"] = True
        topic["metrics"].append(item)

    def means(query, name, units, identity):
        rows = intervals(collected.get(query, []), period)
        emitted = False
        for row in rows:
            labels = row["labels"]
            target = {
                "cluster_id": row["cluster_id"],
                **{key: labels.get(key) for key in identity},
            }
            if any(not labels.get(key) for key in identity):
                continue
            spans = (
                row["intervals"]
                if row.get("unit") in units and row.get("sample_type") == "gauge"
                else []
            )
            put(
                name,
                weighted_mean(spans),
                row.get("unit") or "unknown",
                row["evidence_refs"],
                target,
                "time_weighted_original_samples",
                "binding_semantics_or_samples_missing",
            )
            emitted = True
        if not emitted:
            put(
                name,
                None,
                next(iter(units)),
                [e["id"] for e in collected.get(query, [])],
                data["scope"],
                "time_weighted_original_samples",
                "binding_semantics_or_samples_missing",
            )

    means("D15", "gpu_memory_free_mean", ("MiB", "bytes"), ("gpu_uuid",))
    means("D18", "node_cpu_used_mean", ("percent",), ("node",))
    means("D19", "node_load_by_window", ("load",), ("node", "window"))
    used = intervals(collected.get("D03", []), period)
    totals = intervals(collected.get("D16", []), period)
    emitted = False
    for row in used:
        gpu = row["labels"].get("gpu_uuid")
        if not gpu:
            continue
        matches = [
            r
            for r in totals
            if r["cluster_id"] == row["cluster_id"]
            and r["labels"].get("gpu_uuid") == gpu
            and r.get("sample_type") == "gauge"
            and r.get("unit") == row.get("unit")
            and r["labels"].get("node") == row["labels"].get("node")
        ]
        ratios, refs = [], list(row["evidence_refs"])
        # Ambiguous same-GPU capacity or used series cannot establish a ratio.
        same_used = [
            r
            for r in used
            if r["cluster_id"] == row["cluster_id"]
            and r["labels"].get("gpu_uuid") == gpu
        ]
        if (
            len(matches) == len(same_used) == 1
            and row.get("unit") in {"MiB", "bytes"}
            and row.get("sample_type") == "gauge"
        ):
            refs += matches[0]["evidence_refs"]
            for a, b, value in row["intervals"]:
                for x, y, total in matches[0]["intervals"]:
                    if min(b, y) > max(a, x) and 0 <= value <= total and total > 0:
                        ratios.append((max(a, x), min(b, y), value / total))
        put(
            "gpu_memory_used_ratio",
            weighted_mean(ratios),
            "ratio",
            refs,
            {"cluster_id": row["cluster_id"], "gpu_uuid": gpu},
            "same_gpu_time_unit_intersection",
            "gpu_capacity_join_unverified",
        )
        emitted = True
    if not emitted:
        put(
            "gpu_memory_used_ratio",
            None,
            "ratio",
            [],
            data["scope"],
            "same_gpu_time_unit_intersection",
            "gpu_capacity_join_unverified",
        )
    # Node conditions remain timestamped observations, never GPU health facts.
    topic["quality"]["node_condition_observations"] = [
        {
            "cluster_id": row["cluster_id"],
            "labels": row["labels"],
            "intervals": row["intervals"],
            "evidence_refs": row["evidence_refs"],
        }
        for row in intervals(collected.get("D20", []), period)
        if row.get("sample_type") == "info"
        and row["labels"].get("node")
        and row["labels"].get("condition")
        and row["labels"].get("status")
    ]
